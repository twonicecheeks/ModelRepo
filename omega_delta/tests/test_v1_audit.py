"""Release regression tests for observed audit failures. All feeds are fixtures."""
import csv
import io
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core import Store, canonical, metrics, normalize_quote, stamp
from app.operations import InstanceLock, Jobs, restore_database
from app.providers import Collector, ProviderError, discover_markets, monitor_market, monitor_wallet, pages
from app.simulator import FAMILIES, inclusion_probabilities, sample_credits, simulate
from app.validation import evaluate, grade_observations
from test_core import quote


def text_csv(rows):
    b = io.StringIO()
    writer = csv.DictWriter(b, list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return b.getvalue()


class AuditDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'audit.sqlite3', ROOT/'seed')
        self.forecast = dict(self.store.records('forecasts')[0])

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_blank_forecasts_rejected_without_mutation(self):
        before = len(self.store.state()['snapshots'])
        for bad in ('', ' ', 'NaN', 'Infinity'):
            f = dict(self.forecast, control_xtc=bad)
            with self.assertRaises(ValueError):
                self.store.import_file('forecasts','bad.csv',text_csv([f]))
        self.assertEqual(len(self.store.state()['snapshots']), before)

    def test_probability_curves_must_be_monotone_paired_and_consecutive(self):
        f = self.forecast
        variants = [dict(f, control_p_over_0_5='.1',control_p_under_0_5='.9',
                         control_p_over_1_5='.9',control_p_under_1_5='.1'),
                    dict(f, control_p_under_0_5='.1',control_p_over_0_5='.1'),
                    {k:v for k,v in f.items() if k not in ('control_p_over_2_5','control_p_under_2_5')}]
        for row in variants:
            with self.assertRaises(ValueError):
                self.store.import_file('forecasts','bad-grid.csv',text_csv([row]))

    def test_blank_actual_is_excluded_and_explicit_zero_is_graded(self):
        r = dict(self.store.records('scores')[0], omega_actual_xtc='')
        self.store.import_file('scores','missing.csv',text_csv([r]))
        current = next(x for x in self.store.records('scores') if
                       (x['game_id'],x['player_id'],x['forecast_track']) ==
                       (r['game_id'],r['player_id'],r['forecast_track']))
        self.assertEqual(metrics([current])['n'], 0)
        self.assertEqual(metrics([current])['excluded'], 1)
        self.assertEqual(metrics([dict(current,omega_actual_xtc='0')])['n'],1)

    def test_scores_merge_without_discarding_earlier_weeks(self):
        before = self.store.records('scores')
        r = dict(before[0], omega_actual_xtc='8')
        self.store.import_file('scores','correction.csv',text_csv([r]))
        after = self.store.records('scores')
        self.assertEqual(len(after),len(before))
        self.assertEqual({x['week'] for x in after},{'1','2'})
        self.assertEqual(sum(x['omega_actual_xtc']=='8' for x in after),
                         sum(x['omega_actual_xtc']=='8' for x in before)+(before[0]['omega_actual_xtc']!='8'))
        self.assertEqual(len([s for s in self.store.state()['snapshots'] if s['kind']=='scores']),2)

    def test_wrong_week_track_and_fractional_actual_rejected(self):
        r = dict(self.store.records('scores')[0])
        for changes in ({'week':'2.5'}, {'week':'24'}, {'forecast_track':'UNDECLARED'}, {'omega_actual_xtc':'2.5'}):
            with self.assertRaises(ValueError):
                self.store.import_file('scores','bad-score.csv',text_csv([dict(r,**changes)]))

    def test_archived_forecast_found_when_another_slate_is_active(self):
        f = self.forecast
        other = next(r for r in self.store.records('forecasts') if r['game_id']!=f['game_id'])
        original = self.store.state()['forecast_snapshot']['id']
        self.store.import_file('forecasts','other.csv',text_csv([other]))
        self.assertEqual(len(self.store.records('forecasts')),1)
        found = self.store.find_forecast(f['game_id'],f['player_id'],f['kickoff_utc'])
        self.assertEqual(found['input_snapshot_id'],original)
        self.assertIsNone(self.store.find_forecast(f['game_id'],f['player_id'],'2020-01-01T00:00:00Z'))
        self.store.activate_forecast(original)
        self.assertEqual(len(self.store.records('forecasts')),749)

    def test_quote_comparison_uses_archive_and_records_source_time_limit(self):
        f=self.forecast
        self.store.ingest_quotes([quote(game_id=f['game_id'],player_id=f['player_id'],
            player_name=f['player_name'],captured_at=f['captured_at'],kickoff_utc=f['kickoff_utc'])],'fixture','fixture')
        other=next(r for r in self.store.records('forecasts') if r['game_id']!=f['game_id'])
        self.store.import_file('forecasts','other.csv',text_csv([other]))
        result=self.store.compare_quote(self.store.quote_list()[0]['id'])
        self.assertTrue(result['available'])
        self.assertFalse(result['executable'])
        self.assertEqual(result['provenance'],'SOURCE_REPORTED_CAPTURE_TIME')
        self.assertIn('forecast_received_at',result)

    def outcome(self, **changes):
        f=self.forecast
        observed=(stamp(f['kickoff_utc'])+timedelta(hours=4)).isoformat()
        r={'game_id':f['game_id'],'player_id':f['player_id'],'omega_actual_xtc':'0',
           'sportsbook_like_actual':'','defensive_participant':'Unknown','observed_at':observed,
           'source':'TEST FIXTURE','game_status':'FINAL','target':'combined_standard_def_scrimmage'}
        r.update(changes)
        return r

    def test_final_grading_requires_known_actual_and_preserves_provenance(self):
        r=self.outcome()
        self.store.import_file('outcomes','fixture.csv',text_csv([r]))
        result=grade_observations(self.store)
        self.assertEqual(result['matched_player_games'],1)
        self.assertEqual(len(result['active_forecasts_without_outcomes']),748)
        rows=[x for x in self.store.records('scores') if x['game_id']==r['game_id'] and x['player_id']==r['player_id']]
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x['omega_actual_xtc']=='0' and x['forecast_snapshot_id'] for x in rows))
        self.assertEqual({x['defensive_participant'] for x in rows},{'Unknown'})
        with self.assertRaises(ValueError):
            self.store.import_file('outcomes','missing.csv',text_csv([self.outcome(omega_actual_xtc='')]))

    def test_conflicting_finals_and_wrong_targets_fail_explicitly(self):
        for row in (self.outcome(target='book settlement'),self.outcome(game_status='IN_PROGRESS')):
            with self.assertRaises(ValueError): self.store.import_file('outcomes','bad.csv',text_csv([row]))
        self.store.import_file('outcomes','a.csv',text_csv([self.outcome()]))
        self.store.import_file('outcomes','b.csv',text_csv([self.outcome(omega_actual_xtc='1',source='OTHER FIXTURE')]))
        with self.assertRaisesRegex(ValueError,'Conflicting'): grade_observations(self.store)

    def test_chronological_replay_no_test_labels_enter_fit(self):
        rows=self.store.records('scores')
        result=evaluate(rows)
        fold=result['folds'][0]
        self.assertEqual(fold['training_periods'],[[2026,1]])
        self.assertEqual(fold['training_rows'],246)
        self.assertEqual(fold['baseline']['n'],800)
        self.assertAlmostEqual(fold['challenger']['mae'],1.660,places=3)
        changed=[dict(r,omega_actual_xtc='20') if r['week']=='2' else r for r in rows]
        self.assertEqual(fold['scale'],evaluate(changed)['folds'][0]['scale'])
        self.assertEqual(result['status'],'RESEARCH_ONLY_NO_PROMOTION')
        self.assertEqual(result['cohorts']['matched']['n'],788)
        self.assertIn('Previously inspected',result['limits'][0])

    def test_simulator_neutral_mean_is_preserved_with_sampling_error(self):
        result=simulate(self.store.records('forecasts'),{'game_id':'2026_03_BAL_DAL','team':'BAL',
                        'draws':5000,'seed':9321,'competition':0,'volume_cv':0})
        for player in result['players']:
            # Marginal event thinning is Poisson under neutral assumptions.
            tolerance=5*(max(player['baseline'],.01)/5000)**.5+.015
            self.assertAlmostEqual(player['mean'],player['baseline'],delta=tolerance)
        self.assertTrue(result['team']['max_credit_bound_pass'])

    def test_simulator_rejects_inconsistent_team_opportunities(self):
        rows=[dict(r) for r in self.store.records('forecasts')]
        target=next(r for r in rows if r['game_id']=='2026_03_BAL_DAL' and r['team']=='BAL')
        target['predicted_xto']=str(float(target['predicted_xto'])+1)
        with self.assertRaisesRegex(ValueError,'inconsistent'):
            simulate(rows,{'game_id':'2026_03_BAL_DAL','team':'BAL','draws':200})


class AuditRecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'audit.sqlite3')

    def tearDown(self):
        self.store.db.close();self.tmp.cleanup()

    def ticket(self, **changes):
        data={'ticket_id':'AUDIT','book':'Test Book','selection':'Test only','side':'OVER','line':7.5,
              'odds':-110,'stake':11,'placed_at':'2026-09-27T16:00:00Z'}
        data.update(changes)
        return self.store.add_bet(data)['id']

    def test_reopen_has_no_return_and_corrections_use_current_stake(self):
        bid=self.ticket()
        self.store.settle_bet(bid,{'result':'WIN','source':'fixture'})
        with self.assertRaises(ValueError):self.store.amend_bet(bid,{'stake':22,'odds':-110,'source':'fixture'})
        self.store.settle_bet(bid,{'result':'OPEN','source':'reconcile'})
        self.assertEqual(self.store.bet_list()[0]['payout_cents'],0)
        self.store.amend_bet(bid,{'stake':22,'odds':100,'source':'receipt correction'})
        self.store.settle_bet(bid,{'result':'WIN','source':'correct receipt'})
        b=self.store.bet_list()[0]
        self.assertEqual((b['stake_cents'],b['payout_cents'],b['pnl_cents']),(2200,4400,2200))
        self.assertEqual(len(b['events']),4)

    def test_historical_reference_never_becomes_a_placed_bet_automatically(self):
        self.store.ingest_quotes([quote(source='THE_ODDS_API_HISTORICAL',retrieved_at='2026-09-28T01:00:00Z')],
                                 'fixture','fixture')
        self.assertEqual(self.store.bet_list(),[])
        q=self.store.quote_list()[0]
        self.assertTrue(q['historical_backfill'])
        self.ticket(quote_id=q['id'])
        self.assertEqual(self.store.bet_list()[0]['link_status'],'HISTORICAL_REFERENCE_ONLY')
        with self.assertRaises(ValueError): normalize_quote(quote(retrieved_at='2026-09-26T00:00:00Z'))

    def test_odds_correction_breaks_quote_link_but_keeps_original(self):
        self.store.ingest_quotes([quote()],'fixture','fixture')
        q=self.store.quote_list()[0]
        bid=self.ticket(quote_id=q['id'])
        self.store.amend_bet(bid,{'stake':11,'odds':100,'source':'fixture'})
        self.assertEqual(self.store.bet_list()[0]['link_status'],'CORRECTED_UNLINKED')
        original=json.loads(self.store.db.execute('SELECT payload FROM bets WHERE id=?',(bid,)).fetchone()[0])
        self.assertEqual(original['quote_id'],q['id'])

    def test_backup_restore_roundtrip_and_no_overwrite(self):
        bid=self.ticket()
        self.store.settle_bet(bid,{'result':'CASHOUT','payout':8,'source':'fixture'})
        backup=Path(self.tmp.name)/'backup.sqlite3'
        backup.write_bytes(self.store.database_backup())
        target=Path(self.tmp.name)/'restored'/'omega.sqlite3'
        restore_database(backup,target)
        other=Store(target)
        try:self.assertEqual(other.bet_list(),self.store.bet_list())
        finally:other.db.close()
        with self.assertRaises(ValueError):restore_database(backup,target)

    def test_pre_v1_backup_keeps_existing_tickets(self):
        self.ticket()
        self.store.db.execute('PRAGMA user_version=0');self.store.db.commit()
        upgraded=Store(self.store.path)
        try:self.assertEqual(len(upgraded.bet_list()),1)
        finally:upgraded.db.close()
        backup=self.store.path.with_name('audit.pre-v1.sqlite3')
        self.assertTrue(backup.is_file())
        old=sqlite3.connect(backup)
        try:self.assertEqual(old.execute('SELECT count(*) FROM bets').fetchone()[0],1)
        finally:old.close()

    def test_process_lock_blocks_second_instance(self):
        lock=InstanceLock(Path(self.tmp.name)/'server.lock')
        try:
            with self.assertRaises(ValueError):InstanceLock(Path(self.tmp.name)/'server.lock')
        finally:lock.close()

    def test_jobs_report_success_failure_and_interrupted_restart(self):
        jobs=Jobs(self.store)
        gate=threading.Event()
        first=jobs.start('fixture',lambda:gate.wait(2))
        with self.assertRaises(ValueError):jobs.start('fixture',lambda:None)
        gate.set()
        def broken():raise ValueError('fixture failure')
        failed=jobs.start('broken',broken)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            if all(jobs.get(j['job_id'])['status']!='RUNNING' for j in (first,failed)):break
            time.sleep(.01)
        self.assertEqual(jobs.get(first['job_id'])['status'],'COMPLETE')
        self.assertEqual(jobs.get(failed['job_id'])['status'],'FAILED')
        self.assertIn('fixture failure',jobs.get(failed['job_id'])['result']['error'])
        with self.store.tx() as db:
            db.execute("INSERT INTO jobs VALUES('orphan','fixture','RUNNING','2026-09-27',NULL,'{}')")
        restarted=Jobs(self.store)
        self.assertEqual(restarted.get('orphan')['status'],'INTERRUPTED')

    def test_provider_failure_result_is_not_a_successful_job(self):
        jobs=Jobs(self.store)
        job=jobs.start('provider',lambda:{'status':'FAILED','failed_watches':1})
        deadline=time.monotonic()+2
        while jobs.get(job['job_id'])['status']=='RUNNING' and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(jobs.get(job['job_id'])['status'],'FAILED')

    def test_inbox_bad_csv_does_not_block_valid_file(self):
        import os
        collector=Collector(self.store)
        bad=collector.inbox/'a-bad.csv';good=collector.inbox/'b-good.csv'
        bad.write_text('"unterminated')
        good.write_text(text_csv([quote()]))
        for f in (bad,good):os.utime(f,(time.time()-10,time.time()-10))
        collector.inbox_capture()
        self.assertEqual(len(self.store.quote_list()),1)


class AuditProviderTests(unittest.TestCase):
    def test_search_excludes_closed_markets_and_handles_no_events(self):
        def fetch(base,path,params):
            self.assertEqual(params['events_status'],'active')
            self.assertEqual(params['keep_closed_markets'],0)
            data={'events':[{'markets':[{'closed':True,'clobTokenIds':['1'],'outcomes':['Old']},
                                       {'closed':False,'clobTokenIds':['2'],'outcomes':['Current']}]}]}
            return data,{},canonical(data)
        result,_=discover_markets('NFL',fetch)
        self.assertEqual([m['token_id'] for m in result['markets']],['2'])
        self.assertIsNone(result['markets'][0]['liquidity'])
        result,_=discover_markets('NFL',lambda *a:({'events':None},{},'{}'))
        self.assertEqual(result['markets'],[])

    def test_book_outcome_and_condition_identity_are_enforced(self):
        for asset,condition in [('999','a'),('123','b')]:
            def fetch(base,path,params):
                data={'asset_id':asset,'market':'0x'+condition*64,'bids':[],'asks':[]}
                return data,{},canonical(data)
            with self.assertRaises(ProviderError):monitor_market('123','0x'+'a'*64,fetch)

    def test_wallet_mismatch_and_missing_value_are_not_hidden(self):
        def fetch(base,path,params):
            data={'data':[{'proxy_wallet':'0x'+'b'*40}], 'pagination':{}}
            return data,{},canonical(data)
        with self.assertRaises(ProviderError):monitor_wallet('0x'+'a'*40,fetch)
        def correct(base,path,params):
            data={'data':[{'proxy_wallet':'0x'+'a'*40}], 'pagination':{}}
            return data,{},canonical(data)
        value,_=monitor_wallet('0x'+'a'*40,correct)
        self.assertIsNone(value['sample_position_value'])

    def test_broken_or_repeated_pagination_fails(self):
        def repeated(base,path,params):return {'data':[],'pagination':{'next_cursor':'same'}},{},'{}'
        with self.assertRaises(ProviderError):pages('/v2/trades',{},repeated)
        def missing(base,path,params):return {'data':[],'pagination':{'has_more':True}},{},'{}'
        with self.assertRaises(ProviderError):pages('/v2/trades',{},missing)

    def collector(self):
        temp=tempfile.TemporaryDirectory()
        store=Store(Path(temp.name)/'test.sqlite3')
        collector=Collector(store);collector.key='FIXTURE_NOT_A_KEY'
        return temp,store,collector

    def test_capture_rotation_empty_coverage_and_daily_budget(self):
        temp,store,c=self.collector()
        start=datetime.now(timezone.utc)+timedelta(hours=1)
        events=[{'id':str(i),'commence_time':(start+timedelta(hours=i)).isoformat()} for i in range(3)]
        calls=[]
        def fetch(base,path,params):
            calls.append(path)
            data=events if path.endswith('/events') else {'id':path.split('/')[-2],'commence_time':events[0]['commence_time'],'bookmakers':[]}
            return data,{'x-requests-remaining':'100'},canonical(data)
        store.set_setting('capture',{'max_events':1,'daily_call_cap':5})
        try:
            with patch('app.providers.request_json',fetch):
                first=c.odds_capture();second=c.odds_capture();third=c.odds_capture()
                self.assertEqual(first['missing_due_to_event_cap'],2)
                self.assertEqual(first['events'][0]['status'],'EMPTY')
                self.assertNotEqual(first['events'][0]['event'],second['events'][0]['event'])
                self.assertEqual(third['captured_events'],0)
                self.assertEqual(store.setting('odds_budget')['calls'],5)
                self.assertEqual(len(calls),5)
        finally:store.db.close();temp.cleanup()

    def test_historical_capture_preserves_provider_time_and_marks_recovery(self):
        temp,store,c=self.collector()
        as_of='2026-09-20T12:00:00Z'
        event={'id':'hist','commence_time':'2026-09-20T17:00:00Z','home_team':'Dallas Cowboys','away_team':'Baltimore Ravens'}
        def fetch(base,path,params):
            self.assertTrue(path.startswith('/v4/historical/'))
            self.assertEqual(params['date'],as_of)
            data=[event] if path.endswith('/events') else dict(event,bookmakers=[{'title':'Fixture','markets':[
                {'key':'player_tackles_assists','outcomes':[{'name':'Over','description':'Fixture Player','point':6.5,'price':-110}]}]}])
            envelope={'timestamp':as_of,'data':data}
            return envelope,{},canonical(envelope)
        try:
            with patch('app.providers.request_json',fetch):result=c.odds_capture(as_of)
            q=store.quote_list()[0]
            self.assertTrue(q['historical_backfill'])
            self.assertEqual(q['captured_at'],as_of)
            self.assertGreater(stamp(q['retrieved_at']),stamp(as_of))
            self.assertEqual(store.bet_list(),[])
            self.assertEqual(result['status'],'COMPLETE')
        finally:store.db.close();temp.cleanup()

    def test_failed_capture_preserves_last_success_and_records_failure(self):
        temp,store,c=self.collector()
        store.set_setting('odds_last',{'captured_at':'2026-09-20T12:00:00Z'})
        try:
            with patch('app.providers.request_json',side_effect=ProviderError('HTTP 403 fixture')):
                with self.assertRaises(ProviderError):c.odds_capture()
            self.assertEqual(store.setting('odds_last')['captured_at'],'2026-09-20T12:00:00Z')
            self.assertEqual(store.setting('odds_last_failure')['status'],'FAILED')
            self.assertIsNotNone(store.latest('capture_run'))
        finally:store.db.close();temp.cleanup()

    def test_polymarket_failure_reports_failed_health_without_new_timestamp(self):
        temp,store,c=self.collector()
        store.set_setting('poly_watch',[{'token_id':'123','condition_id':'','label':'Fixture'}])
        store.set_setting('poly_last',{'123':{'captured_at':'2026-09-20T12:00:00Z','best_bid':.4}})
        try:
            with patch('app.providers.monitor_market',side_effect=ProviderError('HTTP 403 fixture')):
                result=c.poly_capture()
            self.assertEqual(result['status'],'FAILED')
            self.assertEqual(result['books']['123']['captured_at'],'2026-09-20T12:00:00Z')
            self.assertIn('failed_at',result['books']['123'])
        finally:store.db.close();temp.cleanup()


if __name__=='__main__':unittest.main()

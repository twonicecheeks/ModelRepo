import copy
import csv
import io
import gzip
import json
import math
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.core import Store, canonical
from app.mlb import MLB, project
from app.mlb_model import (usage_factor,fit_calibration,exposure_ml,postseason_k,
                           k_pmf,k_probabilities,quote_ev,settle)

ROOT=Path(__file__).resolve().parents[1]


class HoldoutTests(unittest.TestCase):
    def test_same_and_future_usage_labels_cannot_change_test_factor(self):
        pairs=json.loads((ROOT/'seed/mlb/USAGE_PAIRS.json').read_text())
        before=usage_factor(pairs,2023)
        for p in pairs:
            if p['season']>=2023:p['outs_ratio']=100000
        self.assertEqual(before,usage_factor(pairs,2023))
        self.assertEqual(max(before['training_seasons']),2022)

    def test_test_moneyline_labels_cannot_enter_calibration(self):
        rows=[json.loads(x) for x in (ROOT/'audit/mlb/PREDICTIONS.jsonl').read_text().splitlines()]
        rows=[r for r in rows if 'exposure_probability' in r]
        before=fit_calibration(rows,2023)
        for r in rows:
            if r['season']>=2023:r['actual_win']=1-r['actual_win'];r['exposure_probability']=.999
        self.assertEqual(before,fit_calibration(rows,2023))
        self.assertEqual(max(before['training_seasons']),2022)

    def test_short_start_has_no_three_and_half_inning_floor(self):
        c={'starterR9':6.,'bullpenR9':3.,'parkFactor':1.,'homeFieldRuns':0.}
        b={'awayRunComponents':c,'homeRunComponents':c}
        w={s:{'IP':1.,'state':'MANAGER_PLAN'} for s in ['away','home']}
        p=exposure_ml(b,w,.8)
        self.assertEqual(p['starter_ip'],{'away':1.,'home':1.})
        self.assertAlmostEqual(p['away_runs'],10/3)

    def test_market_anchored_workload_is_not_adjusted_twice(self):
        row=json.loads((ROOT/'seed/mlb/BASELINE_LEDGER.jsonl').read_text().splitlines()[1])
        a=postseason_k(row['k_projection'],.8,'CURRENT_GAME_MARKET_ANCHORED')
        b=postseason_k(row['k_projection'],1.,'CURRENT_GAME_MARKET_ANCHORED')
        self.assertEqual(a,b);self.assertFalse(a['usage_factor_applied'])
        c=row['k_projection']['components']
        self.assertAlmostEqual(a['expected_outs'],c['expectedOuts'])

    def test_integer_push_and_probability_mass_are_consistent(self):
        p=k_probabilities(5.2,5,1.3)
        self.assertAlmostEqual(sum(p.values()),1.,places=12)
        self.assertGreater(p['push'],0)
        self.assertEqual(k_probabilities(5.2,5.5)['push'],0)
        self.assertAlmostEqual(sum(k_pmf(5.2)),1.,places=12)
        self.assertAlmostEqual(quote_ev(p['over'],p['push'],-110),p['over']*(100/110)-p['under'])
        self.assertEqual(settle('OVER',5,5,-110),0)
        self.assertAlmostEqual(settle('UNDER',4,5,-110),100/110)
        self.assertEqual(settle('UNDER',6,5,-110),-1)

    def test_report_never_promotes_missing_market_evidence(self):
        r=json.loads((ROOT/'audit/mlb/BACKTEST_REPORT.json').read_text())
        self.assertEqual(r['status'],'EDGE_NOT_VERIFIED')
        self.assertEqual(r['coverage']['projected_games'],426)
        self.assertEqual(r['coverage']['paired_k_rows'],775)
        self.assertIsNone(r['market_evidence']['roi'])
        self.assertFalse(r['verification_gates']['authentic_timestamped_entry_prices'])
        self.assertGreater(r['moneyline_calibrated']['challenger']['brier'],r['moneyline_calibrated']['baseline']['brier'])


@unittest.skipUnless(shutil.which('node'),'Node required for recovered structured engines')
class InferenceTests(unittest.TestCase):
    def test_live_input_assembly_matches_real_replay_and_blocks_started_games(self):
        with gzip.open(ROOT/'tests/fixtures/mlb_live_2025.json.gz','rt') as f:payload=json.load(f)
        def build(x):
            p=subprocess.run(['node',str(ROOT/'tools/build_mlb_live.cjs')],input=canonical(x),text=True,capture_output=True,check=True,timeout=60)
            return json.loads(p.stdout)
        assembled=build(payload)[0]
        self.assertEqual(assembled['status'],'READY_RESEARCH')
        p=subprocess.run(['node',str(ROOT/'tools/mlb_project.cjs')],input=canonical(assembled['inputs']),text=True,capture_output=True,check=True,timeout=45)
        results=json.loads(p.stdout)
        baseline=[json.loads(x) for x in (ROOT/'seed/mlb/BASELINE_LEDGER.jsonl').read_text().splitlines() if json.loads(x)['game_id']==assembled['game_id']]
        for a,b in zip(baseline,results):
            if a['market_type']=='ML':self.assertAlmostEqual(a['model_probability'],b['base']['homeWin'],places=12)
            else:self.assertAlmostEqual(a['xk'],b['base']['expectedK'],places=12)
        payload['games'][0]['abstract_state']='F'
        self.assertEqual(build(payload)[0]['status'],'BLOCKED')

    def test_outcomes_and_target_k_lines_do_not_change_forecast(self):
        inputs=[json.loads(x) for x in (ROOT/'seed/mlb/REPRODUCTION_INPUTS.jsonl').read_text().splitlines()[:3]]
        frozen=json.loads((ROOT/'audit/mlb/FROZEN_MODEL.json').read_text())
        m=inputs[0]['production_input'];workloads={s:dict(m['starters'][m[s]]['workload'],regular_starts=True) for s in ['away','home']}
        before=project(inputs,workloads,frozen)
        for r in inputs:
            r['actual_k']=999;r['actual_home_win']=1;r['market_odds']=9999;r['closing_odds']=-9999
            if r['replay_type']=='K':
                r['starter_input']['markets']['player-strikeouts']['representative']={'line':40.5,'overOdds':9000,'underOdds':-9000}
        after=project(inputs,workloads,frozen)
        self.assertEqual(before,after)


class QuoteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db.sqlite3')
        self.mlb=MLB(self.store)
        clock=datetime.now(timezone.utc)
        self.captured=(clock-timedelta(minutes=2)).isoformat()
        self.start=(clock+timedelta(hours=1)).isoformat()
        self.game={'game_id':'999001','start_at':self.start,'away':'ATL','home':'LAD','status':'READY_RESEARCH','snapshot_id':'TEST_ONLY',
            'captured_at':(clock-timedelta(minutes=3)).isoformat(),'forecast':{'moneyline':{'calibrated_home_probability':.57,'baseline_home_probability':.55},
            'starters':[{'player_id':'123','expected_k':5.2,'baseline_k':5.7,'uncertainty_multiplier':1.}]}}
        self.store.set_setting('mlb_board',{'games':[self.game]})

    def tearDown(self):self.store.db.close();self.temp.cleanup()

    def raw(self,**changes):
        r={'game_id':'999001','market_type':'K','player_id':'123','side':'OVER','line':5,'odds':-110,'book':'TEST ONLY','captured_at':self.captured,'source':'TEST FIXTURE','settlement_definition':'FULL_GAME'}
        r.update(changes);b=io.StringIO();w=csv.DictWriter(b,r.keys());w.writeheader();w.writerow(r);return b.getvalue()

    def test_quote_identity_and_timing_are_atomic(self):
        before_forecast=(datetime.now(timezone.utc)-timedelta(minutes=4)).isoformat()
        for raw in [self.raw(player_id='999'),self.raw(captured_at=self.start),self.raw(captured_at=before_forecast),self.raw(settlement_definition='FIRST_FIVE'),self.raw(book='')]:
            with self.assertRaises(ValueError):self.mlb.import_quotes(raw)
        self.assertEqual(self.store.setting('mlb_quotes',[]),[])
        self.assertIsNone(self.store.latest('mlb_quotes'))
        self.assertEqual(self.mlb.import_quotes(self.raw())['rows'],1)
        quote=self.store.setting('mlb_quotes')[0]
        self.assertFalse(quote['entry_receipt_verified'])
        self.assertEqual(quote['status'],'RESEARCH_ONLY')
        self.assertGreater(quote['push_probability'],0)

    def test_saved_board_stops_being_pregame_at_first_pitch(self):
        self.game['start_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        self.store.set_setting('mlb_board',{'games':[self.game]})
        self.assertEqual(self.mlb.state()['board']['games'][0]['display_status'],'STARTED')

    def test_failed_collection_preserves_last_success(self):
        before=self.store.setting('mlb_board')
        with patch.object(self.mlb,'refresh',side_effect=ValueError('offline')):
            with self.assertRaises(ValueError):self.mlb.operation('refresh')
        self.assertEqual(self.store.setting('mlb_board'),before)
        self.assertEqual(self.store.setting('mlb_last_failure')['error'],'offline')

    def test_scratched_pitcher_is_not_graded_as_actual_starter(self):
        self.mlb.import_quotes(self.raw())
        def get(path,**kwargs):
            if path.endswith('linescore'):return {'teams':{'home':{'runs':3},'away':{'runs':2}}}
            if path.endswith('boxscore'):return {'teams':{'home':{'players':{'ID456':{'person':{'id':456},'stats':{'pitching':{'gamesStarted':1,'strikeOuts':8}}}}},'away':{'players':{}}}}
            return {'dates':[{'games':[{'status':{'abstractGameCode':'F'},'teams':{'home':{'team':{'id':119}}}}]}]}
        with patch.object(self.mlb,'get',side_effect=get):self.assertEqual(self.mlb.grade()['graded_quotes'],0)

    def test_mlb_endpoints_preserve_existing_app_state(self):
        from server import make_server
        server,collector=make_server(self.store,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            state=json.load(urllib.request.urlopen(base+'/api/state'))
            self.assertEqual(state['version'],'2.1.3-delta.0.1.0');self.assertIn('forecasts',state)
            self.assertIn('delta',state['mlb']);self.assertEqual(state['mlb']['delta']['model_version'],'delta-0.1.0')
            self.assertEqual(state['mlb']['report']['status'],'EDGE_NOT_VERIFIED')
            report=json.load(urllib.request.urlopen(base+'/api/mlb/report'))
            self.assertEqual(report['coverage']['paired_k_rows'],775)
            request=urllib.request.Request(base+'/api/mlb/quotes',data=canonical({'raw':self.raw()}).encode(),headers={'Content-Type':'application/json','X-Omega-Token':state['csrf']})
            self.assertEqual(json.load(urllib.request.urlopen(request))['rows'],1)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()

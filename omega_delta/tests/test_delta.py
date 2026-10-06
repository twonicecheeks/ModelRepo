"""Analytical and evidence-boundary checks for DELTA's new probability math."""
import copy
import io
import csv
import json
import math
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.core import Store, canonical
from app.delta import Delta, model_files, params_for, project_delta
from app.delta_model import (hitter_rates, forecast, count_distributions, beta_binomial,
                             summarize, at_line, workload_pmf, fit_parameters,
                             count_k_probability, draw_count, simulate)
from app.mlb import MLB

ROOT=Path(__file__).resolve().parents[1]


def input_row():
    return json.loads((ROOT/'seed/mlb/REPRODUCTION_INPUTS.jsonl').read_text().splitlines()[1])


def count_table(**events):
    cell={k:events.get(k,0.) for k in ['ball','called_strike','whiff','foul','in_play']}
    return {f'{b}-{s}':dict(cell) for b in range(4) for s in range(3)}


class MathTests(unittest.TestCase):
    def test_homogeneous_pa_matches_analytical_binomial(self):
        rates=[{'k_probability':.3}]*9
        p=count_distributions(rates,{20:1.})['pa']
        for k in range(21): self.assertAlmostEqual(p[k],math.comb(20,k)*.3**k*.7**(20-k),places=12)
        self.assertAlmostEqual(summarize(p)['variance'],4.2)

    def test_heterogeneous_hitters_and_bf_mixture(self):
        rates=[{'k_probability':p} for p in [.1,.8]+[.2]*7]
        p=count_distributions(rates,{0:.5,2:.5})['pa']
        self.assertAlmostEqual(p[2],.04)
        self.assertAlmostEqual(p[0],.59)
        self.assertAlmostEqual(sum(p),1.)
        self.assertAlmostEqual(summarize(p)['expected_k'],.45)
        self.assertEqual(len(p),3)

    def test_beta_binomial_variance_is_not_underdispersion(self):
        p=beta_binomial(20,.3,100)
        self.assertAlmostEqual(sum(p),1.)
        self.assertAlmostEqual(summarize(p)['expected_k'],6.)
        self.assertAlmostEqual(summarize(p)['variance'],20*.3*.7*(20+100)/(100+1),places=10)
        self.assertGreater(summarize(p)['variance'],4.2)

    def test_workload_mean_is_preserved_and_no_18_bf_ceiling(self):
        p=workload_pmf(24,{'bf_residuals':[.5,1,1.5]})
        self.assertAlmostEqual(sum(n*v for n,v in p.items()),24.)
        self.assertGreater(sum(v for n,v in p.items() if n>27),0)
        anchored=workload_pmf(24,{}, {'bf_pmf':[{'bf':8,'probability':1}]})
        self.assertEqual(anchored,{8:1.})

    def test_integer_push_and_half_line_partition(self):
        p=[.1,.2,.3,.4]
        whole=at_line(p,2);half=at_line(p,2.5)
        self.assertEqual(whole['push'],.3);self.assertEqual(half['push'],0)
        self.assertAlmostEqual(sum(whole.values()),1)
        self.assertAlmostEqual(whole['over'],half['over'])
        with self.assertRaises(ValueError):at_line(p,2.2)

    def test_pitch_count_absorption_and_two_strike_fouls(self):
        self.assertEqual(count_k_probability(count_table(whiff=1)),1.)
        self.assertEqual(count_k_probability(count_table(ball=1)),0.)
        self.assertEqual(draw_count(count_table(whiff=1),random.Random(1)),('K',3))
        self.assertEqual(draw_count(count_table(ball=1),random.Random(1)),('WALK',4))
        with self.assertRaises(ValueError):count_k_probability(count_table(foul=1))
        table=count_table(whiff=.2,called_strike=.1,ball=.3,foul=.2,in_play=.2)
        expected=count_k_probability(table)
        rng=random.Random(123)
        observed=sum(draw_count(table,rng,True)[0]=='K' for _ in range(10000))/10000
        self.assertLess(abs(observed-expected),5*math.sqrt(expected*(1-expected)/10000))

    def test_reverse_splits_and_switch_hitter_hand(self):
        row=input_row();pid=str(row['lineup_rows'][0]['mlbId'])
        profile={'pitcher':{'hand':'R','splits':{'L':{'K':45,'pa':500},'R':{'K':15,'pa':500}}},'hitters':{pid:{'hand':'L'}}}
        left=hitter_rates(row,{},profile)[0]
        profile['hitters'][pid]['hand']='R';right=hitter_rates(row,{},profile)[0]
        self.assertGreater(left['k_probability'],right['k_probability'])
        profile['hitters'][pid]['hand']='S'
        self.assertAlmostEqual(hitter_rates(row,{},profile)[0]['k_probability'],left['k_probability'])

    def test_arsenal_features_require_complete_measured_inputs(self):
        row=input_row();pid=str(row['lineup_rows'][0]['mlbId'])
        profile={'pitcher':{'arsenal':[{'pitch_type':'FF','usage':.4},{'pitch_type':'SL','usage':.6}]},
                 'hitters':{pid:{'pitch_types':{'FF':{'whiff_pct':20},'SL':{'whiff_pct':40}}}}}
        self.assertAlmostEqual(hitter_rates(row,{},profile)[0]['features']['arsenal_whiff_pct'],32)
        profile['feature_model']={'coefficients':{'stuff_plus':.1}}
        with self.assertRaises(ValueError):hitter_rates(row,{},profile)

    def test_future_targets_cannot_enter_parameter_fit(self):
        row=input_row()
        data=[{'input':row,'v2':{'expected_bf':20},'actual_bf':20,'actual_k':5,'season':2024},
              {'input':row,'v2':{'expected_bf':20},'actual_bf':20,'actual_k':5,'season':2025}]
        before=fit_parameters(data,2025)
        data[1].update(actual_bf=100,actual_k=99)
        self.assertEqual(before,fit_parameters(data,2025))
        self.assertEqual(before['training_seasons'],[2024])

    def test_market_and_current_outcome_are_not_forecast_inputs(self):
        row=input_row();v2={'expected_bf':22}
        before=forecast(row,v2,{})
        row.update(actual_k=999,actual_bf=99,market_odds=10000,closing_odds=-10000)
        row['starter_input']['markets']['player-strikeouts']['representative']={'line':.5,'overOdds':-9999}
        self.assertEqual(before,forecast(row,v2,{}))

    def test_monte_carlo_reproducible_and_matches_analytic_mean(self):
        row=input_row();v2={'expected_bf':20}
        a=simulate(row,v2,{},draws=10000,seed=55)
        self.assertEqual(a,simulate(row,v2,{},draws=10000,seed=55))
        exact=forecast(row,v2,{})['pa']['expected_k']
        self.assertLess(abs(a['distribution']['expected_k']-exact),5*a['expected_k_mc_se'])
        with self.assertRaises(ValueError):simulate(row,v2,{},draws=1000.5)

    def test_hook_requires_count_inputs_and_replaces_bf_mixture(self):
        row=input_row();v2={'expected_bf':25}
        profile={'hook_model':{'intercept':-35,'coefficients':{},'max_bf':1,'max_pitches':100},
                 'contact_outcomes':{'OUT':1,'1B':0,'2B':0,'3B':0,'HR':0}}
        with self.assertRaises(ValueError):simulate(row,v2,{},profile,draws=1000)
        profile['hitters']={str(b['mlbId']):{'count_probabilities':count_table(whiff=1)} for b in row['lineup_rows']}
        a=simulate(row,v2,{},profile,draws=1000)
        self.assertEqual(a['expected_bf'],1.)
        self.assertEqual(a['distribution']['expected_k'],1.)
        self.assertEqual(a['mode'],'SIMPLIFIED_DYNAMIC_HOOK_SCENARIO')

    def test_blank_skill_is_not_zero_and_duplicate_identity_rejected(self):
        row=input_row();row['pitcher_row']['K']=''
        with self.assertRaises(ValueError):forecast(row,{'expected_bf':22},{})
        row=input_row();row['lineup_rows'][1]['mlbId']=row['lineup_rows'][0]['mlbId']
        with self.assertRaises(ValueError):forecast(row,{'expected_bf':22},{})


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.mlb=MLB(self.store);self.delta=self.mlb.delta

    def tearDown(self):self.store.db.close();self.tmp.cleanup()

    def test_profile_import_is_atomic_and_never_rewrites_forecast(self):
        clock=datetime.now(timezone.utc)
        profile={'game_id':'12345','player_id':'67890','observed_at':(clock-timedelta(minutes=1)).isoformat(),
                 'start_at':(clock+timedelta(hours=1)).isoformat(),'source':'TEST FIXTURE ONLY',
                 'pitcher':{'hand':'R'},'hitters':{}}
        bad=copy.deepcopy(profile);bad['observed_at']=bad['start_at']
        with self.assertRaises(ValueError):self.delta.import_profiles(canonical({'profiles':[profile,bad]}))
        self.assertIsNone(self.store.latest('delta_profiles'))
        self.assertEqual(self.store.setting('delta_profiles',{}),{})
        self.store.set_setting('mlb_board',{'games':[{'game_id':'12345','forecast':{'TEST':'ORIGINAL'}}]})
        before=self.store.setting('mlb_board')
        self.assertEqual(self.delta.import_profiles(canonical({'profiles':[profile]}))['profiles'],1)
        self.assertEqual(self.store.setting('mlb_board'),before)

    def test_historical_folds_never_use_current_year_parameters(self):
        row=input_row();f=model_files();p=params_for(row,f)
        self.assertEqual(p['training_seasons'],[])
        row['season']=2025
        self.assertLess(max(params_for(row,f)['training_seasons']),2025)

    def test_delta_quote_uses_saved_pmf_and_integer_push(self):
        clock=datetime.now(timezone.utc)
        game={'game_id':'12345','start_at':(clock+timedelta(hours=1)).isoformat(),'away':'SD','home':'MIL',
              'captured_at':(clock-timedelta(minutes=3)).isoformat(),'snapshot_id':'TEST_ONLY',
              'forecast':{'starters':[{'player_id':'123','expected_k':2,'baseline_k':2,'uncertainty_multiplier':1}],
                          'delta':[{'player_id':'123','model_version':'TEST_ONLY','pa':{'pmf':[.1,.2,.3,.4]}}]}}
        self.store.set_setting('mlb_board',{'games':[game]})
        row={'game_id':'12345','market_type':'K','player_id':'123','side':'OVER','line':2,'odds':-110,
             'book':'TEST ONLY','captured_at':(clock-timedelta(minutes=1)).isoformat(),'source':'TEST ONLY','settlement_definition':'FULL_GAME'}
        buff=io.StringIO();w=csv.DictWriter(buff,row);w.writeheader();w.writerow(row)
        self.mlb.import_quotes(buff.getvalue());q=self.store.setting('mlb_quotes')[0]
        self.assertAlmostEqual(q['delta_probability'],.4);self.assertAlmostEqual(q['delta_push_probability'],.3)
        self.assertAlmostEqual(q['delta_ev'],.4*100/110-.3)
        self.assertFalse(q['entry_receipt_verified'])

    def test_grading_rejects_late_local_receipts_and_does_not_invent_zero(self):
        clock=datetime.now(timezone.utc);row=input_row();d=project_delta(row,{'expected_bf':20},model_files())
        game={'game_id':row['game_id'],'start_at':(clock-timedelta(hours=1)).isoformat(),
              'captured_at':(clock-timedelta(hours=2)).isoformat(),'forecast':{'delta':[d]}}
        sid=self.store.snapshot('mlb_forecast','TEST ONLY',canonical({'game':game}))
        with patch.object(self.mlb,'get') as get:
            self.assertEqual(self.delta.grade(self.mlb)['graded_starts'],0);get.assert_not_called()
        with patch('app.core.now',return_value=game['captured_at']):
            self.store.snapshot('mlb_forecast','TEST PRESTART RECEIPT',canonical({'game':game,'fixture':'received_pregame'}))
        def get(path,**kw):
            if path.endswith('boxscore'):return {'teams':{'away':{'players':{'X':{'person':{'id':int(d['player_id'])},'stats':{'pitching':{'gamesStarted':1}}}}},'home':{'players':{}}}}
            return {'dates':[{'games':[{'status':{'abstractGameCode':'F'}}]}]}
        with patch.object(self.mlb,'get',side_effect=get):
            result=self.delta.grade(self.mlb)
        self.assertEqual(result['graded_starts'],0);self.assertEqual(result['pending'],1)

    def test_report_exposes_failed_improvement_and_missing_advanced_replay(self):
        r=self.delta.report
        self.assertEqual(r['coverage']['paired_starts'],775)
        self.assertGreater(r['models']['delta_pa']['mae'],r['models']['v2']['mae'])
        self.assertEqual(r['advanced_feature_validation'],'NOT_RUN_MISSING_HISTORICAL_INPUTS')
        self.assertIsNone(r['market_evidence']['roi']);self.assertFalse(r['market_evidence']['edge_verified'])


if __name__=='__main__':unittest.main()

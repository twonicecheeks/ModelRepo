"""Test research math, cutoff guards and the future-only audit boundary."""
import csv
import io
import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core import Store, canonical
from app.delta import model_files, project_delta
from app.delta_research import (platoon_posterior, arsenal_whiff,
                                four_seam_trend, hook_probability,
                                conditional_k_matrix, research_matchups)
from tools.train_delta_research import train
from tools.delta_prospective import freeze, audit

ROOT=Path(__file__).resolve().parents[1]


class ResearchMath(unittest.TestCase):
    def test_missing_hand_sample_is_estimated_and_small_sample_is_shrunk(self):
        missing=platoon_posterior(.25,.22,.24)
        self.assertEqual(missing['status'],'ESTIMATED_LEAGUE_HAND_PRIOR')
        self.assertAlmostEqual(missing['projected_k_rate'],missing['prior_k_rate'])
        self.assertGreater(missing['projected_k_rate'],.25)
        observed=platoon_posterior(.25,.22,.24,4,4,120)
        self.assertEqual(observed['status'],'SHRUNK_OBSERVED')
        self.assertLess(observed['projected_k_rate'],.30)
        with self.assertRaises(ValueError): platoon_posterior(.25,.22,.24,4,5)

    def test_arsenal_denominators_and_final_two_confirmed_starts(self):
        arsenal=[{'pitch_type':'FF','usage':.6},{'pitch_type':'SL','usage':.4}]
        a=arsenal_whiff(arsenal,{'FF':{'swings':5,'whiffs':5}}, {'FF':.20,'SL':.35})
        self.assertEqual(a['pitch_types'][1]['status'],'ESTIMATED_LEAGUE_TYPE_PRIOR')
        self.assertLess(a['pitch_types'][0]['projected_whiff_per_swing'],.30)
        pitches=[{'game_date':f'2025-09-{i:02d}','game_pk':str(i),'game_type':'R',
                  'pitch_type':'FF','velocity_mph':94+(i>=3)} for i in (1,2,3,4) for _ in range(10)]
        self.assertEqual(four_seam_trend(pitches)['status'],'MISSING_CONFIRMED_START_IDENTITIES')
        v=four_seam_trend(pitches,{'1','2','3','4'})
        self.assertEqual(v['recent_game_ids'],['3','4'])
        self.assertAlmostEqual(v['change_mph'],1.)

    def test_conditional_matrix_conserves_mass_and_moves_with_run_hazard(self):
        rows=[[{'probability':.5,'k':1,'pitches':3,'runs_allowed':0,'leverage_after':1},
               {'probability':.5,'k':0,'pitches':6,'runs_allowed':2,'leverage_after':1}] for _ in range(9)]
        base={'intercept':-3.,'coefficients':{'runs_allowed':0}}
        quick={'intercept':-3.,'coefficients':{'runs_allowed':3}}
        self.assertGreater(hook_probability(quick,{'runs_allowed':2}),hook_probability(quick,{'runs_allowed':0}))
        a=conditional_k_matrix(rows,base,4)
        b=conditional_k_matrix(rows,quick,4)
        self.assertAlmostEqual(sum(a['k_pmf']),1)
        self.assertAlmostEqual(sum(b['bf_pmf']),1)
        self.assertLess(b['expected_bf'],a['expected_bf'])
        self.assertGreater(a['bf_pmf'][4],0)

    def test_research_matchup_requires_prior_vintage(self):
        now=datetime.now(timezone.utc)
        profile={'player_id':'99','observed_at':now.isoformat(),
                 'pitcher':{'hand':'R','splits':{}},
                 'hitters':{str(i):{'hand':'L','splits':{}} for i in range(1,10)}}
        priors={'source':'TEST HISTORICAL SOURCE','training_end_at':(now-timedelta(days=1)).isoformat(),
                'league_k':.22,'batter_k_by_pitcher_hand':{'R':.24},
                'pitcher_k_by_batter_hand':{'L':.23},'hitter_prior_pa':120,
                'pitcher_prior_pa':180,
                'player_overall_k':{'99':.3,**{str(i):.2 for i in range(1,10)}}}
        a=research_matchups(profile,priors,[str(i) for i in range(1,10)])
        self.assertEqual(len(a['lineup']),9)
        self.assertEqual(a['lineup'][0]['batter_split']['status'],'ESTIMATED_LEAGUE_HAND_PRIOR')
        priors['training_end_at']=(now+timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError):research_matchups(profile,priors,[str(i) for i in range(1,10)])


class ResearchFitting(unittest.TestCase):
    def make_csv(self,task,season=2025):
        file=io.StringIO();cols=['season','game_pk','game_start_at','state_at','pa_index','censored','target',
                                  'bf','pitch_count','runs_allowed','strikeouts','leverage']
        if task=='residual':cols+=['baseline_logit','feature_observed_at','velocity_change']
        writer=csv.DictWriter(file,fieldnames=cols);writer.writeheader()
        for game in range(6):
            for bf in range(1,11):
                row={'season':season,'game_pk':str(100+game),
                     'game_start_at':f'{season}-09-01T18:00:00Z',
                     'state_at':f'{season}-09-01T20:00:00Z','pa_index':bf,
                     'censored':0,'target':int(bf==10) if task=='hook' else int((bf+game)%3==0),
                     'bf':bf,'pitch_count':bf*4,'runs_allowed':bf//4,
                     'strikeouts':bf//3,'leverage':1.}
                if task=='residual': row.update(baseline_logit=-1,feature_observed_at=f'{season}-08-31T12:00:00Z',velocity_change=(bf%3)-1)
                writer.writerow(row)
        return file.getvalue()

    def test_train_prior_year_hazard_and_residual_but_reject_2026_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'risk.csv';p.write_text(self.make_csv('hook'))
            model=train('hook',str(p),['bf','pitch_count','runs_allowed','leverage'],
                        '2026-01-01T00:00:00Z',.1,'TEST FIXTURE')
            self.assertEqual(model['events'],6)
            self.assertEqual(model['kind'],'discrete_end_pa_hook')
            self.assertGreater(hook_probability(model,{'bf':10,'pitch_count':40,'runs_allowed':2,'leverage':1}),
                               hook_probability(model,{'bf':1,'pitch_count':4,'runs_allowed':0,'leverage':1}))
            p.write_text(self.make_csv('residual'))
            residual=train('residual',str(p),['velocity_change'],
                           '2026-01-01T00:00:00Z',.1,'TEST FIXTURE')
            self.assertEqual(residual['kind'],'pa_logit_residual')
            p.write_text(self.make_csv('hook',2026))
            with self.assertRaises(ValueError):train('hook',str(p),['bf','pitch_count','runs_allowed'],
                                               '2026-10-01T00:00:00Z',.1,'TEST FIXTURE')


class FutureOnlyAudit(unittest.TestCase):
    def test_freeze_excludes_older_forecasts_and_reads_one_future_snapshot(self):
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);protocol=folder/'freeze.json'
            locked=freeze(protocol,now-timedelta(hours=1))
            with self.assertRaises(ValueError):freeze(protocol,now)
            db=Store(folder/'omega.sqlite3')
            row=json.loads((ROOT/'seed/mlb/REPRODUCTION_INPUTS.jsonl').read_text().splitlines()[1])
            row['season']=2026
            model=project_delta(row,{'expected_bf':20},model_files())
            game={'game_id':row['game_id'],'start_at':(now+timedelta(days=1)).isoformat(),
                  'captured_at':(now-timedelta(minutes=2)).isoformat(),
                  'forecast':{'delta':[model]}}
            db.snapshot('mlb_forecast','TEST FUTURE',canonical({'game':game}))
            old=dict(game,start_at=(now-timedelta(hours=2)).isoformat())
            db.snapshot('mlb_forecast','TEST PAST',canonical({'game':old}))
            report=audit(protocol,folder/'omega.sqlite3')
            self.assertEqual(report['eligible_forecasts'],1)
            self.assertEqual(report['graded_forecasts'],0)
            self.assertEqual(report['entries'][0]['forecast_k'],model['pa']['expected_k'])
            self.assertEqual(locked['parameter_sha256'],model['parameters_sha256'])
            db.db.close()


if __name__=='__main__':unittest.main()

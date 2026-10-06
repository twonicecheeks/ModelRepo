"""Public-source import: chronological cutoff, provenance, identities and units."""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.core import Store
from app.delta import Delta
from tools.delta_sources import prepare, export_statcast, export_players, sha256, outcome


PITCH_FIELDS = ['game_date', 'game_pk', 'pitcher', 'batter', 'at_bat_number',
                'pitch_number', 'balls', 'strikes', 'description', 'events', 'stand',
                'p_throws', 'pitch_type', 'release_speed', 'release_spin_rate',
                'pfx_x', 'pfx_z', 'release_pos_z', 'release_extension', 'zone']
PBP_FIELDS = ['game_pk', 'game_date', 'isPitch', 'type', 'startTime',
              'matchup.pitcher.id', 'matchup.batter.id', 'about.atBatIndex',
              'index', 'count.outs.start', 'count.balls.start', 'count.strikes.start',
              'details.homeScore', 'details.awayScore', 'pre_on_1b', 'pre_on_2b',
              'pre_on_3b', 'result.eventType', 'isSubstitution']


def write_csv(path, columns, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class DeltaSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.today = datetime.now(timezone.utc).date()
        self.old = (self.today - timedelta(days=2)).isoformat()
        self.lineup = [str(n) for n in range(201, 210)]
        def pitch(ab, pn, batter, stand, throws, desc, event='', game='900001', date=None, pitcher='101', pt='FF'):
            return {'game_date': date or self.old, 'game_pk': game,
                    'pitcher': pitcher, 'batter': batter, 'at_bat_number': ab,
                    'pitch_number': pn, 'balls': 0, 'strikes': min(pn-1,2),
                    'description': desc, 'events': event, 'stand': stand,
                    'p_throws': throws, 'pitch_type': pt, 'release_speed': '95',
                    'release_spin_rate': '2300', 'pfx_x': '-0.5', 'pfx_z': '1.2',
                    'release_pos_z': '6', 'release_extension': '6.3', 'zone': '11'}
        self.pitches = [
            pitch(1, 1, '201', 'L', 'R', 'swinging_strike'),
            pitch(1, 2, '201', 'L', 'R', 'called_strike'),
            pitch(1, 3, '201', 'L', 'R', 'swinging_strike', 'strikeout'),
            pitch(2, 1, '202', 'R', 'R', 'hit_into_play', 'single', pt='SL'),
            pitch(3, 1, '201', 'R', 'L', 'hit_into_play', 'single', pitcher='999'),
            pitch(4, 1, '203', 'L', 'R', 'swinging_strike', 'strikeout', date=self.today.isoformat()),
        ]
        self.csv = self.root/'savant.csv'
        write_csv(self.csv, PITCH_FIELDS, self.pitches)

    def args(self, out='result', pbp=(), statcast=None):
        return argparse.Namespace(
            statcast=statcast if statcast is not None else [str(self.csv)], pbp=list(pbp), game_id='999001',
            pitcher_id='101', lineup=','.join(self.lineup),
            start_at=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),
            observed_at=None, out=str(self.root/out))

    def test_profile_has_exact_splits_units_cutoff_and_provenance(self):
        pbp = self.root/'pbp.csv'
        write_csv(pbp, PBP_FIELDS, [
            {'game_pk':'900001','game_date':self.old,'isPitch':'TRUE','type':'pitch',
             'startTime':self.old+'T19:00:00Z','matchup.pitcher.id':'101',
             'matchup.batter.id':'201','about.atBatIndex':1,'index':0,
             'count.outs.start':0,'details.homeScore':0,'details.awayScore':0},
            {'game_pk':'900002','game_date':self.today.isoformat(),'isPitch':'TRUE',
             'type':'pitch','startTime':self.today.isoformat()+'T19:00:00Z',
             'matchup.pitcher.id':'101','matchup.batter.id':'201',
             'about.atBatIndex':1,'index':0}])
        result=prepare(self.args(pbp=[str(pbp)]))
        out=Path(result['output'])
        profile=json.loads((out/'DELTA_PROFILE.json').read_text())['profiles'][0]
        audit=json.loads((out/'COVERAGE.json').read_text())
        pitches=[json.loads(s) for s in (out/'PITCH_EVENTS.jsonl').read_text().splitlines()]
        pbp_rows=[json.loads(s) for s in (out/'PBP_EVENTS.jsonl').read_text().splitlines()]
        self.assertEqual(len(pitches),5)
        self.assertEqual(audit['statcast']['cutoff_excluded'],1)
        self.assertEqual(audit['baseballr']['cutoff_excluded'],1)
        self.assertEqual(len(pbp_rows),1)
        self.assertEqual(audit['sources'][0]['sha256'],sha256(self.csv))
        self.assertEqual(profile['pitcher']['hand'],'R')
        self.assertEqual(profile['pitcher']['splits']['L'],{'pa':1,'K':100.})
        self.assertEqual(profile['pitcher']['splits']['R'],{'pa':1,'K':0.})
        self.assertEqual(profile['hitters']['201']['hand'],'S')
        self.assertIsNone(profile['hitters']['202']['hand'])
        self.assertEqual(profile['hitters']['201']['splits']['L']['K'],0.)
        self.assertEqual(profile['hitters']['201']['splits']['R']['K'],100.)
        self.assertEqual(len(profile['hitters']),9)
        self.assertEqual(profile['pitcher']['arsenal'][0]['horizontal_break'],-6.)
        self.assertEqual(profile['pitcher']['arsenal'][0]['vertical_break'],14.4)
        self.assertEqual(profile['pitcher']['arsenal'][0]['spin_rate'],2300.)
        self.assertAlmostEqual(sum(x['usage'] for x in profile['pitcher']['arsenal']),1.)
        self.assertNotIn('count_probabilities',profile['hitters']['201'])
        self.assertNotIn('feature_model',profile)
        self.assertNotIn('hook_model',profile)
        self.assertFalse(audit['validated_pitch_count_model'])
        store=Store(self.root/'omega.sqlite3')
        imported=Delta(store).import_profiles((out/'DELTA_PROFILE.json').read_text())
        self.assertEqual(imported['profiles'],1)
        self.assertEqual(imported['status'],'IMPORTED_UNVERIFIED')

    def test_optional_priors_create_labeled_research_without_fitted_effect(self):
        priors=self.root/'priors.json'
        priors.write_text(json.dumps({'source':'TEST HISTORICAL LEAGUE TABLE',
            'training_end_at':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),
            'league_k':.22,'batter_k_by_pitcher_hand':{'R':.23,'L':.21},
            'pitcher_k_by_batter_hand':{'R':.22,'L':.24},
            'hitter_prior_pa':120,'pitcher_prior_pa':180,
            'pitch_type_prior_swings':50,
            'league_pitch_type_whiff':{'FF':.2,'SL':.35},
            'player_overall_k':{'101':.3,**{p:.2 for p in self.lineup}}}))
        args=self.args(out='research');args.research_priors=str(priors)
        result=prepare(args);out=Path(result['output'])
        profile=json.loads((out/'DELTA_PROFILE.json').read_text())['profiles'][0]
        report=json.loads((out/'RESEARCH_MATCHUPS.json').read_text())
        self.assertEqual(profile['research'],report)
        self.assertEqual(report['status'],'UNFITTED_RESEARCH_NO_FORECAST_EFFECT')
        self.assertEqual(report['lineup'][0]['batter_split']['status'],'SHRUNK_OBSERVED')
        self.assertEqual(report['lineup'][1]['status'],'UNAVAILABLE')
        self.assertIn('arsenal_whiff',report['lineup'][0])
        self.assertNotIn('feature_model',profile)
        self.assertNotIn('hook_model',profile)

    def test_conflicting_duplicate_is_rejected_atomically(self):
        overlap=self.root/'overlap.csv'
        changed=dict(self.pitches[0],release_speed='100')
        write_csv(overlap,PITCH_FIELDS,[changed])
        with self.assertRaisesRegex(ValueError,'Conflicting Statcast duplicate'):
            prepare(self.args(statcast=[str(self.csv),str(overlap)]))
        self.assertFalse((self.root/'result').exists())

    def test_identical_overlapping_export_is_deduplicated(self):
        overlap=self.root/'overlap.csv'
        write_csv(overlap,PITCH_FIELDS,[self.pitches[0]])
        result=prepare(self.args(statcast=[str(self.csv),str(overlap)]))
        audit=json.loads((Path(result['output'])/'COVERAGE.json').read_text())
        self.assertEqual(audit['statcast']['duplicates'],1)
        self.assertEqual(audit['statcast']['pitcher_pa'],2)

    def test_foul_tip_is_not_two_strike_foul_self_loop(self):
        self.assertEqual(outcome('foul_tip'),'unmapped')

    def test_future_and_same_day_data_cannot_create_profile(self):
        file=self.root/'only-today.csv'
        write_csv(file,PITCH_FIELDS,[self.pitches[-1]])
        with self.assertRaisesRegex(ValueError,'No eligible prior-date'):
            prepare(self.args(statcast=[str(file)]))
        self.assertFalse((self.root/'result').exists())

    def test_previous_utc_day_is_excluded_at_midnight_boundary(self):
        file=self.root/'yesterday.csv'
        row=dict(self.pitches[0],game_date=(self.today-timedelta(days=1)).isoformat())
        write_csv(file,PITCH_FIELDS,[row])
        with self.assertRaisesRegex(ValueError,'No eligible prior-date'):
            prepare(self.args(statcast=[str(file)]))

    def test_official_order_and_timestamp_required(self):
        args=self.args()
        args.lineup='201,202'
        with self.assertRaisesRegex(ValueError,'exactly nine'):
            prepare(args)
        args=self.args()
        args.start_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'future first pitch'):
            prepare(args)

    def test_export_uses_three_day_sequential_windows_and_manifest(self):
        calls=[]
        class Frame:
            def __len__(self): return 2
            def to_csv(self,path,index): Path(path).write_text('pitcher\n101\n102\n')
        def fake(start,end,verbose,parallel):
            calls.append((start,end,verbose,parallel))
            return Frame()
        module=types.ModuleType('pybaseball')
        module.statcast=fake
        args=argparse.Namespace(start=(self.today-timedelta(days=8)).isoformat(),
                                end=(self.today-timedelta(days=2)).isoformat(),
                                out=str(self.root/'export'))
        with patch.dict('sys.modules',{'pybaseball':module}):
            result=export_statcast(args)
        manifest=json.loads((self.root/'export/MANIFEST.json').read_text())
        self.assertEqual(len(calls),3)
        self.assertEqual(result['rows'],6)
        self.assertEqual(len(manifest['files']),3)
        self.assertTrue(all(not parallel for _,_,_,parallel in calls))

    def test_targeted_regular_season_export_and_manifest_verified_import(self):
        calls=[]
        class Series:
            def __init__(self,values): self.values=values
            def __eq__(self,other): return [v==other for v in self.values]
            def dropna(self): return self
            def unique(self): return list(dict.fromkeys(self.values))
        class Frame:
            def __init__(self,rows): self.rows=rows
            def __len__(self): return len(self.rows)
            @property
            def columns(self): return PITCH_FIELDS+['game_type']
            def __getitem__(self,key): return Series([r.get(key) for r in self.rows])
            @property
            def loc(self):
                outer=self
                class Locate:
                    def __getitem__(self,mask):
                        return Frame([r for r,keep in zip(outer.rows,mask) if keep])
                return Locate()
            def to_csv(self,path,index): write_csv(Path(path),self.columns,self.rows)
        def pitcher(start,end,player_id):
            calls.append(('pitcher',str(player_id),start,end))
            return Frame([dict(self.pitches[0],game_type='R'),
                          dict(self.pitches[2],game_type='R'),
                          dict(self.pitches[3],game_type='F')])
        def batter(start,end,player_id):
            pid=str(player_id)
            calls.append(('batter',pid,start,end))
            if pid=='201': return Frame([dict(self.pitches[0],game_type='R'),
                                         dict(self.pitches[2],game_type='R')])
            if pid=='202': return Frame([dict(self.pitches[3],game_type='F')])
            r=dict(self.pitches[3],batter=pid,pitcher='999',at_bat_number=int(pid),game_type='R')
            return Frame([r])
        module=types.ModuleType('pybaseball')
        module.statcast_pitcher=pitcher
        module.statcast_batter=batter
        args=argparse.Namespace(start=(self.today-timedelta(days=8)).isoformat(),
                                end=self.old,pitcher_id='101',lineup=','.join(self.lineup),
                                include_postseason=False,out=str(self.root/'selected'))
        with patch.dict('sys.modules',{'pybaseball':module}):
            output=export_players(args)
        manifest=json.loads((self.root/'selected/MANIFEST.json').read_text())
        self.assertEqual(len(calls),10)
        self.assertEqual(manifest['game_types'],'R_ONLY')
        self.assertEqual(output['missing_players'],['202'])
        self.assertEqual(output['files'],9)
        prepare_args=self.args(out='prepared-selected',statcast=[])
        prepare_args.statcast_dir=[str(self.root/'selected')]
        processed=prepare(prepare_args)
        audit=json.loads((Path(processed['output'])/'COVERAGE.json').read_text())
        self.assertGreaterEqual(audit['statcast']['duplicates'],2)
        self.assertEqual(audit['statcast']['pitcher_pa'],1)
        self.assertEqual(len(audit['sources']),9)
        with (self.root/'selected'/manifest['files'][0]['name']).open('a') as stream:
            stream.write('tampered\n')
        rejected=self.args(out='rejected',statcast=[])
        rejected.statcast_dir=[str(self.root/'selected')]
        with self.assertRaisesRegex(ValueError,'hash differs'):
            prepare(rejected)


if __name__ == '__main__':
    unittest.main()

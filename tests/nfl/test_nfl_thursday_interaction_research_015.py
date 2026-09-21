#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'packages/models/nfl/game/thursday_interaction_research_015.py'
spec=importlib.util.spec_from_file_location('m',p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

assert m.assert_development_only([2016,2024])==(2016,2024)
for bad in ([2025],[2026],[2024,2025]):
    try:
        m.assert_development_only(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('sealed/prospective season must be rejected')

assert m.score_margin_bucket({'score_differential':10})=='LEADING_9_PLUS'
assert m.score_margin_bucket({'score_differential':3})=='LEADING_1_8'
assert m.score_margin_bucket({'score_differential':0})=='TIED'
assert m.score_margin_bucket({'score_differential':-4})=='TRAILING_1_8'
assert m.score_margin_bucket({'score_differential':-12})=='TRAILING_9_PLUS'

no_int={
 'play_type':'no_play','no_play':1,'penalty':1,'yardline_100':4,'wpa':0.18,
 'desc':'J.Allen pass short right INTERCEPTED at DET 4. PENALTY on DET-R.Ya-Sin, Defensive Holding, 5 yards, accepted. No Play.',
 'state_intelligence':{'play_intent':'NO_PLAY'}
}
assert 'NULLIFIED_INTERCEPTION' in m.nullified_impact_types(no_int)
pl=m.penalty_leverage(no_int)
assert pl['high_leverage_candidate'] and pl['red_zone'] and abs(pl['wpa']-0.18)<1e-12

no_sack={
 'play_type':'no_play','no_play':1,'penalty':1,'yardline_100':11,
 'desc':'J.Allen steps back to pass. Sacked at DET 11 for -7 yards. PENALTY on DET-J.Campbell, Defensive Holding, 2 yards, accepted. No Play.',
 'state_intelligence':{'play_intent':'NO_PLAY'}
}
assert m.nullified_impact_types(no_sack)==('NULLIFIED_SACK',)


def row(pid,drive,team,intent,yards=0,down=1,first=0,score=0,desc='',success=None,pressure='BASE_STRUCTURAL_EXPOSURE',penalty=0,no_play=0):
    r={
      'game_id':'2024_01_A_B','play_id':pid,'drive':drive,'posteam':team,'defteam':'B' if team=='A' else 'A',
      'yards_gained':yards,'down':down,'first_down':first,'score_differential':score,'desc':desc,
      'penalty':penalty,'no_play':no_play,'play_type':'no_play' if no_play else ('run' if intent=='DESIGNED_RUN' else 'pass'),
      'state_intelligence':{
        'play_intent':intent,'football_tendency_eligible':intent not in {'NO_PLAY','SPECIAL_TEAMS'},
        'competitive_state':'COMPETITIVE','pressure_opportunity_bucket':pressure,
      }
    }
    if success is not None:r['success']=success
    return r

rows=[
 row(1,'1','A','DESIGNED_RUN',5,1,0,0,success=1),
 row(2,'1','A','DROPBACK_SCRAMBLE',8,3,1,0,pressure='HIGH_STRUCTURAL_EXPOSURE'),
 row(3,'1','A','DESIGNED_PASS',25,1,1,0,desc='A pass complete for 25 yards. TOUCHDOWN.'),
 row(4,'2','B','DESIGNED_PASS',12,1,1,-7),
 row(5,'2','B','DESIGNED_PASS',10,2,1,-7,desc='B pass complete for 10 yards. TOUCHDOWN.'),
 row(6,'3','A','DESIGNED_PASS',9,1,0,0),
 row(7,'3','A','DROPBACK_SACK',-7,3,0,0,pressure='HIGH_STRUCTURAL_EXPOSURE'),
 row(8,'3','A','DESIGNED_PASS',11,3,1,0,desc='A pass complete for 11 yards. TOUCHDOWN.'),
]

dr=m.attach_response_drive_flags(m.build_drive_records(rows))
assert len(dr)==3
A1=next(x for x in dr if x['drive']=='1')
assert A1['scrambles']==1 and A1['scramble_late_down_conversions']==1
assert A1['explosive_plays_20_plus']==1
assert abs(A1['pass_intent_rate']-2/3)<1e-12
A3=next(x for x in dr if x['drive']=='3')
assert A3['response_to_opponent_score'] is True and A3['response_drive_scored'] is True
assert A3['sacks']==1 and A3['explosive_plays_20_plus']==0

summary=m.summarize_game_interactions(rows+[no_int,no_sack])
assert summary['response_drives']['n']==2
assert summary['response_drives']['scored']==2
assert summary['qb_scramble_drive_survival']['late_down_scramble_conversions']==1
assert len(summary['nullified_impact_events'])==2
assert summary['penalty_leverage']['rows_with_erased_major_event']==2
assert 'TRUE_PRESSURE_GEOMETRY' in summary['data_gaps']

compact=m.build_historical_game_team_records(rows)
a=next(x for x in compact if x['team']=='A')
assert a['drives']==2 and a['dropbacks']==5 and a['scrambles']==1 and a['sacks']==1
assert a['mean_drive_mechanism_shift_tv'] is not None and a['mean_drive_mechanism_shift_tv']>0

print('PASS NFL State Intelligence 0.1.5 Thursday interaction contracts · 2025 sealed · no market dependency')

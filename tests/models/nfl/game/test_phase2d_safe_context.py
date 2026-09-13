#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import phase2d_hardening as h

games=[]
for wk in range(1,5):
    games.append({'game_id':f'2024_0{wk}_A_B','season':2024,'week':wk,'home_team':'A','away_team':'B'})
qb=[]
for wk in range(1,4):
    for team,qid in [('A','QBA'),('B','QBB')]:
        qb.append({'game_id':f'2024_0{wk}_A_B','season':2024,'week':wk,'team':team,'qb_gsis_id':qid,'observed_primary':1,'dropbacks':30,'primary_dropback_share':.95,'epa':.1 if team=='A' else -.05,'cpoe':1.0,'sack_rate':.05,'explosive_pass_rate':.1,'int_rate':.02})
q=h.build_strict_lag_qb_context(games,qb)
assert q[0]['home_lag_qb_gsis_id']==''
assert q[1]['home_lag_qb_gsis_id']=='QBA'
assert q[3]['away_last4_lag_qb_games']==3.0

snaps=[]
for wk in range(1,4):
    gid=f'2024_0{wk}_A_B'
    for team in ('A','B'):
        snaps += [
            {'game_id':gid,'season':2024,'week':wk,'team':team,'pfr_player_id':f'{team}OL','position':'OT','offense_snaps':60,'defense_snaps':0},
            {'game_id':gid,'season':2024,'week':wk,'team':team,'pfr_player_id':f'{team}WR','position':'WR','offense_snaps':50,'defense_snaps':0},
            {'game_id':gid,'season':2024,'week':wk,'team':team,'pfr_player_id':f'{team}DB','position':'CB','offense_snaps':0,'defense_snaps':60},
        ]
s=h.build_strict_lag_snap_context(games,snaps)
assert s[0]['home_lag_offense_snap_continuity'] is None
assert s[1]['home_lag_offense_snap_continuity'] is None
assert abs(s[2]['home_lag_offense_snap_continuity']-1.0)<1e-12
assert abs(s[3]['away_lag_defense_snap_continuity']-1.0)<1e-12
print('PASS Phase2D strict-lag context')

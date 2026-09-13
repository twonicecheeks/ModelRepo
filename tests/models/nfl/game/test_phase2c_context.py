#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import phase2c_context as pc

def play(g,s,w,t,q,epa=0.2,cpoe=2.0,y=10,sack=0,interception=0):
    return {'game_id':g,'season':s,'week':w,'posteam':t,'qb_dropback':1,'epa':epa,'qb_epa':epa,'cpoe':cpoe,'sack':sack,'yards_gained':y,'interception':interception,'passer_player_id':q,'passer_player_name':q,'no_play':0,'qb_kneel':0}

pbp=[]
# 2015 incumbent A dominates; 2016 week1 current-game QB B must NOT alter its own pregame context.
for _ in range(4):pbp.append(play('2015_17_X_Y',2015,17,'X','A',epa=.3))
for _ in range(3):pbp.append(play('2016_01_X_Z',2016,1,'X','B',epa=-.8))
qg=pc.extract_observed_qb_game_metrics(pbp)
games=[{'game_id':'2015_17_X_Y','season':2015,'week':17,'home_team':'Y','away_team':'X'}, {'game_id':'2016_01_X_Z','season':2016,'week':1,'home_team':'Z','away_team':'X'}]
rosters=[
 {'season':2016,'week':1,'team':'X','gsis_id':'A','pfr_id':'pA','position':'QB','depth_chart_position':'QB','status':'ACT','game_type':'REG'},
 {'season':2016,'week':1,'team':'X','gsis_id':'B','pfr_id':'pB','position':'QB','depth_chart_position':'QB','status':'ACT','game_type':'REG'},
]
ctx=pc.build_qb_pregame_context(games,qg,rosters)
r=next(x for x in ctx if x['game_id']=='2016_01_X_Z')
assert r['away_projected_qb_gsis_id']=='A',r
assert r['away_qb_resolution']=='INCUMBENT_ACTIVE_PROXY'
assert r['away_week1_qb_continuity']==1.0
assert abs(r['away_prior_season_qb_epa']-.3)<1e-9
# If current-game B had leaked, this would be negative.
assert r['away_last4_qb_epa']>.2

snaps=[
 {'game_id':'2015_17_X_Y','season':2015,'week':17,'team':'X','pfr_player_id':'ol1','position':'LT','offense_snaps':60,'defense_snaps':0},
 {'game_id':'2015_17_X_Y','season':2015,'week':17,'team':'X','pfr_player_id':'wr1','position':'WR','offense_snaps':40,'defense_snaps':0},
 {'game_id':'2015_17_X_Y','season':2015,'week':17,'team':'X','pfr_player_id':'d1','position':'CB','offense_snaps':0,'defense_snaps':50},
]
rosters += [
 {'season':2016,'week':1,'team':'X','gsis_id':'OL1','pfr_id':'ol1','position':'T','depth_chart_position':'T','status':'ACT','game_type':'REG'},
 {'season':2016,'week':1,'team':'X','gsis_id':'D2','pfr_id':'d2','position':'CB','depth_chart_position':'CB','status':'ACT','game_type':'REG'},
]
rc=pc.build_roster_continuity_context(games,snaps,rosters)
r=next(x for x in rc if x['game_id']=='2016_01_X_Z')
assert abs(r['away_offense_snap_continuity']-.6)<1e-9,r
assert abs(r['away_ol_snap_continuity']-1.0)<1e-9
assert abs(r['away_skill_snap_continuity']-0.0)<1e-9
assert abs(r['away_defense_snap_continuity']-0.0)<1e-9
assert r['away_week1_offense_snap_continuity']==r['away_offense_snap_continuity']
print('PASS Phase2C context: QB strict lag / Week1 continuity / snap-weighted roster return')

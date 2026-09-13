#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import phase2c_model as pm
base=('a','b')
row={'week':1,'home_qb_continuity':1,'away_qb_continuity':0,'home_qb_change_proxy':0,'away_qb_change_proxy':1,'home_qb_unresolved':0,'away_qb_unresolved':0,'home_active_qb_count':2,'away_active_qb_count':2}
for h in pm.QB_HORIZONS:
    for side in ('home','away'):
        row[f'{side}_{h}_qb_games']=4;row[f'{side}_{h}_qb_dropbacks']=120
        for m in pm.QB_METRICS:row[f'{side}_{h}_qb_{m}']=.1 if side=='home' else 0
for s in pm.ROSTER_STEMS:
    row[f'home_{s}']=.9;row[f'away_{s}']=.7;row[f'home_week1_{s}']=.9;row[f'away_week1_{s}']=.7
row['home_week1_qb_continuity']=1;row['away_week1_qb_continuity']=0;row['home_week1_qb_change_proxy']=0;row['away_week1_qb_change_proxy']=1
assert pm.combined_names(base,include_qb=False,include_roster=False)==base
nq=pm.combined_names(base,include_qb=True,include_roster=False);nr=pm.combined_names(base,include_qb=False,include_roster=True);na=pm.combined_names(base,include_qb=True,include_roster=True)
assert len(nq)>2 and len(nr)>2 and len(na)>len(nq)
v=pm.combined_vector((.2,.3),row,base,include_qb=True,include_roster=True)
assert len(v)==len(na)
print('PASS Phase2C vectorization: pure base preserved / QB and roster feature families isolated')

#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import phase2e_freeze as p
assert p.season_stage(1)=='week1'
assert p.season_stage(2)=='weeks2to4'
assert p.season_stage(4)=='weeks2to4'
assert p.season_stage(5)=='week5plus'
assert p.candidate_keep('last8_off_success_rate_diff')
assert not p.candidate_keep('last4_off_success_rate_diff')
assert not p.candidate_keep('prior_season_def_takeaway_rate_diff',no_turnover=True)
assert not p.candidate_keep('prior_season_off_rush_epa_diff',no_rush_epa=True)
rows=[]
for season in (2018,2019,2020,2021):
    for week in range(1,9):
        y=(season+week)%2
        # base is better in week1, context better after week1.
        pb=.75 if (y and week==1) else (.25 if (not y and week==1) else (.60 if y else .40))
        pc=.58 if (y and week==1) else (.42 if (not y and week==1) else (.80 if y else .20))
        rows.append({'season':season,'week':week,'y':y,'pb':pb,'pc':pc})
w=p.select_stage_weights(rows,base_field='pb',context_field='pc')
assert w['week1']['selected']['contextWeight'] < w['week5plus']['selected']['contextWeight']
ps=p.apply_stage_weights(rows,base_field='pb',context_field='pc',weights=w)
assert len(ps)==len(rows) and all(0<x<1 for x in ps)
print('PASS Phase2E freeze primitives')

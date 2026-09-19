#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'packages/models/nfl/omega/offball_lb_opportunity_0370.py'
spec=importlib.util.spec_from_file_location('lb037',p)
m=importlib.util.module_from_spec(spec);sys.modules['lb037']=m;spec.loader.exec_module(m)

assert m.assert_development_only([2017,2024])==(2017,2024)
try:m.assert_development_only([2025])
except ValueError:pass
else:raise AssertionError('2025 must remain sealed')

rows=[]
for week in range(1,71):
    for team,opp in [('A','B'),('B','A')]:
        for j in range(2):
            pid=f'{team}{j}'
            snap=.92 if j==0 else .72
            actual=(6.0 if j==0 else 3.0)+(week%2)
            r={
              'game_id':f'2024_{week:02d}_{team}_{opp}','season':2024,'week':week,
              'team':team,'opponent':opp,'player_id':pid,'display_name':pid,
              'position':'ILB' if j==0 else 'MLB','position_group':'LB',
              'actual_xtc':actual,'control_xtc':actual-.4 if j==0 else actual+.2,
              'predicted_xto':45+week*.1,'predicted_snap_share':snap,'prior_games':week-1,
            }
            shares={'RUSH':.42,'COMPLETE_PASS':.38,'SCRAMBLE':.08,'SACK':.06,'OTHER_PASS':.06}
            rates={'RUSH':.18 if j==0 else .12,'COMPLETE_PASS':.12 if j==0 else .08,
                   'SCRAMBLE':.20 if j==0 else .11,'SACK':.04,'OTHER_PASS':.05}
            for fam in m.FAMILIES:
                r[f'pred_share_{fam}']=shares[fam]
                r[f'pred_credit_{fam}']=shares[fam]*rates[fam]*snap*10
            rows.append(r)

team,player=m.build_decomposition_rows(rows)
assert len(team)==140 and len(player)==280
# Week 1 histories use defaults; week 2 is allowed to use week 1, never same-week outcome.
w1=[r for r in team if r['week']==1][0]
w2=[r for r in team if r['week']==2 and r['team']==w1['team']][0]
assert w1['prior_team_games_log']==0
assert w2['prior_team_games_log']>0
# Player actual allocation sums to one per team-game when pool > 0.
for gid in sorted({r['game_id'] for r in player}):
    for tm in sorted({r['team'] for r in player if r['game_id']==gid}):
        rr=[r for r in player if r['game_id']==gid and r['team']==tm]
        assert abs(sum(r['actual_lb_share'] for r in rr)-1)<1e-12

train_team=[r for r in team if r['week']<=60]
test_team=[r for r in team if r['week']>=61]
train_player=[r for r in player if r['week']<=60]
test_player=[r for r in player if r['week']>=61]
tm=m.fit_ridge(train_team,m.TEAM_FEATURES,'actual_lb_pool',m.FIXED_L2_TEAM)
am=m.fit_ridge(train_player,m.ALLOC_FEATURES,'actual_lb_share',m.FIXED_L2_ALLOC,clip_high=1.0)
sc=m.apply_combined(test_team,test_player,tm,am)
assert len(sc)==len(test_player)
for gid in {r['game_id'] for r in sc}:
    for team_name in {r['team'] for r in sc if r['game_id']==gid}:
        rr=[r for r in sc if r['game_id']==gid and r['team']==team_name]
        assert abs(sum(r['predicted_lb_share'] for r in rr)-1)<1e-9
        assert all(r['omega_037_xtc']>=0 for r in rr)

clone=m.RidgeModel.from_dict(tm.to_dict())
assert abs(clone.predict(test_team[0])-tm.predict(test_team[0]))<1e-12
print('PASS OMEGA 0.37 decomposition contracts · team pool + player allocation · 2025 sealed')

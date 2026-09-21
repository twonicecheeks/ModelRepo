#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'packages/models/nfl/omega/offball_lb_joint_0400.py'
spec=importlib.util.spec_from_file_location('lb040',p)
m=importlib.util.module_from_spec(spec);sys.modules['lb040']=m;spec.loader.exec_module(m)

assert m.assert_development_only([2017,2024])==(2017,2024)
try:m.assert_development_only([2025])
except ValueError:pass
else:raise AssertionError('2025 must remain sealed')

exposure=[]
opportunity=[]
for i in range(140):
    snap=.45+.003*(i%100)
    exposure.append({
      'actual_snap_share':min(1.0,snap+.04),
      'position_prior_snap_share':.62,'prior_games_cap8':min(1.0,i/8),'prior_games_log':1.0,
      'last1_snap_share':snap,'last2_snap_share_mean':snap-.01,'last4_snap_share_mean':snap-.02,
      'last8_snap_share_mean':snap-.03,'last4_snap_share_std':.05,'last4_snap_share_min':max(0,snap-.12),
      'last4_snap_share_max':min(1,snap+.10),'last1_minus_last4':.02,'last2_minus_last8':.02,
      'position_DB':0.0,'position_LB':1.0,'position_DL':0.0,'position_OTHER':0.0,
      'cold_start':0.0,'one_prior_game':0.0,
    })
    r={}
    for j,n in enumerate(m.TEAM_BASE_FEATURES):
        r[n]=float((i+j)%17)/10.0
    shares={'RUSH':.42,'COMPLETE_PASS':.38,'SCRAMBLE':.08,'SACK':.06,'OTHER_PASS':.06}
    for fam in m.FAMILIES:
        r[f'pred_share_{fam}']=shares[fam]
        r[f'actual_opp_{fam}']=10*shares[fam]+(i%3)*.1
    opportunity.append(r)

em=m.fit_exposure(exposure)
oms=m.fit_opportunities(opportunity)
assert 0<=em.predict(exposure[0])<=1
assert all(oms[f].predict(opportunity[0])>=0 for f in m.FAMILIES)

clone=m.RidgeModel.from_dict(em.to_dict())
assert abs(clone.predict(exposure[7])-em.predict(exposure[7]))<1e-12

control={
 'game_id':'G','team':'A','player_id':'P','actual_xtc':4.0,
 'predicted_snap_share':.50,'actual_snap_share':.58,
}
rates={'RUSH':.20,'COMPLETE_PASS':.12,'SCRAMBLE':.18,'SACK':.05,'OTHER_PASS':.02}
opps={'RUSH':12.0,'COMPLETE_PASS':10.0,'SCRAMBLE':2.0,'SACK':2.0,'OTHER_PASS':1.0}
for fam in m.FAMILIES:
    control[f'pred_opp_{fam}']=opps[fam]
    control[f'shrunk_rate_{fam}']=rates[fam]
control['control_xtc']=sum(opps[f]*.50*rates[f] for f in m.FAMILIES)

er=dict(exposure[0]);er.update({'game_id':'G','team':'A','player_id':'P'})
tr=dict(opportunity[0]);tr.update({'game_id':'G','defense_team':'A'})
sc=m.score_ablation(
  [control],em,{('G','A','P'):er},oms,{('G','A'):tr}
)
assert len(sc)==1
assert abs(sc[0]['omega040_control_xtc']-control['control_xtc'])<1e-12
assert sc[0]['omega040_joint_xtc']>=0

fake=[]
for i in range(20):
    fake.append({'game_id':f'G{i}','actual_xtc':5.0,'base':4.0,'cand':4.5})
b=m.paired_game_bootstrap(fake,'base','cand',reps=100,seed=1)
assert b['ci95']['maeImprovement']['low']>0
print('PASS OMEGA 0.40 joint LB challenger contracts · exact control reconstruction · 2025 sealed')

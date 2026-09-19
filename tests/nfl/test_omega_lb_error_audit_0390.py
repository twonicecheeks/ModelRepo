#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/audit_omega_offball_lb_error_0390.py'
spec=importlib.util.spec_from_file_location('audit0390',p)
m=importlib.util.module_from_spec(spec);sys.modules['audit0390']=m;spec.loader.exec_module(m)

row={
 'actual_snap_share':.80,'predicted_snap_share':.60,'prior_games':7,
}
for fam,actual_opp,pred_opp,rate,actual_credit in [
 ('RUSH',20,15,.10,2.0),
 ('COMPLETE_PASS',18,18,.05,1.0),
 ('SCRAMBLE',4,2,.20,1.0),
 ('SACK',3,3,.10,.0),
 ('OTHER_PASS',5,5,.05,.0),
]:
    row[f'actual_team_opp_{fam}']=actual_opp
    row[f'pred_opp_{fam}']=pred_opp
    row[f'shrunk_rate_{fam}']=rate
    row[f'actual_credit_{fam}']=actual_credit
    row[f'pred_credit_{fam}']=pred_opp*.60*rate

z=m.enrich([row])[0]
assert z['audit_snap_bucket']=='>=0.75'
assert z['audit_history_bucket']=='>=6'
assert abs(z['audit_oracle_opp_RUSH']-(20*.60*.10))<1e-12
assert abs(z['audit_oracle_snap_RUSH']-(15*.80*.10))<1e-12
assert abs(z['audit_oracle_both_RUSH']-(20*.80*.10))<1e-12

s=m.summarize([z])
assert s['baseline']['n']==1
assert 'RUSH' in s['families']
assert abs(s['families']['RUSH']['maeGainFromBothOracle'] - (
    s['families']['RUSH']['baseline']['mae']-s['families']['RUSH']['oracleBoth']['mae']
))<1e-12
print('PASS OMEGA 0.39 error-attribution contracts')

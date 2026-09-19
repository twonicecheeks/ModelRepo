#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import sys
root=Path(__file__).resolve().parents[2]
p=root/'packages/models/nfl/omega/position_specific_challenger_0360.py'
spec=importlib.util.spec_from_file_location('m',p);m=importlib.util.module_from_spec(spec);sys.modules['m']=m;spec.loader.exec_module(m)

assert m.assert_development_only([2017,2024])==(2017,2024)
try:m.assert_development_only([2025])
except ValueError:pass
else:raise AssertionError('2025 must remain sealed')
assert m.canonical_position('MLB')=='LB' and m.canonical_position('CB')=='DB' and m.canonical_position('EDGE')=='DL'

base={
 'position_group':'LB','control_xtc':6.0,'predicted_xto':45,'predicted_snap_share':.9,'prior_games':8,
 'pred_credit_RUSH':3,'pred_credit_SCRAMBLE':1,'pred_credit_COMPLETE_PASS':1.5,'pred_credit_SACK':.3,'pred_credit_OTHER_PASS':.2,
 'pred_share_RUSH':.4,'pred_share_SCRAMBLE':.08,'pred_share_COMPLETE_PASS':.35,'pred_share_SACK':.05,'pred_share_OTHER_PASS':.12,
 'shrunk_rate_RUSH':.16,'shrunk_rate_SCRAMBLE':.22,'shrunk_rate_COMPLETE_PASS':.09,'shrunk_rate_SACK':.2,'shrunk_rate_OTHER_PASS':.05,
}
f=m.feature_map(base)
assert abs(f['rush_x_scramble_share']-.032)<1e-12
assert abs(f['mobile_family_credit_share']-(1.3/6))<1e-12
assert len(m.vector(base,'LB'))==len(m.LB_FEATURES)

rows=[]
for i in range(80):
 r=dict(base);r['game_id']=f'G{i//4}';r['player_id']=f'P{i}';r['actual_xtc']=5.5 + (i%3)*.2
 rows.append(r)
mdl=m.fit_residual(rows,'LB')
z=m.apply_challengers(rows[:2],{'LB':mdl})
assert len(z)==2 and all(r['position_challenger_track']=='LB_RESIDUAL_SHADOW' for r in z)

dl=dict(base);dl.update({'position_group':'DL','actual_xtc':3,'control_xtc':3.1})
out=m.apply_challengers([dl],{'LB':mdl})[0]
assert out['position_challenger_xtc']==3.1 and out['position_challenger_track']=='DL_CONTROL_NO_CHANGE'

print('PASS OMEGA 0.36 position-specific challenger contracts · DL control preserved · 2025 sealed')

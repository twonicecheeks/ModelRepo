#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/audit_omega_offball_lb_matchup_signal_0440.py'
spec=importlib.util.spec_from_file_location('audit0440',p)
m=importlib.util.module_from_spec(spec);sys.modules['audit0440']=m;spec.loader.exec_module(m)

assert m.role_band(.20)=='LOW_<35'
assert m.role_band(.50)=='ROTATION_35-65'
assert m.role_band(.75)=='STARTER_65-85'
assert m.role_band(.90)=='EVERY_DOWN_85+'

rows=[]
for i in range(250):
    x=i/249
    rows.append({'x':x,'snap_residual_actual_minus_pred':0.4*x-0.2})
r=m.pearson(rows,'x')
assert r is not None and r>.99

flat=[{'x':1.0,'snap_residual_actual_minus_pred':(-1 if i%2 else 1)*.1} for i in range(20)]
assert m.pearson(flat,'x')==0.0

s=m.summarize_signal(rows,'x')
assert s['n']==250
assert s['pearson']>.99
print('PASS OMEGA 0.44 matchup-conditioned LB exposure signal audit contracts')

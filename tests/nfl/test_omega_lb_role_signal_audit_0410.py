#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/audit_omega_offball_lb_role_signal_0410.py'
spec=importlib.util.spec_from_file_location('audit0410',p)
m=importlib.util.module_from_spec(spec);sys.modules['audit0410']=m;spec.loader.exec_module(m)

starter={
 'depth_rank':1,'prev_depth_rank':2,'predicted_snap_share':.50,'actual_snap_share':.82,
 'actual_xtc':5.0,
}
backup={
 'depth_rank':2,'prev_depth_rank':1,'predicted_snap_share':.80,'actual_snap_share':.42,
 'actual_xtc':2.0,
}
for r in (starter,backup):
    for f in ('RUSH','COMPLETE_PASS','SCRAMBLE','SACK','OTHER_PASS'):
        r[f'pred_opp_{f}']=5.0
        r[f'shrunk_rate_{f}']=.10

assert m.role_state(starter)=='STARTER_CONFLICT'
assert m.role_state(backup)=='BACKUP_CONFLICT'
rows=m.enrich([starter,backup])
assert rows[0]['audit_snap_residual_actual_minus_pred']>0
assert rows[1]['audit_snap_residual_actual_minus_pred']<0
s=m.summarize(rows)
assert s['n']==2
g=m.grouped(rows,'audit_role_state')
assert g['STARTER_CONFLICT']['positiveResidualRate']==1.0
assert g['BACKUP_CONFLICT']['negativeResidualRate']==1.0
print('PASS OMEGA 0.41 role-signal audit contracts')

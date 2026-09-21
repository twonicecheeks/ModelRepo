#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/audit_omega_offball_lb_injury_signal_0431.py'
spec=importlib.util.spec_from_file_location('audit0431',p)
m=importlib.util.module_from_spec(spec);sys.modules['audit0431']=m;spec.loader.exec_module(m)

assert m.state_from_injury(None)=='NOT_LISTED'
assert m.state_from_injury({'report_status':'Out','practice_status':'Full Participation in Practice'})=='OUT'
assert m.state_from_injury({'report_status':'Questionable','practice_status':'Did Not Participate in Practice'})=='QUESTIONABLE'
assert m.state_from_injury({'report_status':'','practice_status':'Did Not Participate in Practice'})=='PRACTICE_DNP'
assert m.state_from_injury({'report_status':'','practice_status':'Limited Participation in Practice'})=='PRACTICE_LIMITED'
assert m.state_from_injury({'report_status':'','practice_status':'Full Participation in Practice'})=='PRACTICE_FULL'
assert m.state_group('QUESTIONABLE')=='GAME_STATUS'
assert m.state_group('PRACTICE_DNP')=='PRACTICE_RESTRICTED'

rows=[]
for y in (2021,2022,2023,2024):
    for i in range(20):
        rows.append({
          'season':y,'actual_snap_share':.50,'predicted_snap_share':.62,
          'snap_residual_actual_minus_pred':-.12,
        })
pooled=m.summarize(rows)
yearly={str(y):m.summarize([r for r in rows if r['season']==y]) for y in (2021,2022,2023,2024)}
assert pooled['n']==80
assert pooled['negativeResidualRate']==1.0
assert m.directional_material(pooled,yearly)

weak=[dict(r,snap_residual_actual_minus_pred=-.02,actual_snap_share=.60,predicted_snap_share=.62) for r in rows]
wp=m.summarize(weak)
wy={str(y):m.summarize([r for r in weak if r['season']==y]) for y in (2021,2022,2023,2024)}
assert not m.directional_material(wp,wy)

assert m.timing_class('2024-09-06T12:00:00Z','2024-09-08')=='STRICT_PRIOR_DAY'
assert m.timing_class('2024-09-08T10:00:00Z','2024-09-08')=='SAME_GAMEDAY'
print('PASS OMEGA 0.43.1 strict-prior LB injury signal audit contracts')

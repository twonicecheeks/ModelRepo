#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/audit_omega_offball_lb_exposure_structure_0420.py'
spec=importlib.util.spec_from_file_location('audit0420',p)
m=importlib.util.module_from_spec(spec);sys.modules['audit0420']=m;spec.loader.exec_module(m)

assert m.role_band(.20)=='LOW_<35'
assert m.role_band(.50)=='ROTATION_35-65'
assert m.role_band(.75)=='STARTER_65-85'
assert m.role_band(.90)=='EVERY_DOWN_85+'
assert m.trend_band(-.20)=='DOWN_15+'
assert m.trend_band(.20)=='UP_15+'
assert m.volatility_band(.03)=='STD_<05'
assert m.volatility_band(.22)=='STD_20+'
assert m.history_band(0)=='0-1'
assert m.history_band(7)=='5-8'
assert m.room_count_band(1)=='ONE'
assert m.room_count_band(3)=='THREE_PLUS'
assert m.competition_band(.90)=='OTHER_85+'

rows=[]
for y in (2021,2022,2023,2024):
    for i in range(30):
        rows.append({
          'season':y,'actual_snap_share':.78,'predicted_snap_share':.68,
          'snap_residual_actual_minus_pred':.10,
        })
pooled=m.summarize(rows)
yearly={str(y):m.summarize([r for r in rows if r['season']==y]) for y in (2021,2022,2023,2024)}
assert pooled['n']==120
assert pooled['positiveResidualRate']==1.0
assert m.material_slice('x',pooled,yearly)

weak=[dict(r,snap_residual_actual_minus_pred=.02,actual_snap_share=.70,predicted_snap_share=.68) for r in rows]
wp=m.summarize(weak)
wy={str(y):m.summarize([r for r in weak if r['season']==y]) for y in (2021,2022,2023,2024)}
assert not m.material_slice('x',wp,wy)
print('PASS OMEGA 0.42 exposure-structure audit contracts')

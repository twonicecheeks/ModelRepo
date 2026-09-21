#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/audit_omega_offball_lb_room_0380.py'
spec=importlib.util.spec_from_file_location('audit0380',p)
m=importlib.util.module_from_spec(spec);sys.modules['audit0380']=m;spec.loader.exec_module(m)

explicit=[
 {'game_id':'G1','team':'A','actual_xtc':'6','control_xtc':'5.5'},
 {'game_id':'G1','team':'A','actual_xtc':'3','control_xtc':'3.2'},
 {'game_id':'G2','team':'B','actual_xtc':'5','control_xtc':'5.1'},
]
added=[
 {'game_id':'G1','team':'A','actual_xtc':'2','control_xtc':'1.8'},
]
s=m.summarize_rooms(explicit,added)
assert s['teamGames']==2
assert s['teamGamesWithHighConfidenceGenericAddition']==1
assert abs(s['teamGameAdditionRate']-.5)<1e-12
assert abs(s['addedShareOfCompletedActualCredits']-(2/16))<1e-12
assert m.bin_prob(.1)=='0.00-0.20'
assert m.bin_prob(.3)=='0.20-0.50'
assert m.bin_prob(.6)=='0.50-0.80'
assert m.bin_prob(.9)=='0.80-1.00'
print('PASS OMEGA 0.38 room-completeness audit contracts')

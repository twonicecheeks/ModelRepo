#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/compare_omega_tackle_market_01712.py'
spec=importlib.util.spec_from_file_location('m',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

assert m.alias_market_name('Foyesade Oluokun','Jaguars') == 'FOYEOLUOKUN'
assert m.alias_market_name('Joshua Metellus','Vikings') == 'JOSHMETELLUS'
assert m.alias_market_name('Foyesade Oluokun','Falcons') == 'FOYESADEOLUOKUN'
assert m.alias_market_name('Josh Metellus','Vikings') == 'JOSHMETELLUS'

ledger=[
 {'player_id':'00-foye','player_name':'Foye Oluokun','team':'JAX','opponent':'CLE'},
 {'player_id':'00-josh','player_name':'Josh Metellus','team':'MIN','opponent':'GB'},
]
idx=m.build_indexes(ledger)

c,method=m.resolve_market_identity(
 {'player_id':'2611','player_name':'Foyesade Oluokun','player_team':'Jaguars','opponent':''},idx)
assert len(c)==1 and c[0]['player_id']=='00-foye'
assert method=='EXPLICIT_ALIAS_NAME_TEAM'

c,method=m.resolve_market_identity(
 {'player_id':'3977','player_name':'Joshua Metellus','player_team':'Vikings','opponent':''},idx)
assert len(c)==1 and c[0]['player_id']=='00-josh'
assert method=='EXPLICIT_ALIAS_NAME_TEAM'

print('PASS OMEGA 0.17.12 explicit team-scoped player alias contracts')

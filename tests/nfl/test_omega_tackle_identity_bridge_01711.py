#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/compare_omega_tackle_market_01711.py'
spec=importlib.util.spec_from_file_location('m',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

assert m.canon_name('Kevin Byard III') == m.canon_name('Kevin Byard')
assert m.canon_name("A.J. Epenesa") == m.canon_name("AJ Epenesa")
assert m.canon_team('Chicago Bears') == m.canon_team('CHI') == 'BEARS'
assert m.canon_team('Jacksonville Jaguars') == m.canon_team('JAC') == m.canon_team('JAX') == 'JAGUARS'
assert m.canon_team('Los Angeles Rams') == m.canon_team('LA') == m.canon_team('LAR') == 'RAMS'
assert m.canon_team('Los Angeles Chargers') == m.canon_team('LAC') == 'CHARGERS'

ledger=[
 {'player_id':'00-1','player_name':'Kevin Byard','team':'CHI','opponent':'MIN'},
 {'player_id':'00-2','player_name':'Robert Spillane','team':'NE','opponent':'SEA'},
]
idx=m.build_indexes(ledger)
c,method=m.resolve_market_identity(
 {'player_id':'1202','player_name':'Kevin Byard III','player_team':'Chicago Bears','opponent':'Minnesota Vikings'},idx)
assert len(c)==1 and c[0]['player_id']=='00-1'
assert method.startswith('CANON_NAME_')

# Provider-local numeric id must not drive the join.
c,method=m.resolve_market_identity(
 {'player_id':'00-2','player_name':'Kevin Byard III','player_team':'Chicago Bears','opponent':'Minnesota Vikings'},idx)
assert len(c)==1 and c[0]['player_id']=='00-1'

print('PASS OMEGA 0.17.11 deterministic identity-bridge contracts')

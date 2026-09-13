#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/import_omega_official_inactives_0190.py'
spec=importlib.util.spec_from_file_location('m',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

assert m.cteam('Chicago Bears')=='BEARS'
assert m.cteam('CHI')=='BEARS'
assert m.alias_name('Foyesade Oluokun','JAX')=='FOYEOLUOKUN'

sections=[
 {'canonicalTeam':'BEARS','inactiveCandidates':['Player One','Player Two','Player Three']},
 {'canonicalTeam':'VIKINGS','inactiveCandidates':['Viking One','Viking Two','Viking Three']}
]
pub,conf=m.consolidate_sections(sections)
assert not conf
assert 'BEARS' in pub and m.cname('Player One') in pub['BEARS']

# Duplicate agreeing DOM representations should not create a conflict.
sections2=[
 {'canonicalTeam':'BEARS','inactiveCandidates':['Player One','Player Two','Player Three']},
 {'canonicalTeam':'BEARS','inactiveCandidates':['Player One','Player Two','Player Four']}
]
pub,conf=m.consolidate_sections(sections2)
assert 'BEARS' in pub and not conf

# Strongly disagreeing duplicates fail closed for the team.
sections3=[
 {'canonicalTeam':'BEARS','inactiveCandidates':['Player One','Player Two','Player Three']},
 {'canonicalTeam':'BEARS','inactiveCandidates':['Different A','Different B','Different C']}
]
pub,conf=m.consolidate_sections(sections3)
assert 'BEARS' in conf and 'BEARS' not in pub

print('PASS OMEGA 0.19.0 official-inactives availability contracts')

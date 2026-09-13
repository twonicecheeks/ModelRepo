#!/usr/bin/env python3
from pathlib import Path
import importlib.util,tempfile,csv,subprocess,json
ROOT=Path(__file__).resolve().parents[2]
def load(name):
 p=ROOT/'scripts/nfl'/name;s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
s=load('seal_omega_tackle_014_post_holdout.py');assert s.r5(1.657091)==1.65709
r=load('init_omega_tackle_pregame_role_014.py');assert 'game_status' in r.FIELDS and 'predicted_xtc' not in r.FIELDS
x=load('append_omega_tackle_pregame_role_snapshot_014.py');assert 'OUT' in x.ENUMS['game_status'];assert any('odds'==t for t in x.FORBIDDEN_TOKENS)
print('PASS OMEGA 0.14 production-gate contract tests')

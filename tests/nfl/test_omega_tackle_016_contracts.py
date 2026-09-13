#!/usr/bin/env python3
from pathlib import Path
import importlib.util,tempfile,json
ROOT=Path(__file__).resolve().parents[2]
def load(rel,name):
 p=ROOT/rel;spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
fr=load('scripts/nfl/freeze_omega_tackle_016_probability.py','fr')
params={'globalSize':4,'size_LOW':2,'size_ROTATIONAL':3,'size_STARTER':5,'size_EVERY_DOWN':8}
spec={'frozenMeanSpecSha256':fr.EXPECTED_MEAN_SHA,'selectedArchitecture':'NB_ROLE','distribution':{'productionResearchParamsFitThrough2024':params}}
aud={'integrity':{'omega2025OutcomeRowsRead':0,'marketFieldsRead':0,'oddsPapiRequests':0},'confirmation2024':{'label':'CONFIRMATION_BOTH_IMPROVE','selectedVsPoissonCountNLLImprovement':.1,'selectedVsPoissonThresholdBrierImprovement':.001}}
assert fr.validate(spec,aud)==params
cap=load('scripts/nfl/capture_omega_tackle_016_2026_pregame.py','cap')
assert cap.roster_status('ACT')=='ACTIVE_ROSTER' and cap.roster_status('DEV')=='PRACTICE_SQUAD'
assert cap.game_status('Questionable')=='QUESTIONABLE' and cap.game_status('Out')=='OUT' and cap.game_status('')=='NOT_LISTED'
assert cap.pg('CB')=='DB' and cap.pg('OLB')=='LB' and cap.pg('DT')=='DL' and cap.pg('WR')==''
text=(ROOT/'scripts/nfl/build_omega_tackle_016_2026_week1.py').read_text()
assert "week!=1" in text and "2026OutcomeRowsRead':0" in text
assert 'CURRENT_OMEGA_TACKLE_2026_PREGAME_SOURCE' in text
print('PASS OMEGA 0.16 prospective probability contracts')

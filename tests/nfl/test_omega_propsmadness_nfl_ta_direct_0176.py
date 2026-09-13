#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/import_omega_propsmadness_nfl_ta_direct_0176.py'
spec=importlib.util.spec_from_file_location('m',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

payload={
 'requests':{
  'market':{'ok':True,'status':200,'data':{
   'market':{'slug':'player-tackles-assists','name':'Tackles + Assists'},
   'offers':[
    {'matchId':17067,'player':{'id':3000,'name':'Test Defender','teamId':1},
     'bet':{'line':7.5,'sportsbook':{'name':'pinnacle'},'odds':{'over':{'american':-110},'under':{'american':-105}}}}
   ]}},
  'matches':{'ok':True,'status':200,'data':{'matches':[
    {'id':17067,'homeTeam':{'id':1,'abbreviation':'SEA'},'awayTeam':{'id':2,'abbreviation':'NE'},'startTime':'2026-09-09T00:00:00Z'}
  ]}}
 }}
rows,stats=m.normalize_capture(payload)
assert len(rows)==1
r=rows[0]
assert r['market_kind']=='tackles_assists'
assert r['player_name']=='Test Defender'
assert r['player_team']=='SEA'
assert r['opponent']=='NE'
assert r['line']=='7.5'
assert r['over_odds_american']=='-110'
assert r['under_odds_american']=='-105'
assert stats['offerCount']==1

bad={'requests':{'market':{'ok':True,'data':{'market':{'slug':'wrong'},'offers':[{}]}},'matches':{'ok':True,'data':{}}}}
try:m.normalize_capture(bad)
except ValueError:pass
else:raise AssertionError('slug mismatch must fail closed')

try:m.american(1.91)
except ValueError:pass
else:raise AssertionError('decimal odds must fail closed')

print('PASS OMEGA 0.17.6 direct PropsMadness T+A adapter contracts')

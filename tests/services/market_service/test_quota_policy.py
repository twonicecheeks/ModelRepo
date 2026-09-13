#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
service=ROOT/'services/market-service/src/model_service.py'
spec=importlib.util.spec_from_file_location('svc',service)
svc=importlib.util.module_from_spec(spec); spec.loader.exec_module(svc)
with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    svc.DATA_DIR=td/'data'; svc.LATEST_MLB=svc.DATA_DIR/'mlb/latest.json'; svc.CACHE_DIR=td/'cache'
    svc.get_api_key=lambda:'x'
    cfg={
      'provider':{'oddspapi':{'moneylineBooks':['pinnacle','circasports','fanduel'],'moneylineSharpBooks':['pinnacle','circasports'],'minRefreshSeconds':0,'consensusMaxBookSkewSeconds':120}},
      'sports':{'mlb':{'tournamentId':109,'sportId':13,'markets':{'moneyline':131}}}
    }
    svc.load_config=lambda:cfg
    calls=[]
    def fake(path,params,key):
        calls.append((path,dict(params)))
        if path=='odds-by-tournaments': return []
        raise AssertionError('unexpected OddsPapi endpoint '+path)
    svc.oddspapi_get=fake
    svc.official_mlb_schedule=lambda date:[]
    snap=svc.refresh_mlb(force=True)
    assert len(calls)==3,calls
    assert {p for p,_ in calls}=={'odds-by-tournaments'},calls
    assert [x[1]['bookmaker'] for x in calls]==['pinnacle','circasports','fanduel'],calls
    assert all('bookmakers' not in x[1] for x in calls),calls
    assert snap['requestCount']==3,snap
    assert snap['tournamentRequestCount']==3,snap
    assert snap['quotaPolicy']['monthlyRequestLimit']==250
    assert snap['quotaPolicy']['playerPropsIncluded'] is False
    assert snap['quotaPolicy']['playerPropRequestsThisRefresh']==0
    assert 'starterStrikeoutMarkets' not in snap
    assert 'playerPropBridge' not in snap
print('PASS OddsPapi refresh uses only 3 default game-market requests and zero player-prop calls')

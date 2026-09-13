#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
service=ROOT/'services/market-service/src/model_service.py'
spec=importlib.util.spec_from_file_location('svc_join',service)
svc=importlib.util.module_from_spec(spec); spec.loader.exec_module(svc)

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    svc.DATA_DIR=td/'data'; svc.LATEST_MLB=svc.DATA_DIR/'mlb/latest.json'; svc.CACHE_DIR=td/'cache'
    svc.get_api_key=lambda:'x'
    svc.now_utc=lambda: datetime(2026,9,7,16,0,0,tzinfo=timezone.utc)
    svc.time.sleep=lambda _x: None
    cfg={
      'provider':{'oddspapi':{'moneylineBooks':['pinnacle','circasports','fanduel'],'moneylineSharpBooks':['pinnacle','circasports'],'minRefreshSeconds':0,'consensusMaxBookSkewSeconds':120}},
      'sports':{'mlb':{'tournamentId':109,'sportId':13,'markets':{'moneyline':131}}}
    }
    svc.load_config=lambda:cfg
    svc.official_mlb_schedule=lambda date:[{
      'gamePk':'823415','startTime':'2026-09-07T17:05:00Z','away':'ATL','home':'PHI','abstractState':'Preview',
      'awayStarter':'Grant Holmes','homeStarter':'Jesús Luzardo'
    }]

    prices={
      'pinnacle':(1.62,2.42),
      'circasports':(1.64,2.38),
      'fanduel':(1.58,2.50),
    }
    calls=[]
    fixture_ids={
      'pinnacle':'pin-823415',
      'circasports':'circa-823415',
      'fanduel':'fd-823415',
    }
    def payload_for(book):
        home,away=prices[book]
        return [{
          'fixtureId':fixture_ids[book],
          'participant1Id':143,'participant2Id':144,
          'participant1Name':'Philadelphia Phillies','participant2Name':'Atlanta Braves',
          'sportId':13,'tournamentId':109,'statusId':0,'startTime':'2026-09-07T17:05:00Z',
          'bookmakerOdds':{
            book:{'suspended':False,'markets':{
              '131':{'marketActive':True,'outcomes':{
                '131':{'players':{'0':{'active':True,'price':home,'bookmakerOutcomeId':'home'}}},
                '132':{'players':{'0':{'active':True,'price':away,'bookmakerOutcomeId':'away'}}},
              }}
            }}
          }
        }]
    def fake(path,params,key):
        calls.append((path,dict(params)))
        assert path=='odds-by-tournaments',path
        assert 'bookmaker' in params and 'bookmakers' not in params,params
        return payload_for(params['bookmaker'])
    svc.oddspapi_get=fake

    snap=svc.refresh_mlb(force=True)
    assert len(calls)==3,calls
    assert snap['requestCount']==3,snap
    assert snap['tournamentRequestCount']==3,snap
    assert len(snap['rows'])==1,snap['rows']
    row=snap['rows'][0]
    assert row['gamePk']=='823415',row
    assert row['canonicalAggregation']=='MLB_GAMEPK',row
    assert row['oddsPapiFixtureIds']==fixture_ids,row['oddsPapiFixtureIds']
    assert set(row['quotes'])=={'pinnacle','circasports','fanduel'},row['quotes']
    assert row['sharp'] and set(row['sharp']['books'])=={'pinnacle','circasports'},row['sharp']
    assert row['sharp']['kind']=='sharp_consensus',row['sharp']
    assert row['bestAvailable']['home']['book']=='circasports',row['bestAvailable']
    assert row['bestAvailable']['away']['book']=='fanduel',row['bestAvailable']
    assert snap['sharpReadyRowCount']==1,snap
    assert snap['twoSharpConsensusRowCount']==1,snap
    assert snap['multiBookMergedRowCount']==1,snap
    assert snap['canonicalGameCount']==1,snap
    for book in ('pinnacle','circasports','fanduel'):
        c=snap['bookCoverage'][book]
        assert c['requestOutcome']=='ok',c
        assert c['fixturesReturned']==1,c
        assert c['officialJoined']==1,c
        assert c['moneylineQuotesParsed']==1,c
        assert c['error'] is None,c
print('PASS bookmaker-specific OddsPapi fixture IDs merge by MLB gamePk into one row with 2-sharp consensus + retail best price')

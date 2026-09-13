#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/import_omega_propsmadness_nfl_ta_direct_01710.py'
spec=importlib.util.spec_from_file_location('m',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

market={'market':{'slug':'player-tackles-assists','name':'Player Tackles + Assists'}}
matches={'matches':[{'id':1,'homeTeam':{'id':10,'abbreviation':'SEA'},'awayTeam':{'id':20,'abbreviation':'NE'}}]}

live={
 'offer':{
   'matchId':1,'player':{'id':5,'firstName':'Live','lastName':'Player','teamId':10},
   'bet':{'sportsbook':{'name':'FanDuel'},'market':market['market'],'line':7.5,
          'odds':{'over':-110,'under':-110}},
   'offerType':'offer'
 }
}
no_offer={
 'offer':{
   'matchId':1,'player':{'id':6,'firstName':'Reference','lastName':'Player','teamId':20},
   'bet':{'sportsbook':None,'market':market['market'],'line':None,'odds':None},
   'referenceBet':{'sportsbook':{'name':'DraftKings'},'market':market['market'],
                   'line':5.5,'odds':{'over':-120,'under':-106}},
   'offerType':'noOffer'
 }
}
malformed={'id':'bad'}

payload={'requests':{
 'market':{'ok':True,'data':{**market,'offers':[live,no_offer]}},
 'matches':{'ok':True,'data':matches}
}}
rows,refs,q,stats=m.normalize_capture(payload)
assert len(rows)==1 and len(refs)==1 and len(q)==0
assert rows[0]['book']=='FanDuel'
assert refs[0]['classification']=='REFERENCE_ONLY_NON_EXECUTABLE'
assert refs[0]['sportsbook']=='DraftKings'
assert refs[0]['line']=='5.5'
assert refs[0]['over_odds_american']=='-120'
assert stats['referenceOnlyRows']==1
assert stats['quarantineRate']==0

# Explicit noOffer rows never count as schema drift.
payload2={'requests':{
 'market':{'ok':True,'data':{**market,'offers':[live]+[no_offer]*20}},
 'matches':{'ok':True,'data':matches}
}}
rows,refs,q,stats=m.normalize_capture(payload2)
assert len(rows)==1 and len(refs)==20 and len(q)==0

# Genuine malformed rows still count and >25% fails closed.
payload3={'requests':{
 'market':{'ok':True,'data':{**market,'offers':[live,malformed,malformed]}},
 'matches':{'ok':True,'data':matches}
}}
try:m.normalize_capture(payload3)
except ValueError as e: assert 'schema drift' in str(e)
else: raise AssertionError('genuine schema drift must fail')

print('PASS OMEGA 0.17.10 noOffer/referenceBet classification contracts')

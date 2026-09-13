#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root = Path(__file__).resolve().parents[2]
p = root/'scripts/nfl/import_omega_propsmadness_nfl_ta_direct_0177.py'
spec = importlib.util.spec_from_file_location('m', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

base_market = {'market': {'slug':'player-tackles-assists','name':'Tackles + Assists'}}
matches = {'matches': [
    {'id':1,
     'homeTeam':{'id':10,'abbreviation':'SEA'},
     'awayTeam':{'id':20,'abbreviation':'NE'}}
]}

# Valid: top-level line.
a = {
    'matchId':1,
    'player':{'id':5,'name':'A','teamId':10},
    'bet':{
        'line':7.5,
        'sportsbook':{'name':'pinnacle'},
        'odds':{'over':{'american':-110},'under':{'american':-105}}
    }
}

# Valid: line nested under side selections.
b = {
    'matchId':1,
    'player':{'id':6,'name':'B','teamId':10},
    'bet':{
        'sportsbook':{'name':'fanduel'},
        'odds':{
            'over':{'american':120,'line':8.5},
            'under':{'american':-150,'line':8.5}
        }
    }
}

# Additional valid rows so a single malformed row is <= 25%.
d = {
    'matchId':1,
    'player':{'id':7,'name':'D','teamId':20},
    'bet':{
        'line':6.5,
        'sportsbook':{'name':'circasports'},
        'odds':{'over':{'american':105},'under':{'american':-125}}
    }
}
e = {
    'matchId':1,
    'player':{'id':8,'name':'E','teamId':20},
    'bet':{
        'line':5.5,
        'sportsbook':{'name':'draftkings'},
        'odds':{'over':{'american':-115},'under':{'american':-105}}
    }
}

# Malformed metadata-like row should quarantine, not kill snapshot when <=25%.
c = {'id':'metadata','note':'not priceable'}

payload = {
    'requests': {
        'market': {'ok':True,'data':{**base_market,'offers':[a,b,d,e,c]}},
        'matches': {'ok':True,'data':matches}
    }
}
rows, q, stats = m.normalize_capture(payload)

assert len(rows) == 4
assert len(q) == 1
assert stats['quarantineRate'] == 0.2
assert rows[0]['line'] == '7.5'
assert rows[1]['line'] == '8.5'

# >25% rejected must still fail closed.
payload2 = {
    'requests': {
        'market': {'ok':True,'data':{**base_market,'offers':[a,c,c,c]}},
        'matches': {'ok':True,'data':matches}
    }
}
try:
    m.normalize_capture(payload2)
except ValueError as ex:
    assert 'schema drift' in str(ex)
else:
    raise AssertionError('high reject rate must fail closed')

print('PASS OMEGA 0.17.8 test fixture honors <=25% quarantine and >25% fail-closed boundary')

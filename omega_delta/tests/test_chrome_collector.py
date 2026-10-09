"""Offline identity, chronology, persistence and HTTP authorization contracts."""
import copy
import json
import sys
import tempfile
import io
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import Store
from app.mlb import MLB
from app.collector import ChromeCollector
from server import make_server

EXT = 'a' * 32

def iso(t): return t.isoformat().replace('+00:00','Z')

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'omega.sqlite3')
        self.mlb = MLB(self.store)
        self.collector = ChromeCollector(self.store, self.mlb)
        self.t = datetime.now(timezone.utc).replace(microsecond=0)
        self.game = {'status':'READY_RESEARCH','game_id':'849838','away':'TB','home':'NYY',
                     'start_at':iso(self.t+timedelta(hours=4)),
                     'captured_at':iso(self.t-timedelta(minutes=5)), 'snapshot_id':'fixture_forecast',
                     'forecast':{'starters':[{'player':'Max Fried','player_id':'608331','team':'NYY',
                         'expected_k':4.2,'baseline_k':4.8,'uncertainty_multiplier':1}], 'delta':[]}}
        self.store.set_setting('mlb_board',{'games':[self.game]})
        self.capture = {'leagueCode':'mlb','status':'PASS','capturedAt':iso(self.t-timedelta(minutes=1)),
            'matches':{'matches':[{'match':{'id':17375,'startDateTimestamp':(self.t+timedelta(hours=4)).timestamp(),
                'awayTeam':{'id':102,'nameAbbreviation':'TB'},'homeTeam':{'id':94,'nameAbbreviation':'NYY'}}}]},
            'pitcherBoard':[{'matchId':'17375','playerId':'8228','player':{'name':'Max Fried','teamId':'94'},
                'markets':{'player-strikeouts':{'observedAt':iso(self.t-timedelta(minutes=2)),
                    'offers':[{'sportsbook':{'name':'Fixture book'},'line':4.5,'odds':{'over':101,'under':-122}}]}}}]}

    def tearDown(self):
        self.store.db.close(); self.tmp.cleanup()

    def test_pair_scope_and_no_secret_in_state(self):
        pair=self.collector.pair(EXT)
        self.assertTrue(self.collector.authorized('chrome-extension://'+EXT,pair['token']))
        for origin,token in [('https://propsmadness.com',pair['token']),('chrome-extension://'+'b'*32,pair['token']),('chrome-extension://'+EXT,'wrong')]:
            self.assertFalse(self.collector.authorized(origin,token))
        self.assertNotIn(pair['token'],json.dumps(self.collector.state()))
        self.assertNotIn('token_sha256',json.dumps(self.collector.state()))
        self.collector.disconnect()
        self.assertFalse(self.collector.authorized('chrome-extension://'+EXT,pair['token']))

    def test_quotes_use_mlb_identity_and_duplicate_is_idempotent(self):
        r=self.collector.ingest(self.capture)
        self.assertEqual(r['priced_quotes'],2)
        q=self.store.setting('mlb_quotes')
        self.assertEqual({x['player_id'] for x in q},{'608331'})
        self.assertTrue(all(x['entry_receipt_verified'] is False for x in q))
        self.assertTrue(self.collector.ingest(self.capture)['duplicate'])
        self.assertEqual(len(self.store.setting('mlb_quotes')),2)
        self.assertEqual(self.store.setting('mlb_board')['games'][0]['forecast'],self.game['forecast'])

    def test_quote_before_forecast_is_held_but_source_saved(self):
        self.capture['pitcherBoard'][0]['markets']['player-strikeouts']['observedAt']=iso(self.t-timedelta(minutes=6))
        r=self.collector.ingest(self.capture)
        self.assertEqual(r['priced_quotes'],0)
        self.assertIn('predates forecast',r['held_quotes'][0]['reason'])
        self.assertIsNotNone(self.store.latest('chrome_capture'))

    def test_no_forecast_never_imports_price(self):
        self.game.pop('forecast');self.store.set_setting('mlb_board',{'games':[self.game]})
        self.assertEqual(self.collector.ingest(self.capture)['priced_quotes'],0)
        self.assertFalse(self.store.setting('mlb_quotes'))

    def test_wrong_name_team_or_game_cannot_join_by_propsmadness_id(self):
        for key,value in [('name','Nick Martinez'),('teamId','102')]:
            c=copy.deepcopy(self.capture);c['pitcherBoard'][0]['player'][key]=value
            self.assertEqual(self.collector.ingest(c)['priced_quotes'],0)
        c=copy.deepcopy(self.capture);c['matches']['matches'][0]['match']['startDateTimestamp']+=60
        self.assertEqual(self.collector.ingest(c)['priced_quotes'],0)

    def test_live_quote_retained_without_pregame_comparison(self):
        self.game['start_at']=iso(self.t-timedelta(minutes=3))
        self.store.set_setting('mlb_board',{'games':[self.game]})
        self.capture['matches']['matches'][0]['match']['startDateTimestamp']=(self.t-timedelta(minutes=3)).timestamp()
        r=self.collector.ingest(self.capture)
        self.assertEqual(r['priced_quotes'],0)
        self.assertIn('Live/postgame',r['held_quotes'][0]['reason'])

    def test_missing_or_future_timestamp_does_not_create_source(self):
        for value in [None,iso(self.t+timedelta(hours=1)),self.t.replace(tzinfo=None).isoformat()]:
            c=copy.deepcopy(self.capture);c['capturedAt']=value
            with self.assertRaises(ValueError):self.collector.ingest(c)
        self.assertIsNone(self.store.latest('chrome_capture'))

    def test_old_browser_boards_are_archived_without_activation_or_secrets(self):
        archive={'leagueCode':'legacy','schemaVersion':'OMEGA_CHROME_LEGACY_ARCHIVE_V1',
                 'artifacts':{'model_mlb_k_projection_board_current':{'expectedK':99}}}
        r=self.collector.ingest(archive)
        self.assertEqual(r['status'],'ARCHIVED_NOT_ACTIVATED')
        self.assertEqual(self.store.setting('mlb_board')['games'][0]['forecast'],self.game['forecast'])
        archive['artifacts']['service_token']='not-allowed'
        with self.assertRaises(ValueError):self.collector.ingest(archive)

    def test_http_pairing_csrf_origin_and_cors(self):
        # Exercise the real request handler without binding a socket in CI.
        with patch('server.ThreadingHTTPServer') as factory:
            server,_=make_server(self.store,port=8741)
            Handler=factory.call_args.args[1]
        server.server_port=8741
        base='http://127.0.0.1:8741'
        def request(path,body=None,headers=None,method=None):
            headers=dict(headers or {})
            raw=json.dumps(body).encode() if body is not None else b''
            headers.update({'Host':'127.0.0.1:8741','Content-Length':str(len(raw))})
            if body is not None:headers['Content-Type']='application/json'
            handler=object.__new__(Handler)
            handler.path=path;handler.headers=headers;handler.server=server
            handler.rfile=io.BytesIO(raw);handler.wfile=io.BytesIO()
            handler.connection=SimpleNamespace(settimeout=lambda value:None)
            response={'status':None,'headers':{}}
            handler.send_response=lambda status:response.update(status=status)
            handler.send_header=lambda name,value:response['headers'].update({name:value})
            handler.end_headers=lambda:None
            getattr(handler,'do_'+(method or ('POST' if body is not None else 'GET')))()
            return response['status'],response['headers'],handler.wfile.getvalue()
        state=json.loads(request('/api/state')[2]);self.assertIn('csrf',state);token=state['csrf']
        self.assertEqual(request('/api/collector/pair',{'extension_id':EXT})[0],403)
        status,_,raw=request('/api/collector/pair',{'extension_id':EXT},{'Origin':base,'X-Omega-Token':token})
        self.assertEqual(status,200);pair=json.loads(raw)
        origin='chrome-extension://'+EXT
        self.assertEqual(request('/api/state',headers={'Origin':origin})[0],403)
        self.assertEqual(request('/api/collector/capture',{'capture':self.capture},{'Origin':origin})[0],403)
        status,headers,_=request('/api/collector/capture',headers={'Origin':origin},method='OPTIONS')
        self.assertEqual(status,204);self.assertEqual(headers['Access-Control-Allow-Origin'],origin)
        self.assertEqual(request('/api/collector/capture',headers={'Origin':'https://example.com'},method='OPTIONS')[0],403)
        status,headers,raw=request('/api/collector/capture',{'capture':self.capture},
            {'Origin':origin,'X-Omega-Collector-Token':pair['token']})
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['priced_quotes'],2)
        self.assertEqual(headers['Access-Control-Allow-Origin'],origin)
        self.assertEqual(request('/api/collector/disconnect',{},
            {'Origin':origin,'X-Omega-Collector-Token':pair['token']})[0],403)

if __name__=='__main__':unittest.main()

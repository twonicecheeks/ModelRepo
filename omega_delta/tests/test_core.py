"""Offline acceptance contracts for the prototype. No provider quota consumed."""
from __future__ import annotations

import csv
import io
import json
import math
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.core import Store, metrics, normalize_quote, now, price_saved_distribution
from app.providers import book_metrics, monitor_market, monitor_wallet, normalize_odds_event, pages
from app.simulator import line_probabilities, simulate
from server import make_server


def quote(**changes):
    row = {"game_id":"2026_03_BAL_DAL","player_id":"00-0034982","player_name":"Roquan Smith", "book":"Test Book",
           "side":"OVER","line":7.5,"odds":-110,"captured_at":"2026-09-27T15:00:00Z", "kickoff_utc":"2026-09-27T20:25:00Z"}
    row.update(changes)
    return row


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/"test.sqlite3")

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def test_quote_deduplication_and_raw_hash(self):
        a=self.store.ingest_quotes([quote()],'{"source":"a"}',"fixture")
        b=self.store.ingest_quotes([quote()],'{"source":"a"}',"fixture")
        self.assertEqual(a["new_quotes"],1)
        self.assertEqual(b["new_quotes"],0)
        self.assertEqual(a["snapshot_id"],b["snapshot_id"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("DELETE FROM snapshots")
        self.assertEqual(len(self.store.quote_list()),1)

    def test_raw_csv_line_endings_preserved(self):
        from app.core import digest
        raw='game_id,player_id,status,observed_at,source\r\ng,p,UNKNOWN,2026-09-27T12:00:00Z,test\r\n'
        result=self.store.import_file('availability','test.csv',raw)
        self.assertEqual(self.store.latest('availability')['sha256'],digest(raw.encode()))
        self.assertEqual(self.store.latest('availability')['raw'],raw)

    def test_invalid_quote_batch_is_atomic(self):
        with self.assertRaises(ValueError):
            self.store.ingest_quotes([quote(),quote(odds=0)],"invalid","fixture")
        self.assertEqual(self.store.quote_list(),[])
        self.assertIsNone(self.store.latest("provider_quotes"))

    def test_postgame_quotes_preserved_and_marked(self):
        q=normalize_quote(quote(captured_at="2026-09-27T21:00:00Z"))
        self.assertEqual(q["phase"],"LIVE_OR_POSTGAME")
        with self.assertRaises(ValueError):
            normalize_quote(quote(captured_at="2026-09-27T15:00:00"))

    def add_bet(self, **changes):
        b={"ticket_id":"TEST-1","book":"Test Book","selection":"Player over 7.5","kind":"SINGLE","side":"OVER","line":7.5,
           "odds":-110,"stake":11,"placed_at":"2026-09-27T15:20:00Z"}
        b.update(changes)
        return self.store.add_bet(b)["id"]

    def test_ticket_stake_math_and_append_only_corrections(self):
        bid=self.add_bet()
        self.store.settle_bet(bid,{"result":"WIN","source":"test receipt"})
        b=self.store.bet_list()[0]
        self.assertEqual((b["stake_cents"],b["payout_cents"],b["pnl_cents"]),(1100,2100,1000))
        self.store.settle_bet(bid,{"result":"VOID","source":"test correction"})
        b=self.store.bet_list()[0]
        self.assertEqual(b["pnl_cents"],0)
        self.assertEqual(len(b["events"]),2)
        with self.assertRaises(ValueError):
            self.add_bet()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("UPDATE bets SET placed_at='changed'")

    def test_positive_odds_push_cashout(self):
        bid=self.add_bet(odds=150,stake=10)
        self.store.settle_bet(bid,{"result":"WIN","source":"receipt"})
        self.assertEqual(self.store.bet_list()[0]["payout_cents"],2500)
        self.store.settle_bet(bid,{"result":"PUSH","source":"corrected"})
        self.assertEqual(self.store.bet_list()[0]["pnl_cents"],0)
        self.store.settle_bet(bid,{"result":"CASHOUT","payout":6.25,"source":"cashout receipt"})
        self.assertEqual(self.store.bet_list()[0]["pnl_cents"],-375)

    def test_clv_uses_same_line_book_and_only_pregame_after_placement(self):
        self.store.ingest_quotes([quote()],"first","fixture")
        first=self.store.quote_list()[0]
        self.add_bet(quote_id=first["id"])
        self.store.ingest_quotes([quote(odds=-130,captured_at="2026-09-27T20:20:00Z"),
                                  quote(odds=200,captured_at="2026-09-27T21:00:00Z"),
                                  quote(odds=-150,line=8.5,captured_at="2026-09-27T20:24:00Z")],"later","fixture")
        b=self.store.bet_list()[0]
        self.assertEqual(b["clv"]["price"],-130)
        self.assertGreater(b["clv"]["implied_probability_delta"],0)

    def test_link_does_not_accept_postplacement_or_mismatched_quotes(self):
        self.store.ingest_quotes([quote()],"first","fixture")
        q=self.store.quote_list()[0]
        with self.assertRaises(ValueError):
            self.add_bet(quote_id=q["id"],placed_at="2026-09-27T14:00:00Z")
        with self.assertRaises(ValueError):
            self.add_bet(quote_id=q["id"],odds=-120)

    def test_restart_preserves_actual_ticket(self):
        self.add_bet()
        other=Store(self.store.path)
        self.assertEqual(len(other.bet_list()),1)
        other.db.close()

    def test_invalid_numbers_and_fractional_pennies_rejected(self):
        for bad in ("NaN","Infinity",-1):
            with self.assertRaises(ValueError):
                self.add_bet(stake=bad)
        with self.assertRaises(ValueError):
            self.add_bet(stake=1.001)


class RealArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.store=Store(Path(cls.temp.name)/"test.sqlite3",ROOT/"seed")

    @classmethod
    def tearDownClass(cls):
        cls.store.db.close();cls.temp.cleanup()

    def test_actual_counts_and_participation_bias(self):
        control=[r for r in self.store.records("scores") if r["forecast_track"]=="CONTROL"]
        matched=[r for r in control if r["defensive_participant"].lower()=="true"]
        self.assertEqual(len(control),1046)
        self.assertEqual(len(matched),788)
        self.assertAlmostEqual(metrics(control)["bias"],0.5829704523,places=7)
        self.assertAlmostEqual(metrics(matched)["bias"],0.0807393168,places=7)
        self.assertEqual(len(self.store.records("forecasts")),749)
        self.assertEqual(self.store.bet_list(),[])
        self.assertEqual(self.store.quote_list(),[])

    def test_roles_are_not_counted_as_extra_unique_forecasts(self):
        rows=self.store.records("scores")
        self.assertEqual(len(rows),1846)
        self.assertEqual(len({(r["game_id"],r["player_id"]) for r in rows}),1046)

    def test_joint_simulation_zero_participation_credit_constraints_and_replay(self):
        rows=self.store.records("forecasts")
        players=sorted([r for r in rows if r["game_id"]=="2026_03_BAL_DAL" and r["team"]=="BAL"],key=lambda r:float(r["role_point_xtc"]),reverse=True)
        pair=[r["player_id"] for r in players[:2]]
        cfg={"game_id":"2026_03_BAL_DAL","team":"BAL","pair":pair,"draws":400,"availability":{pair[0]:0,pair[1]:1},"lines":[6,6.5]}
        a=simulate(rows,cfg);b=simulate(rows,cfg)
        self.assertEqual(a,b)
        self.assertTrue(a["team"]["max_credit_bound_pass"])
        self.assertEqual(a["pair"]["players"][0]["mean"],0)
        self.assertIsNone(a["pair"]["correlation"])
        for p in a["pair"]["probabilities"]:
            self.assertAlmostEqual(sum(p.values()),1)
        self.assertAlmostEqual(sum(r["mean"] for r in a["players"]),a["team"]["mean_credits"])

    def test_saved_input_is_not_modified_by_scenario(self):
        before=self.store.latest("forecasts")["sha256"]
        rows=self.store.records("forecasts")
        simulate(rows,{"game_id":"2026_03_BAL_DAL","team":"BAL","draws":200})
        self.assertEqual(self.store.latest("forecasts")["sha256"],before)

    def test_integer_push_probability(self):
        self.assertEqual(line_probabilities([5,6,6,7],6),{"over":.25,"under":.25,"push":.5})
        self.assertEqual(line_probabilities([5,6,6,7],6.5),{"over":.25,"under":.75,"push":0})

    def test_pricing_includes_push_and_does_not_extrapolate(self):
        f={"control_p_over_5_5":.75,"control_p_over_6_5":.25}
        over=price_saved_distribution(f,6,"OVER",100)
        under=price_saved_distribution(f,6,"UNDER",100)
        self.assertEqual(over["push"],.5)
        self.assertEqual(over["expected_roi"],0)
        self.assertEqual(under["win"],.25)
        with self.assertRaises(ValueError):price_saved_distribution(f,20.5,"OVER",-110)


class ProviderContractTests(unittest.TestCase):
    def test_book_sorting_depth_slippage_and_empty_book(self):
        book={"bids":[{"price":".4","size":"100"},{"price":".48","size":"20"}],
              "asks":[{"price":".7","size":"100"},{"price":".5","size":"100"}]}
        m=book_metrics(book,100)
        self.assertEqual(m["best_bid"],.48)
        self.assertEqual(m["best_ask"],.5)
        self.assertEqual(m["ask_depth_dollars_2c"],50)
        self.assertAlmostEqual(m["hypothetical_buy"]["average_price"],100/(100+50/.7))
        self.assertTrue(m["hypothetical_buy"]["fully_filled"])
        e=book_metrics({"asks":[],"bids":[]})
        self.assertIsNone(e["spread"])
        self.assertFalse(e["hypothetical_buy"]["fully_filled"])

    def test_pagination_preserves_wallet_anchor_and_marks_truncation(self):
        calls=[]
        def fetch(base,path,params):
            calls.append(params)
            return {"data":[{"current_value":1}],"pagination":{"next_cursor":"c"+str(len(calls))}}, {}, '{}'
        rows,pg,raws=pages('/v2/positions',{"user":"0x"+"a"*40},fetch,limit_pages=2)
        self.assertEqual(len(rows),2)
        self.assertTrue(pg["truncated"])
        self.assertEqual(calls[1]["user"],"0x"+"a"*40)
        self.assertEqual(calls[1]["cursor"],"c1")

    def test_wallet_attribution_is_not_resting_order_identity(self):
        def fetch(base,path,params):
            if path=='/book':
                d={"asset_id":"123","market":"0x"+"b"*64,"bids":[{"price":.4,"size":10}],"asks":[{"price":.5,"size":20}]}
            else:
                self.assertEqual(params['taker_only'],'false')
                d={"data":[{"condition_id":"0x"+"b"*64,"token_id":"123","proxy_wallet":"0x"+"a"*40,"price":.5,"size":10,"side":"BUY"}],"pagination":{"next_cursor":None}}
            return d,{},json.dumps(d)
        r,_=monitor_market("123","0x"+"b"*64,fetch)
        self.assertEqual(r["resting_order_wallets"],"NOT_PUBLIC")
        self.assertEqual(r["wallets"][0]["role"],"FILL_PARTICIPANT; MAKER_ROLE_UNVERIFIED")

    def test_odds_adapter_preserves_both_sides_and_unknown_identity(self):
        event={"id":"fixture-event","home_team":"Dallas Cowboys","away_team":"Baltimore Ravens","commence_time":"2026-09-27T20:25:00Z",
               "bookmakers":[{"title":"Test","markets":[{"key":"player_tackles_assists","outcomes":[{"name":"Over","description":"Unknown defender","price":-110,"point":6.5},{"name":"Under","description":"Unknown defender","price":-110,"point":6.5}]}]}]}
        q=normalize_odds_event(event,[],"2026-09-27T15:00:00Z")
        self.assertEqual(len(q),2)
        self.assertEqual(q[0]["player_id"],"")
        self.assertEqual(q[0]["game_id"],"ODDS:fixture-event")


class ServerTests(unittest.TestCase):
    def test_http_import_ticket_and_simulation_workflow(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.sqlite3',ROOT/'seed')
            server,collector=make_server(store,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                state=json.load(urllib.request.urlopen(base+'/api/state'))
                def post(path,body):
                    req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Omega-Token':state['csrf']})
                    return json.load(urllib.request.urlopen(req))
                b=post('/api/bets',{'ticket_id':'HTTP-TEST','book':'Fixture','selection':'Test only','kind':'SINGLE','side':'OVER','line':6.5,'odds':-110,'stake':11,'placed_at':'2026-09-27T12:00:00Z'})
                post('/api/bets/settle',{'id':b['id'],'result':'WIN','source':'test fixture'})
                r=post('/api/simulate',{'game_id':'2026_03_BAL_DAL','team':'BAL','draws':200})
                self.assertEqual(r['status'],'UNTRAINED_SCENARIO')
                self.assertTrue(r['snapshot_id'].startswith('simulation_'))
                again=json.load(urllib.request.urlopen(base+'/api/state'))
                self.assertEqual(again['bets'][0]['pnl_cents'],1000)
                self.assertEqual(again['last_simulation']['snapshot_id'],r['snapshot_id'])
                export=json.load(urllib.request.urlopen(base+'/api/export'))
                self.assertEqual(len(export['tables']['bets']),1)
                self.assertEqual(urllib.request.urlopen(base+'/').status,200)
                self.assertEqual(urllib.request.urlopen(base+'/app.js').status,200)
            finally:
                server.shutdown();server.server_close();store.db.close()

    def test_health_csrf_origin_and_static_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.sqlite3')
            server,collector=make_server(store,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                state=json.load(urllib.request.urlopen(base+'/api/state'))
                req=urllib.request.Request(base+'/api/poly/auto',data=b'{"enabled":true}',headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req)
                self.assertEqual(ctx.exception.code,403)
                req.add_header('X-Omega-Token',state['csrf'])
                self.assertTrue(json.load(urllib.request.urlopen(req))['enabled'])
                req.add_header('Origin','https://unrelated.example')
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'/../server.py')
            finally:
                server.shutdown();server.server_close();store.db.close()


if __name__=='__main__':
    unittest.main(verbosity=2)

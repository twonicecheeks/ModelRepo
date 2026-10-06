#!/usr/bin/env python3
"""Launch OMEGA Next on localhost. No build tools or pip dependencies required."""
from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.core import Store, bounded, canonical, now
from app.providers import Collector, ProviderError, discover_markets
from app.simulator import simulate
from app.validation import evaluate, grade_observations
from app.operations import InstanceLock, Jobs, restore_database
from app.mlb import MLB

ROOT = Path(__file__).resolve().parent


def make_server(store, host="127.0.0.1", port=8741):
    collector = Collector(store)
    token = secrets.token_urlsafe(32)
    jobs = Jobs(store)
    mlb = MLB(store)
    simulation_lock=threading.Lock()

    def run_simulation(body):
        if not simulation_lock.acquire(False): raise ValueError('A simulation is already running.')
        try:
            with store.lock:
                rows=store.records('forecasts')
                snapshot_id=store.setting('active_forecast') or (store.latest('forecasts') or {}).get('id')
            result=simulate(rows,body)
            result.update(created_at=now(),input_snapshot_id=snapshot_id)
            result['snapshot_id']=store.snapshot('simulation','Joint scenario '+str(body.get('game_id')),canonical(result))
            store.set_setting('last_simulation',result)
            return result
        finally: simulation_lock.release()

    def run_validation():
        report=evaluate(store.records('scores'))
        report['snapshot_id']=store.snapshot('validation','Chronological calibration evaluation',canonical(report))
        store.set_setting('last_validation',report)
        return report

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # No query strings or ticket content in terminal logs.
            pass

        def send(self, data, status=200, mime="application/json", filename=None):
            if not isinstance(data, bytes):
                data = canonical(data).encode() if mime=="application/json" else str(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):
                pass

        def safe_host(self):
            expected = {f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}
            return self.headers.get("Host") in expected

        def do_GET(self):
            if not self.safe_host() or self.headers.get('Sec-Fetch-Site')=='cross-site':
                return self.send({"error":"Local access only."},403)
            path = urllib.parse.urlsplit(self.path).path
            try:
                if path == "/api/health":
                    return self.send({"app":"OMEGA Next","ok":True})
                if path == "/api/state":
                    data = store.state()
                    data.update(csrf=token,odds_key_configured=bool(collector.key),odds_last=store.setting("odds_last",{}),
                                odds_last_failure=store.setting('odds_last_failure'),
                                odds_quota=store.setting("odds_quota",{}),odds_budget=store.setting("odds_budget",{}),jobs=jobs.recent())
                    data['mlb']=mlb.state()
                    return self.send(data)
                if path == '/api/mlb/report':
                    return self.send(mlb.report,filename='OMEGA_V2_MLB_BACKTEST.json')
                if path == '/api/mlb/quote-template.csv':
                    return self.send('game_id,market_type,player_id,side,line,odds,book,captured_at,source,settlement_definition\n',mime='text/csv',filename='MLB_QUOTE_TEMPLATE.csv')
                if path == '/api/mlb/frozen':
                    return self.send(mlb.frozen,filename='OMEGA_V2_MLB_FROZEN_MODEL.json')
                if path == '/api/delta/report':
                    return self.send(mlb.delta.report,filename='DELTA_BACKTEST_REPORT.json')
                if path == '/api/delta/escalator-report':
                    return self.send(mlb.delta.counterfactual,filename='DELTA_ESCALATOR_EXPERIMENT.json')
                if path == '/api/delta/frozen':
                    return self.send(mlb.delta.frozen,filename='DELTA_FROZEN_MODEL.json')
                if path == '/api/delta/input-template.json':
                    return self.send((ROOT/'examples/DELTA_INPUT_TEMPLATE.json').read_bytes(),filename='DELTA_INPUT_TEMPLATE.json')
                if path == '/api/delta/data-sources.md':
                    return self.send((ROOT/'DELTA_DATA_SOURCES.md').read_bytes(),mime='text/markdown; charset=utf-8',filename='DELTA_DATA_SOURCES.md')
                if path == '/api/delta/market-template.csv':
                    return self.send((ROOT/'examples/DELTA_MARKET_TEMPLATE.csv').read_bytes(),mime='text/csv',filename='DELTA_MARKET_TEMPLATE.csv')
                if path == '/api/delta/market-audit':
                    audit = ROOT/'audit/delta/MARKET_AUDIT_0.1.3.json'
                    if not audit.is_file(): return self.send({'error':'No local market audit has been supplied.'},404)
                    return self.send(audit.read_bytes(),filename='DELTA_MARKET_AUDIT_0.1.3.json')
                if path == '/api/quote/compare':
                    qid=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id',[''])[0]
                    return self.send(store.compare_quote(qid))
                if path == '/api/job':
                    jid=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('id',[''])[0]
                    return self.send(jobs.get(jid))
                if path == '/api/backup.sqlite3':
                    return self.send(store.database_backup(),mime='application/vnd.sqlite3',filename='OMEGA_BACKUP_'+now()[:10]+'.sqlite3')
                if path == "/api/export":
                    return self.send(store.backup(),filename="OMEGA_NEXT_BACKUP.json")
                if path == "/api/bets.csv":
                    buff = io.StringIO()
                    fields = ["id","ticket_id","book","selection","kind","side","line","odds","stake","placed_at","result","payout","profit","model_snapshot_id","quote_snapshot_id"]
                    w = csv.DictWriter(buff,fields)
                    w.writeheader()
                    for b in store.bet_list():
                        row = {k:b.get(k,"") for k in fields}
                        row.update(stake=b["stake_cents"]/100,payout=b["payout_cents"]/100,profit=b["pnl_cents"]/100)
                        # Defuse spreadsheet formula injection in user-entered text.
                        for k,v in row.items():
                            if isinstance(v,str) and v.startswith(("=","+","-","@","\t","\r")):
                                row[k] = "'"+v
                        w.writerow(row)
                    return self.send(buff.getvalue(),mime="text/csv",filename="OMEGA_ACTUAL_BETS.csv")
                if path == "/api/quote-template.csv":
                    return self.send("game_id,player_id,player_name,team,book,side,line,odds,captured_at,kickoff_utc,market,source,settlement_definition\n",mime="text/csv",filename="OMEGA_QUOTE_TEMPLATE.csv")
                if path == "/api/snapshot":
                    sid = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("id",[""])[0]
                    with store.lock:
                        r = store.db.execute("SELECT * FROM snapshots WHERE id=?",(sid,)).fetchone()
                    if not r:
                        return self.send({"error":"Snapshot not found"},404)
                    ext = ".csv" if r["kind"] in {"forecasts","scores","quotes","legacy_market","definition","availability","outcomes"} else ".json"
                    return self.send(r["raw"].encode(),mime="text/csv" if ext==".csv" else "application/json",filename=r["id"]+ext)
                target = ROOT/"web"/("index.html" if path=="/" else path.lstrip("/"))
                resolved = target.resolve()
                if not resolved.is_relative_to((ROOT/"web").resolve()) or not resolved.is_file():
                    return self.send({"error":"Not found"},404)
                return self.send(resolved.read_bytes(),mime=mimetypes.guess_type(str(resolved))[0] or "application/octet-stream")
            except (ValueError,KeyError) as e:
                self.send({'error':str(e)},400)
            except Exception:
                traceback.print_exc()
                self.send({"error":"Request failed; check the local terminal."},500)

        def do_POST(self):
            origin = self.headers.get("Origin")
            if not self.safe_host() or self.headers.get("X-Omega-Token") != token or (origin and origin not in {f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"}):
                return self.send({"error":"Session changed. Refresh OMEGA and try again."},403)
            try:
                self.connection.settimeout(20)
                if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('Use application/json.')
                length = int(self.headers.get("Content-Length",0))
                if length<=0 or length>22_000_000:
                    raise ValueError("Request must be between 1 byte and 22 MB.")
                b = json.loads(self.rfile.read(length))
                if not isinstance(b,dict):
                    raise ValueError("Request must be a JSON object.")
                path = urllib.parse.urlsplit(self.path).path
                if path == "/api/import":
                    result = store.import_file(b["kind"],b.get("name","import.csv"),b["raw"])
                    store.log("IMPORT","OK",f"{b['kind']}: {result['rows']} rows")
                elif path == "/api/bets":
                    result = store.add_bet(b)
                elif path == "/api/bets/settle":
                    result = store.settle_bet(b["id"],b)
                elif path == '/api/bets/amend':
                    result=store.amend_bet(b['id'],b)
                elif path == '/api/forecasts/activate':
                    result=store.activate_forecast(b['id'])
                elif path == "/api/simulate":
                    result = run_simulation(b)
                elif path == '/api/jobs':
                    kind=b.get('kind')
                    actions={'simulation':lambda:run_simulation(b.get('config',{})),
                             'capture':collector.odds_capture,'polymarket':collector.poly_capture,
                             'validation':run_validation,'grading':lambda:grade_observations(store),
                             'historical_capture':lambda:collector.odds_capture(b.get('as_of')),
                             'mlb_refresh':lambda:mlb.operation('refresh',b.get('date')),
                             'mlb_grade':lambda:mlb.operation('grade'),
                             'delta_simulation':lambda:mlb.delta.simulate(b.get('config',{})),
                             'delta_grade':lambda:mlb.operation('delta_grade')}
                    if kind not in actions: raise ValueError('Unknown job type.')
                    if kind=='historical_capture' and not b.get('as_of'): raise ValueError('Historical capture requires an as-of timestamp.')
                    result=jobs.start(kind,actions[kind])
                elif path == '/api/mlb/quotes':
                    result=mlb.import_quotes(b['raw'],b.get('name','mlb-quotes.csv'))
                elif path == '/api/delta/profiles':
                    result=mlb.delta.import_profiles(b['raw'],b.get('name','delta-profiles.json'))
                elif path == "/api/capture/settings":
                    cfg = {"enabled":bool(b.get("enabled")),"interval_seconds":int(bounded(b.get("interval_seconds",900),60,86400)),
                           "max_events":int(bounded(b.get("max_events",16),1,32)),"daily_call_cap":int(bounded(b.get("daily_call_cap",60),1,10000))}
                    if b.get("api_key"):
                        collector.key = str(b["api_key"]).strip()
                    if b.get('clear_key'): collector.key=''
                    if cfg["enabled"] and not collector.key:
                        raise ValueError("An API key is needed to enable scheduled capture.")
                    store.set_setting("capture",cfg)
                    result = {"saved":True,"api_key_persistence":"SESSION_ONLY; use OMEGA_ODDS_API_KEY for restarts"}
                elif path == "/api/capture/run":
                    result = collector.odds_capture()
                elif path == "/api/poly/search":
                    result,raw = discover_markets(b.get("query","NFL"))
                    store.snapshot("polymarket_search",b.get("query","NFL"),raw)
                elif path == "/api/poly/watch":
                    token_id,condition = str(b.get("token_id","")),str(b.get("condition_id",""))
                    if not re.fullmatch(r"[0-9]{1,100}",token_id):
                        raise ValueError("Choose a result with a decimal token ID.")
                    if condition and not re.fullmatch(r"0x[0-9a-fA-F]{64}",condition):
                        raise ValueError("Invalid condition ID.")
                    watches = [w for w in store.setting("poly_watch",[]) if w["token_id"]!=token_id]
                    if not b.get("remove"):
                        if len(watches)>=8:
                            raise ValueError("Version 1 supports eight watched outcomes.")
                        watches.append({"token_id":token_id,"condition_id":condition,"label":str(b.get("label",token_id))[:200]})
                    store.set_setting("poly_watch",watches)
                    result = {"watches":watches}
                elif path == "/api/poly/wallet":
                    address = str(b.get("address",""))
                    if not re.fullmatch(r"0x[0-9a-fA-F]{40}",address):
                        raise ValueError("Enter a valid public wallet address.")
                    watches = [w for w in store.setting("wallet_watch",[]) if w["address"].lower()!=address.lower()]
                    if not b.get("remove"):
                        if len(watches)>=8:
                            raise ValueError("Version 1 supports eight watched wallets.")
                        watches.append({"address":address,"label":str(b.get("label",address))[:100]})
                    store.set_setting("wallet_watch",watches)
                    result = {"watches":watches}
                elif path == "/api/poly/refresh":
                    result = collector.poly_capture()
                elif path == "/api/poly/auto":
                    store.set_setting("poly_auto",bool(b.get("enabled")))
                    result = {"enabled":bool(b.get("enabled"))}
                else:
                    return self.send({"error":"Unknown action"},404)
                self.send(result)
            except (ValueError,KeyError,TypeError,csv.Error,ProviderError) as e:
                self.send({"error":str(e)},400)
            except Exception:
                traceback.print_exc()
                self.send({"error":"Operation failed; check the local terminal."},500)

    srv = ThreadingHTTPServer((host,port),Handler)
    srv.daemon_threads = True
    return srv,collector


def main():
    default_data = (Path.home()/"Library"/"Application Support"/"OMEGA Next") if sys.platform=="darwin" else Path.home()/".local"/"share"/"omega-next"
    parser = argparse.ArgumentParser(description="OMEGA 2.1.3 / DELTA 0.1 — local sports research and records")
    parser.add_argument("--port",type=int,default=8741)
    parser.add_argument("--data-dir",type=Path,default=default_data)
    parser.add_argument("--no-open",action="store_true")
    parser.add_argument('--restore-backup',type=Path,help='Restore a SQLite backup into an empty data directory.')
    args = parser.parse_args()
    try:
        instance=InstanceLock(args.data_dir/'server.lock')
        if args.restore_backup: restore_database(args.restore_backup,args.data_dir/'omega.sqlite3')
        store = Store(args.data_dir/"omega.sqlite3",ROOT/"seed")
        if not store.setting('v2_upgrade_backup'):
            backup=args.data_dir/'omega.pre-v2.sqlite3'
            if not backup.exists():
                with backup.open('xb') as out:out.write(store.database_backup())
                os.chmod(backup,0o600)
            store.set_setting('v2_upgrade_backup',str(backup))
        if not store.setting('delta_upgrade_backup'):
            backup=args.data_dir/'omega.pre-delta-0.1.sqlite3'
            if not backup.exists():
                with backup.open('xb') as out:out.write(store.database_backup())
                os.chmod(backup,0o600)
            store.set_setting('delta_upgrade_backup',str(backup))
    except (ValueError,sqlite3.DatabaseError) as e:
        print(str(e),file=sys.stderr);return 1
    try:
        server,collector = make_server(store,port=args.port)
    except OSError as e:
        print(f"Cannot open port {args.port}: {e}. Try --port 8742.",file=sys.stderr)
        instance.close();store.db.close()
        return 1
    collector.start()
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"\nOMEGA 2.1.3 / DELTA 0.1 is running: {url}\nYour records: {store.path}\nMLB candidates: research; betting edge unverified.\nLeave this terminal open for automatic capture. Ctrl+C stops it.\n",flush=True)
    if not args.no_open:
        threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop.set()
        server.server_close()
        for thread in getattr(collector,'threads',[]): thread.join(timeout=1)
        # Provider I/O has a bounded timeout. The process owns the DB until it
        # exits; leaving an in-flight daemon cannot unlock it for a second app.
        instance.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

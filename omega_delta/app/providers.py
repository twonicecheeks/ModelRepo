"""Read-only provider adapters. No sportsbook order submission or wallet keys."""
from __future__ import annotations

import csv
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import bounded, canonical, digest, now, number, stamp

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"
ODDS = "https://api.the-odds-api.com"


class ProviderError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("Unexpected provider redirect; verify the adapter endpoint.")


def request_json(base, path, params=None):
    if base not in {GAMMA, CLOB, DATA, ODDS}:
        raise ValueError("Provider host is not supported.")
    # Normal system certificate verification. Existing certifi installations are
    # used on Macs whose framework Python has no installed CA store.
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    url = base+path+("?"+urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "OMEGA-Next/1.0 (read-only research)"})
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=context))
    try:
        with opener.open(req, timeout=18) as response:
            raw = response.read(12_000_001)
            if len(raw)>12_000_000:
                raise ProviderError("Provider response exceeded 12 MB.")
            data = json.loads(raw)
            return data, dict(response.headers), raw.decode()
    except urllib.error.HTTPError as e:
        if e.code in (401,403):
            raise ProviderError(f"{urllib.parse.urlparse(base).hostname} refused access (HTTP {e.code}). Check provider access; no bypass attempted.") from None
        if e.code == 429:
            raise ProviderError("Provider rate limit reached (429). Wait before refreshing.") from None
        raise ProviderError(f"Provider returned HTTP {e.code}.") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            raise ProviderError("Verified TLS certificate bundle unavailable. Use the existing MODEL phase1b Python, or install certifi in your Python environment.") from None
        raise ProviderError(f"Provider connection failed: {type(e).__name__}. No fresh data was captured.") from None


def parse_array(x):
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        try:
            v = json.loads(x)
            return v if isinstance(v,list) else []
        except json.JSONDecodeError:
            return []
    return []


def discover_markets(query, fetch=request_json):
    q = str(query).strip()
    if not 2 <= len(q) <= 100:
        raise ValueError("Enter a team, matchup, or market search (2–100 characters).")
    data, headers, raw = fetch(GAMMA, "/public-search", {"q": q, "limit_per_type": 8,
                               "events_status":"active", "keep_closed_markets":0})
    if not isinstance(data,dict) or not isinstance(data.get('events') or [],list):
        raise ProviderError('Search returned an invalid event envelope.')
    out = []
    for e in data.get("events") or []:
        if e.get('closed'): continue
        for m in e.get("markets") or []:
            if m.get('closed'): continue
            tokens, outcomes = parse_array(m.get("clobTokenIds")), parse_array(m.get("outcomes"))
            if len(tokens) != len(outcomes):
                continue
            for token,outcome in zip(tokens,outcomes):
                out.append({"event": e.get("title", ""), "question": m.get("question", ""), "outcome": outcome,
                            "token_id": str(token), "condition_id": m.get("conditionId", ""), "slug": m.get("slug", ""),
                            "closed": False, "end_date": m.get("endDate", ""), "liquidity": number(m.get("liquidity"),None)})
    return {"markets": out[:120], "captured_at": now(),
            "truncated":len(out)>120 or bool((data.get('pagination') or {}).get('hasMore')),
            "scope": "Active search sample, up to 120 outcomes; not a complete NFL market inventory."}, raw


def book_metrics(raw, spend=100):
    if not isinstance(raw,dict) or not isinstance(raw.get('bids'),list) or not isinstance(raw.get('asks'),list):
        raise ProviderError('Order-book response must contain bids and asks arrays.')
    spend=bounded(spend,.01,1000000)
    def levels(key, reverse):
        grouped = defaultdict(float)
        for row in raw.get(key, []):
            price, size = bounded(row.get("price"),0,1), bounded(row.get("size"),0,1e15)
            if not (0<=price<=1) or size<0:
                raise ProviderError("Invalid order-book level.")
            if size:
                grouped[price] += size
        return [{"price":p,"size":s} for p,s in sorted(grouped.items(), reverse=reverse)]
    bids, asks = levels("bids", True), levels("asks", False)
    bid, ask = (bids[0]["price"] if bids else None), (asks[0]["price"] if asks else None)
    spread = ask-bid if bid is not None and ask is not None else None
    bid_band = [r for r in bids if bid is not None and r["price"] >= bid-.02000001]
    ask_band = [r for r in asks if ask is not None and r["price"] <= ask+.02000001]
    bsize, asize = sum(r["size"] for r in bid_band), sum(r["size"] for r in ask_band)
    remaining, shares = float(spend), 0.0
    for r in asks:
        if r["price"] <= 0:
            continue
        dollars = min(remaining, r["size"]*r["price"])
        shares += dollars/r["price"]
        remaining -= dollars
        if remaining <= 1e-9:
            break
    spent = spend-remaining
    return {"bids": bids, "asks": asks, "best_bid": bid, "best_ask": ask, "spread": spread,
            "midpoint": (bid+ask)/2 if bid is not None and ask is not None else None,
            "crossed": spread is not None and spread<0,
            "bid_depth_shares_2c": bsize, "ask_depth_shares_2c": asize,
            "bid_depth_dollars_2c": sum(r["price"]*r["size"] for r in bid_band),
            "ask_depth_dollars_2c": sum(r["price"]*r["size"] for r in ask_band),
            "imbalance_2c": (bsize-asize)/(bsize+asize) if bsize+asize else None,
            "hypothetical_buy": {"budget": spend, "spent": spent, "shares": shares, "average_price": spent/shares if shares else None,
                                 "fully_filled": remaining<.000001, "fees_included": False},
            "book_timestamp": raw.get("timestamp"), "hash": raw.get("hash"), "captured_at": now()}


def pages(path, params, fetch=request_json, limit_pages=3):
    rows, raws, cursor = [], [], None
    seen_cursors=set()
    for page in range(limit_pages):
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        else:
            query["limit"] = 200
        data, _, raw = fetch(DATA, path, query)
        if not isinstance(data,dict) or not isinstance(data.get("data"),list):
            raise ProviderError("Unexpected Polymarket v2 response. Adapter needs review.")
        rows.extend(data["data"])
        raws.append(raw)
        pagination=data.get('pagination')
        if not isinstance(pagination,dict): raise ProviderError('Missing pagination envelope.')
        cursor = pagination.get("next_cursor")
        if cursor and cursor in seen_cursors: raise ProviderError('Provider repeated a pagination cursor; sample was not extended.')
        if cursor: seen_cursors.add(cursor)
        if pagination.get('has_more') and not cursor: raise ProviderError('Incomplete pagination: has_more without a cursor.')
        if not cursor:
            break
    return rows, {"truncated": bool(cursor), "next_cursor": cursor, "pages": len(raws)}, raws


def monitor_market(token, condition="", fetch=request_json):
    if not re.fullmatch(r"[0-9]{1,100}", str(token)):
        raise ValueError("A decimal CLOB token ID is required.")
    if condition and not re.fullmatch(r"0x[0-9a-fA-F]{64}", condition):
        raise ValueError("Invalid condition ID.")
    data, _, raw = fetch(CLOB, "/book", {"token_id":token})
    if not isinstance(data,dict): raise ProviderError('Order-book response is not an object.')
    if str(data.get('asset_id','')) != str(token): raise ProviderError('Order-book asset ID does not match the watched outcome.')
    book_condition=data.get('market','')
    if not re.fullmatch(r'0x[0-9a-fA-F]{64}',book_condition): raise ProviderError('Book has no valid condition ID.')
    if condition and condition.lower()!=book_condition.lower(): raise ProviderError('Condition ID does not match this outcome; correct the watch entry.')
    condition=book_condition
    result = book_metrics(data)
    result.update(token_id=token, condition_id=condition or data.get("market", ""), resting_order_wallets="NOT_PUBLIC")
    raws, wallets = [raw], defaultdict(lambda: {"trades":0,"notional":0,"buy_notional":0,"sell_notional":0})
    if condition:
        try:
            trades, paging, trade_raws = pages("/v2/trades", {"condition":condition,"taker_only":"false"}, fetch)
            raws += trade_raws
            for t in trades:
                if t.get('condition_id','').lower()!=condition.lower(): raise ProviderError('Trade sample returned a different condition.')
                if str(t.get('token_id','')) != str(token): continue
                w = t.get("proxy_wallet", "")
                if not re.fullmatch(r"0x[0-9a-fA-F]{40}",w):
                    continue
                v = bounded(t.get("price"),0,1)*bounded(t.get("size"),0,1e15)
                wallets[w]["trades"] += 1
                wallets[w]["notional"] += v
                side = str(t.get("side", "")).lower()
                if side in {"buy","sell"}:
                    wallets[w][side+"_notional"] += v
            result.update(wallets=[dict(v,wallet=k,role="FILL_PARTICIPANT; MAKER_ROLE_UNVERIFIED") for k,v in sorted(wallets.items(),key=lambda kv:kv[1]["notional"],reverse=True)[:20]],
                          trade_pagination=paging, trade_sample_rows=len(trades),
                          trade_sample_note="Up to 600 market fill-side rows, filtered to this outcome. Both sides may appear; not total market volume or resting-order ownership.")
        except ProviderError as e:
            result["wallet_error"] = str(e)
    result.setdefault("wallets", [])
    return result, canonical(raws)


def monitor_wallet(address, fetch=request_json):
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise ValueError("Wallet must be a public 0x address with 40 hex characters.")
    positions, pp, rawp = pages("/v2/positions", {"user":address,"status":"OPEN"}, fetch)
    activity, pa, rawa = pages("/v2/activity", {"user":address}, fetch)
    for row in positions+activity:
        if not isinstance(row,dict) or str(row.get('proxy_wallet','')).lower()!=address.lower():
            raise ProviderError('Wallet response contains a missing or different wallet identity.')
    def sample_total(field):
        if any(r.get(field) in (None,'') for r in positions): return None
        return sum(number(r[field]) for r in positions)
    return {"address": address, "captured_at": now(), "positions": positions, "activity": activity,
            "positions_pagination": pp, "activity_pagination": pa,
            "sample_position_value": sample_total('current_value'),
            "sample_realized_pnl": sample_total('realized_pnl'),
            "scope": "Returned open-position sample only; not whole-wallet lifetime P&L."}, canonical(rawp+rawa)


TEAM_CODES = dict(zip(
    ["Arizona Cardinals","Atlanta Falcons","Baltimore Ravens","Buffalo Bills","Carolina Panthers","Chicago Bears","Cincinnati Bengals","Cleveland Browns","Dallas Cowboys","Denver Broncos","Detroit Lions","Green Bay Packers","Houston Texans","Indianapolis Colts","Jacksonville Jaguars","Kansas City Chiefs","Las Vegas Raiders","Los Angeles Chargers","Los Angeles Rams","Miami Dolphins","Minnesota Vikings","New England Patriots","New Orleans Saints","New York Giants","New York Jets","Philadelphia Eagles","Pittsburgh Steelers","San Francisco 49ers","Seattle Seahawks","Tampa Bay Buccaneers","Tennessee Titans","Washington Commanders"],
    ["ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN","DET","GB","HOU","IND","JAX","KC","LV","LAC","LA","MIA","MIN","NE","NO","NYG","NYJ","PHI","PIT","SF","SEA","TB","TEN","WAS"]))


def name_key(n):
    return re.sub(r"[^a-z0-9]", "", n.casefold())


def normalize_odds_event(data, forecasts, captured_at):
    home, away = TEAM_CODES.get(data.get("home_team")), TEAM_CODES.get(data.get("away_team"))
    kickoff = data.get("commence_time")
    candidates = [r for r in forecasts if {r["team"],r["opponent"]} == {home,away}
                  and kickoff and abs((stamp(r["kickoff_utc"])-stamp(kickoff)).total_seconds())<600]
    game_ids = {r["game_id"] for r in candidates}
    game = next(iter(game_ids)) if len(game_ids)==1 else "ODDS:"+str(data["id"])
    out = []
    for book in data.get("bookmakers", []):
        for market in book.get("markets", []):
            if market.get("key") != "player_tackles_assists":
                continue
            for o in market.get("outcomes", []):
                if o.get("name", "").upper() not in {"OVER","UNDER"} or o.get("point") is None:
                    continue
                matches = [r for r in candidates if name_key(r["player_name"])==name_key(o.get("description", ""))]
                exact = matches[0] if len(matches)==1 else {}
                out.append({"game_id":game, "player_id":exact.get("player_id", ""), "player_name":o.get("description", ""),
                            "team":exact.get("team", ""), "side":o["name"].upper(), "line":o["point"], "odds":o["price"],
                            "book":book.get("title") or book.get("key"), "captured_at":captured_at, "kickoff_utc":kickoff,
                            "provider_updated_at":market.get("last_update") or book.get("last_update"), "market":"tackles_assists",
                            "source":"THE_ODDS_API", "provider_event_id":data["id"], "settlement_definition":"UNVERIFIED_BOOK_RULES"})
    return out


class Collector:
    def __init__(self, store):
        self.store = store
        self.key = os.environ.get("OMEGA_ODDS_API_KEY", "")
        self.stop = threading.Event()
        self.capture_lock = threading.Lock()
        self.poly_lock = threading.Lock()
        self.thread = None
        self.inbox = store.path.parent/"inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)

    def odds_capture(self, historical_at=None):
        if not self.key:
            raise ValueError("Configure a The Odds API key first. Your OddsPapi key is a different provider.")
        if not self.capture_lock.acquire(blocking=False):
            raise ValueError("A capture is already running.")
        try:
            cfg = self.store.setting("capture", {})
            historical = stamp(historical_at) if historical_at else None
            if historical and historical >= datetime.now(timezone.utc): raise ValueError('Historical capture needs a past timestamp.')
            today = now()[:10]
            budget = self.store.setting("odds_budget", {"date":today,"calls":0})
            if budget["date"] != today:
                budget = {"date":today,"calls":0}
            cap = int(cfg.get("daily_call_cap", 60))

            def call(path, params):
                if budget["calls"] >= cap:
                    raise ProviderError("Daily request cap reached; capture paused until tomorrow UTC.")
                budget["calls"] += 1
                self.store.set_setting("odds_budget", budget)
                data, h, raw = request_json(ODDS,path,dict(params,apiKey=self.key))
                self.store.set_setting("odds_quota", {k:v for k,v in h.items() if k.lower().startswith("x-requests")})
                return data,raw

            prefix='/v4/historical' if historical else '/v4'
            params={'date':historical.isoformat().replace('+00:00','Z')} if historical else {}
            events, raw = call(prefix+"/sports/americanfootball_nfl/events", params)
            self.store.snapshot("odds_events", "NFL events", raw)
            if historical:
                if not isinstance(events,dict) or not isinstance(events.get('data'),list): raise ProviderError('Invalid historical event envelope.')
                events=events['data']
            if not isinstance(events,list): raise ProviderError('Event feed is not a list.')
            t = historical or datetime.now(timezone.utc)
            eligible = sorted([e for e in events if t < stamp(e["commence_time"]) < t+timedelta(hours=48)],key=lambda e:e["commence_time"])
            seen=self.store.setting('odds_event_attempts',{})
            if not historical: eligible.sort(key=lambda e:(seen.get(str(e['id']),''),e['commence_time']))
            chosen = eligible[:int(cfg.get("max_events",16))]
            total, results = 0, []
            forecast_rows=self.store.forecast_archive()
            for e in chosen:
                if self.stop.is_set():
                    results.append({'event':e['id'],'status':'STOPPED'});continue
                if budget['calls']>=cap:
                    results.append({'event':e['id'],'status':'CALL_CAP'});continue
                try:
                    data, raw = call(prefix+"/sports/americanfootball_nfl/events/"+urllib.parse.quote(e["id"],safe="")+"/odds",
                                     dict(params,regions="us",markets="player_tackles_assists",oddsFormat="american"))
                    capture_time = now()
                    if historical:
                        capture_time=data.get('timestamp')
                        if not capture_time or stamp(capture_time)>historical: raise ProviderError('Historical response is later than the requested as-of time.')
                        data=data.get('data')
                    if not isinstance(data,dict) or data.get('id')!=e['id']: raise ProviderError('Odds response event ID mismatch.')
                    rows = normalize_odds_event(data,forecast_rows,capture_time)
                    if historical:
                        for row in rows: row.update(source='THE_ODDS_API_HISTORICAL',retrieved_at=now(),historical_backfill=True)
                    r = self.store.ingest_quotes(rows,raw,"THE_ODDS_API "+str(e["id"]))
                    total += r["new_quotes"]
                    results.append({"event":e["id"],"rows":r["rows"],
                                    'matched_rows':sum(bool(q.get('player_id')) for q in rows),
                                    'unmatched_rows':sum(not q.get('player_id') for q in rows),
                                    'status':'CAPTURED' if r['rows'] else 'EMPTY'})
                except (ProviderError,ValueError,KeyError,TypeError) as error:
                    results.append({'event':e['id'],'status':'ERROR','error':str(error)})
                seen[str(e['id'])]=now()
            if not historical: self.store.set_setting('odds_event_attempts',seen)
            captured=sum(r['status'] in {'CAPTURED','EMPTY'} for r in results)
            results.extend({'event':e['id'],'status':'EVENT_CAP'} for e in eligible[len(chosen):])
            result = {"captured_at":now(),"eligible_events":len(eligible),"captured_events":captured,"new_quotes":total,"events":results,
                      'historical_as_of':historical_at,'status':('NO_ELIGIBLE_EVENTS' if not eligible else 'COMPLETE' if captured==len(eligible) else 'PARTIAL'),
                      "missing_due_to_event_cap":len(eligible)-len(chosen)}
            self.store.snapshot('capture_run','Sportsbook capture coverage',canonical(result))
            self.store.set_setting("odds_last",result)
            self.store.set_setting('odds_last_failure',None)
            self.store.log("MARKET_CAPTURE",result['status'],f"{captured}/{len(eligible)} events captured; {total} new quotes.")
            return result
        except Exception as error:
            failure={'failed_at':now(),'status':'FAILED','historical_as_of':historical_at,'error':str(error)[:800]}
            self.store.snapshot('capture_run','Failed sportsbook capture',canonical(failure))
            self.store.set_setting('odds_last_failure',failure)
            raise
        finally:
            self.capture_lock.release()

    def poly_capture(self):
        if not self.poly_lock.acquire(blocking=False):
            raise ValueError("Polymarket refresh already running.")
        try:
            results = self.store.setting("poly_last", {})
            watches=self.store.setting('poly_watch',[])[:8]
            wallet_watches=self.store.setting('wallet_watch',[])[:8]
            failed=0; complete=0; partial=0
            for w in watches:
                if self.stop.is_set(): break
                try:
                    result, raw = monitor_market(w["token_id"],w.get("condition_id", ""))
                    sid = self.store.snapshot("polymarket_book", w.get("label",w["token_id"]),raw)
                    results[w["token_id"]] = dict(result,label=w.get("label", ""),snapshot_id=sid,error=None)
                    complete+=1
                    if result.get('wallet_error'): partial+=1
                except (ProviderError,ValueError) as e:
                    failed+=1
                    old = dict(results.get(w["token_id"],{}))
                    old.update(error=str(e),failed_at=now(),label=w.get("label", ""))
                    results[w["token_id"]] = old
                    self.store.log("POLYMARKET","ERROR",str(e))
            self.store.set_setting("poly_last",results)
            wallets = self.store.setting("wallet_last",{})
            for w in wallet_watches:
                if self.stop.is_set(): break
                try:
                    result,raw = monitor_wallet(w["address"])
                    sid = self.store.snapshot("polymarket_wallet",w["address"],raw)
                    wallets[w["address"]] = dict(result,label=w.get("label", ""),snapshot_id=sid,error=None)
                    complete+=1
                except (ProviderError,ValueError) as e:
                    failed+=1
                    old = dict(wallets.get(w["address"],{}))
                    old.update(error=str(e),failed_at=now(),label=w.get("label", ""))
                    wallets[w["address"]] = old
            self.store.set_setting("wallet_last",wallets)
            status='PARTIAL' if partial or (failed and complete) else 'FAILED' if failed else 'COMPLETE'
            if self.stop.is_set(): status='STOPPED'
            return {"books":results,"wallets":wallets,'status':status,'successful_watches':complete,'failed_watches':failed}
        finally:
            self.poly_lock.release()

    def inbox_capture(self):
        seen = self.store.setting("inbox_seen", {})
        for f in sorted(self.inbox.glob("*.csv")):
            if not f.is_file() or f.stat().st_size>20_000_000:
                continue
            try:
                # A partially copied or invalid file must not block the others.
                before=f.stat()
                if time.time()-before.st_mtime<2: continue
                with f.open(encoding="utf-8", newline="") as source: raw=source.read()
                if f.stat().st_size!=before.st_size: continue
                sha=digest(raw)
                if seen.get(f.name)==sha: continue
                result = self.store.import_file("quotes",f.name,raw)
                self.store.log("INBOX","OK",f"{f.name}: {result['rows']} quote rows.")
            except (ValueError,KeyError,UnicodeError,OSError,csv.Error) as e:
                self.store.log("INBOX","INVALID",f"{f.name}: {e}")
                continue
            seen[f.name] = sha
            self.store.set_setting("inbox_seen",seen)

    def run(self):
        last_odds, last_poly = 0, 0
        while not self.stop.is_set():
            try:
                self.inbox_capture()
                cfg = self.store.setting("capture",{})
                if cfg.get("enabled") and time.time()-last_odds >= max(60,int(cfg.get("interval_seconds",900))):
                    last_odds = time.time()
                    try:
                        self.odds_capture()
                    except (ProviderError,ValueError) as e:
                        self.store.log("MARKET_CAPTURE","ERROR",str(e))
                if self.store.setting("poly_auto",False) and time.time()-last_poly >= 60:
                    last_poly = time.time()
                    self.poly_capture()
            except Exception as e:
                self.store.log("COLLECTOR","ERROR",str(e))
            self.stop.wait(10)

    def start(self):
        # Separate lanes prevent a slow public API from blocking quote intake.
        self.threads=[]
        for kind,action in [('INBOX',self.inbox_capture),('MARKET_CAPTURE',self.odds_capture),('POLYMARKET',self.poly_capture)]:
            thread=threading.Thread(target=self.lane,args=(kind,action),daemon=True)
            thread.start();self.threads.append(thread)
        self.thread=self.threads[0]

    def lane(self,kind,action):
        failures=0
        while not self.stop.is_set():
            cfg=self.store.setting('capture',{})
            enabled=kind=='INBOX' or (kind=='MARKET_CAPTURE' and cfg.get('enabled')) or (kind=='POLYMARKET' and self.store.setting('poly_auto',False))
            delay=10 if kind=='INBOX' else max(60,int(cfg.get('interval_seconds',900))) if kind=='MARKET_CAPTURE' else 60
            if enabled:
                try:
                    result=action()
                    failures=0
                    status='OK'
                    if isinstance(result,dict) and result.get('status') in {'PARTIAL','FAILED','STOPPED'}:
                        status=result['status']
                        if status=='FAILED': failures+=1
                except Exception as e:
                    failures+=1;status='ERROR'
                    self.store.log(kind,status,f'{type(e).__name__}: {str(e)[:600]}')
                delay=min(3600,delay*2**min(failures,5))
                with self.store.tx():
                    health=self.store.setting('collector_health',{})
                    health[kind]={'at':now(),'status':status,'consecutive_failures':failures,'next_check_seconds':delay}
                    self.store.set_setting('collector_health',health)
            self.stop.wait(delay if enabled else 5)

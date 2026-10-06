"""Persistence, validation, and grading. Standard library only; Python >=3.10."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import tempfile
import threading
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import fmean

VERSION = "2.1.3-delta.0.1.0"
TARGET = "combined_standard_def_scrimmage"
UTC = timezone.utc


def now():
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def stamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A timestamp with timezone is required.")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Use an ISO timestamp with a timezone, e.g. 2026-09-28T12:00:00Z.") from None
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include a timezone.")
    return dt.astimezone(UTC)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def number(x, default=0.0):
    if x is None or x == "":
        return default
    try:
        n = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid number: {str(x)[:80]}") from None
    if not math.isfinite(n):
        raise ValueError("Numbers must be finite.")
    return n


def bounded(x, low, high):
    if x is None or isinstance(x, bool) or (isinstance(x, str) and not x.strip()):
        raise ValueError("A numeric value is required; missing values are not zero.")
    v = number(x)
    if not low <= v <= high:
        raise ValueError(f"Value must be between {low} and {high}.")
    return v


def truth(x):
    return str(x).lower() in {"true", "1", "yes"}


def odds(x):
    v = number(x)
    if abs(v) < 100 or abs(v) > 100000:
        raise ValueError("American odds must be <= -100 or >= +100.")
    return v


def win_profit(price):
    p = odds(price)
    return 100 / abs(p) if p < 0 else p / 100


def break_even(price):
    return 1 / (1 + win_profit(price))


def cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def csv_rows(raw):
    if not isinstance(raw, str):
        raise ValueError("Import must contain UTF-8 text.")
    if len(raw.encode()) > 20_000_000:
        raise ValueError("File exceeds the 20 MB import limit.")
    reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")), strict=True)
    fields = reader.fieldnames or []
    if not fields or len(set(fields)) != len(fields) or any(not f.strip() for f in fields):
        raise ValueError("CSV needs unique, nonempty column names.")
    rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError("CSV row length does not match its header.")
    if len(rows) > 30000:
        raise ValueError("At most 30,000 rows per import.")
    return rows


def metrics(rows, actual="omega_actual_xtc"):
    total = len(rows)
    rows = [r for r in rows if r.get("predicted_xtc") not in (None, "") and r.get(actual) not in (None, "")]
    if not rows:
        return {"n": 0, "excluded": total, "mae": None, "rmse": None, "bias": None, "above": 0, "below": 0, "equal": 0}
    e = [number(r["predicted_xtc"]) - number(r[actual]) for r in rows]
    return {"n": len(e), "excluded": total-len(e), "mae": fmean(abs(x) for x in e), "rmse": math.sqrt(fmean(x*x for x in e)),
            "bias": fmean(e), "above": sum(x > 1e-9 for x in e), "below": sum(x < -1e-9 for x in e),
            "equal": sum(abs(x) <= 1e-9 for x in e), "predicted_mean": fmean(number(r["predicted_xtc"]) for r in rows),
            "actual_mean": fmean(number(r[actual]) for r in rows), "games": len({r["game_id"] for r in rows})}


def validate_grid(row):
    grids = defaultdict(dict)
    for key, value in row.items():
        match = re.fullmatch(r"(.+)_p_(over|under)_(\d+)_5", key)
        if match:
            track, side, threshold = match.groups()
            grids[track][(int(threshold), side)] = bounded(value, 0, 1)
    for track, grid in grids.items():
        prev, last = 1.0, -1
        for threshold in sorted({k[0] for k in grid}):
            if threshold != last+1 or (threshold,"over") not in grid or (threshold,"under") not in grid:
                raise ValueError(f"{track}: probability grid must start at 0.5 with consecutive over/under pairs.")
            over, under = grid[threshold,"over"], grid[threshold,"under"]
            if over > prev+1e-9 or abs(over+under-1) > 1e-6:
                raise ValueError(f"{track}: probabilities must be monotone and over + under must equal one.")
            prev, last = over, threshold


def price_saved_distribution(forecast, line, side, price, track="control"):
    """Use stored half-point survival probabilities, including integer pushes.

    No assumed distribution parameters and no extrapolation beyond stored lines.
    This arithmetic prices the research target; book settlement must be aligned
    before interpreting it as a betting edge.
    """
    line, price = number(line), odds(price)
    if line < 0 or line*2 != int(line*2) or side not in {"OVER", "UNDER"}:
        raise ValueError("Unsupported threshold or side.")
    def survival(count):
        if count < 0:
            return 1.0
        key = f"{track}_p_over_{count}_5"
        if key not in forecast or forecast[key] in (None, ""):
            raise ValueError("Threshold is outside the stored probability grid.")
        return bounded(forecast[key],0,1)
    floor = math.floor(line)
    over = survival(floor)
    if line == floor:
        push = survival(floor-1)-over
        under = 1-survival(floor-1)
    else:
        under, push = 1-over, 0.0
    if min(over,under,push) < -1e-8:
        raise ValueError("Stored distribution is not monotone.")
    win, loss = (over,under) if side=="OVER" else (under,over)
    return {"win":win,"loss":loss,"push":max(0,push),"expected_roi":win*win_profit(price)-loss,
            "target":TARGET,"settlement_matched":False}


class Store:
    def __init__(self, path, seed=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        os.chmod(self.path, 0o600)
        # Preserve a consistent prototype database before the first migration.
        existing = self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bets'").fetchone()
        schema = self.db.execute("PRAGMA user_version").fetchone()[0]
        if schema > 2:
            self.db.close()
            raise ValueError("This database is from a newer OMEGA version.")
        if existing and schema < 2:
            backup_path = self.path.with_name(self.path.stem+".pre-v1.sqlite3")
            if not backup_path.exists():
                dest = sqlite3.connect(str(backup_path))
                try: self.db.backup(dest)
                finally: dest.close()
                os.chmod(backup_path, 0o600)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS snapshots(
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, received_at TEXT NOT NULL,
                sha256 TEXT NOT NULL, raw TEXT NOT NULL, UNIQUE(kind,sha256));
            CREATE TABLE IF NOT EXISTS quotes(
                id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
                payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bets(
                id TEXT PRIMARY KEY, ticket_key TEXT NOT NULL UNIQUE, placed_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bet_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, bet_id TEXT NOT NULL REFERENCES bets(id),
                kind TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL);
            PRAGMA user_version=2;
        """)
        # Appending corrections is possible; changing audit history in place is not.
        for t in ("snapshots", "quotes", "bets", "bet_events"):
            for action in ("UPDATE", "DELETE"):
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS {t}_no_{action.lower()} BEFORE {action} ON {t} BEGIN SELECT RAISE(ABORT,'Append-only record'); END")
        self.db.commit()
        if seed:
            for name, kind in (("OMEGA_0.38_WEEK3_REMAINING_DUAL_TRACK.csv", "forecasts"),
                               ("OMEGA_0.39_FORECAST_SCORES.csv", "scores"),
                               ("OMEGA_0.39_CAPTURED_MARKET_ROWS.csv", "legacy_market"),
                               ("OMEGA_0.39_SCORING_DEFINITION_DIFFERENCES.csv", "definition")):
                f = Path(seed) / name
                if f.exists() and not self.latest(kind):
                    with f.open(encoding="utf-8", newline="") as source:
                        self.import_file(kind, name, source.read())

    @contextmanager
    def tx(self):
        with self.lock:
            with self.db:
                yield self.db

    def snapshot(self, kind, name, raw, db=None):
        if db is None:
            with self.tx() as c:
                return self.snapshot(kind, name, raw, c)
        sha = digest(raw)
        sid = kind + "_" + sha[:24]
        db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?,?)", (sid, kind, str(name)[:200], now(), sha, raw))
        return sid

    def latest(self, kind):
        with self.lock:
            r = self.db.execute("SELECT * FROM snapshots WHERE kind=? ORDER BY rowid DESC LIMIT 1", (kind,)).fetchone()
        return dict(r) if r else None

    def records(self, kind):
        if kind in {"scores", "availability", "outcomes"}:
            with self.lock:
                snapshots = list(self.db.execute("SELECT id,raw FROM snapshots WHERE kind=? ORDER BY rowid",(kind,)))
            merged = {}
            for source in snapshots:
                for row in csv_rows(source["raw"]):
                    key = (row["game_id"],row["player_id"],row.get("forecast_track", ""))
                    if kind in {"availability","outcomes"}: key += (row["observed_at"],row["source"])
                    merged[key] = dict(row, input_snapshot_id=source["id"])
            return list(merged.values())
        if kind == "forecasts":
            active = self.setting("active_forecast")
            if active:
                with self.lock:
                    selected = self.db.execute("SELECT raw FROM snapshots WHERE id=? AND kind='forecasts'",(active,)).fetchone()
                if selected: return csv_rows(selected[0])
        r = self.latest(kind)
        return csv_rows(r["raw"]) if r else []

    def activate_forecast(self, sid):
        with self.lock:
            found = self.db.execute("SELECT 1 FROM snapshots WHERE id=? AND kind='forecasts'",(sid,)).fetchone()
        if not found: raise ValueError("Forecast snapshot not found.")
        self.set_setting("active_forecast",sid)
        return {"snapshot_id":sid}

    def forecast_archive(self, as_of=None):
        """Latest source-reported pregame forecast per player-game across slates.

        Reception time remains separate: a historical import is not evidence
        that this app possessed a forecast at its reported capture time.
        """
        cutoff = stamp(as_of) if as_of else None
        merged = {}
        with self.lock:
            sources = list(self.db.execute("SELECT id,raw,received_at FROM snapshots WHERE kind='forecasts' ORDER BY rowid"))
        for source in sources:
            for row in csv_rows(source["raw"]):
                captured = stamp(row["captured_at"])
                if captured >= stamp(row["kickoff_utc"]) or (cutoff and captured > cutoff):
                    continue
                key = (row["game_id"], row["player_id"])
                if key not in merged or captured >= stamp(merged[key]["captured_at"]):
                    merged[key] = dict(row, input_snapshot_id=source["id"],
                                       forecast_received_at=source["received_at"])
        return list(merged.values())

    def find_forecast(self, game, player, as_of):
        return next((r for r in self.forecast_archive(as_of)
                     if r["game_id"] == game and r["player_id"] == player), None)

    def compare_quote(self, qid):
        q = next((q for q in self.quote_list() if q["id"]==qid),None)
        if not q: raise ValueError("Quote not found.")
        if q["market"] != "tackles_assists" or q["phase"] != "PREGAME":
            return {"available":False,"reason":"Only pregame tackle-plus-assist quotes can use this distribution."}
        f = self.find_forecast(q["game_id"],q.get("player_id"),q["captured_at"])
        if not f: return {"available":False,"reason":"No player-game forecast was captured by this quote's timestamp."}
        try: result = price_saved_distribution(f,q["line"],q["side"],q["odds"])
        except ValueError as e: return {"available":False,"reason":str(e)}
        return dict(result,available=True,forecast_snapshot_id=f["input_snapshot_id"],forecast_captured_at=f["captured_at"],
                    forecast_received_at=f["forecast_received_at"], quote_provenance=q.get("provenance","SOURCE_REPORTED_CAPTURE_TIME"),
                    executable=False,provenance="SOURCE_REPORTED_CAPTURE_TIME",reason="Research comparison; availability and official settlement are not verified.")

    def import_file(self, kind, name, raw):
        if kind not in {"forecasts", "scores", "quotes", "legacy_market", "definition", "availability", "outcomes"}:
            raise ValueError("Unsupported import type.")
        rows = csv_rows(raw)
        if not rows:
            raise ValueError("No data rows found.")
        required = {"forecasts": {"game_id", "player_id", "player_name", "team", "control_xtc", "role_point_xtc", "kickoff_utc", "captured_at"},
                    "scores": {"game_id", "player_id", "player_name", "week", "forecast_track", "predicted_xtc", "omega_actual_xtc", "defensive_participant"},
                    "availability": {"game_id", "player_id", "status", "observed_at", "source"},
                    "outcomes": {"game_id","player_id","omega_actual_xtc","defensive_participant","observed_at","source","game_status","target"}}.get(kind, set())
        if not required <= set(rows[0]):
            raise ValueError("Missing columns: " + ", ".join(sorted(required - set(rows[0]))))
        seen = set()
        for r in rows:
            if kind in {"forecasts", "scores"}:
                for field in ("game_id","player_id","player_name"):
                    if not r[field].strip(): raise ValueError(f"{field} cannot be empty.")
                key = (r["game_id"], r["player_id"], r.get("forecast_track", ""))
                if key in seen:
                    raise ValueError("Duplicate player-game-track in import.")
                seen.add(key)
            if kind == "forecasts":
                for field in ("control_xtc", "role_point_xtc"):
                    bounded(r[field], 0, 100)
                if stamp(r["captured_at"]) >= stamp(r["kickoff_utc"]) or stamp(r["captured_at"]) > datetime.now(UTC):
                    raise ValueError("Forecast captured after kickoff. Import retrospective outputs as scores.")
                validate_grid(r)
                for field in ("predicted_xto","control_h012_snap_share","role_point_snap_share"):
                    if field in r: bounded(r[field],0,300 if field=="predicted_xto" else 1)
                for field in r:
                    if field.startswith(("pred_share_","control_pred_credit_")):
                        bounded(r[field],0,100 if "credit" in field else 1)
            if kind == "scores":
                bounded(r["predicted_xtc"], 0, 100)
                week = bounded(r["week"],1,25)
                if int(week) != week: raise ValueError("Week must be an integer.")
                if r["forecast_track"] not in {"CONTROL", "ROLE_SHADOW"}:
                    raise ValueError("Forecast track must be CONTROL or ROLE_SHADOW.")
                game_parts = r["game_id"].split("_")
                if len(game_parts) == 4 and game_parts[0].isdigit() and game_parts[1].isdigit() and int(game_parts[1]) != week:
                    raise ValueError("Score week does not match its game ID.")
                if r["defensive_participant"].lower() not in {"true","false","1","0","yes","no","unknown",""}:
                    raise ValueError("Unknown participation flag.")
                for field in ("omega_actual_xtc", "sportsbook_like_actual"):
                    if r.get(field) not in (None, ""):
                        v = bounded(r[field], 0, 100)
                        if int(v) != v:
                            raise ValueError("Actual tackle counts must be integers.")
            if kind == "availability":
                if not r['game_id'].strip() or not r['player_id'].strip():
                    raise ValueError('Availability needs nonempty game and player IDs.')
                if r["status"].upper() not in {"ACTIVE", "INACTIVE", "QUESTIONABLE", "UNKNOWN"}:
                    raise ValueError("Unknown availability status.")
                if not r["source"].strip() or stamp(r["observed_at"]) > datetime.now(UTC):
                    raise ValueError("Availability needs a source and a nonfuture observation time.")
            if kind == "outcomes":
                if r['target'] != TARGET or r['game_status'].upper() != 'FINAL':
                    raise ValueError('Outcome must be FINAL and use the combined_standard_def_scrimmage target.')
                for field in ('game_id','player_id','source'):
                    if not r[field].strip(): raise ValueError(field+' cannot be empty.')
                if stamp(r['observed_at']) > datetime.now(UTC): raise ValueError('Outcome observation cannot be in the future.')
                for field in ('omega_actual_xtc','sportsbook_like_actual'):
                    if field=='sportsbook_like_actual' and r.get(field) in (None,''): continue
                    value=bounded(r[field],0,100)
                    if int(value)!=value: raise ValueError('Actual counts must be integers.')
                if r['defensive_participant'].lower() not in {'true','false','unknown'}: raise ValueError('Participation must be True, False or Unknown.')
        normalized = [normalize_quote(r) for r in rows] if kind == "quotes" else []
        with self.tx() as c:
            sid = self.snapshot(kind, name, raw, c)
            added = 0
            for r in normalized:
                rid = digest(canonical(r))
                added += c.execute("INSERT OR IGNORE INTO quotes VALUES(?,?,?)", (rid, sid, canonical(r))).rowcount
            if kind == "forecasts":
                c.execute("INSERT INTO settings VALUES('active_forecast',?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",(canonical(sid),))
        return {"snapshot_id": sid, "rows": len(rows), "new_quotes": added}

    def ingest_quotes(self, rows, raw, source):
        # Validate every row before inserting any; retain raw response and empty captures.
        parsed = [normalize_quote(r) for r in rows]
        with self.tx() as c:
            sid = self.snapshot("provider_quotes", source, raw, c)
            n = 0
            for r in parsed:
                rid = digest(canonical(r))
                n += c.execute("INSERT OR IGNORE INTO quotes VALUES(?,?,?)", (rid, sid, canonical(r))).rowcount
        return {"rows": len(parsed), "new_quotes": n, "snapshot_id": sid}

    def setting(self, key, default=None):
        with self.lock:
            r = self.db.execute("SELECT payload FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set_setting(self, key, value):
        with self.tx() as c:
            c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload", (key, canonical(value)))

    def log(self, kind, status, detail):
        with self.tx() as c:
            c.execute("INSERT INTO logs(at,kind,status,detail) VALUES(?,?,?,?)", (now(), kind, status, str(detail)[:1200]))

    def quote_list(self):
        with self.lock:
            return [dict(json.loads(r["payload"]), id=r["id"], snapshot_id=r["snapshot_id"]) for r in self.db.execute("SELECT * FROM quotes ORDER BY rowid DESC")]

    def add_bet(self, data):
        allowed = {"ticket_id","book","selection","placed_at","odds","stake","kind","side","line","quote_id","notes"}
        b = {k:v for k,v in data.items() if k in allowed}
        for k in ("ticket_id", "book", "selection", "placed_at"):
            if not str(b.get(k, "")).strip():
                raise ValueError(k.replace("_", " ") + " is required.")
            b[k] = str(b[k]).strip()
            if len(b[k]) > (2000 if k=="selection" else 200): raise ValueError(k+" is too long.")
        b["odds"] = odds(b.get("odds"))
        stake = bounded(b.get("stake"), .01, 1000000)
        if Decimal(str(stake)) * 100 != (Decimal(str(stake)) * 100).to_integral_value():
            raise ValueError("Stake must have at most two decimal places.")
        b["stake_cents"] = cents(stake)
        b["placed_at"] = stamp(b["placed_at"]).isoformat().replace("+00:00", "Z")
        if stamp(b["placed_at"]) > datetime.now(UTC):
            raise ValueError("A placed bet cannot have a future placement time.")
        b["kind"] = b.get("kind", "SINGLE").upper()
        if b["kind"] not in {"SINGLE", "PARLAY"}:
            raise ValueError("Choose single or parlay.")
        if b["kind"] == "SINGLE":
            b["side"] = b.get("side", "").upper()
            if b["side"] not in {"OVER", "UNDER"}:
                raise ValueError("Single props require over or under.")
            b["line"] = bounded(b.get("line"), 0, 1000)
            if b["line"]*2 != int(b["line"]*2): raise ValueError("Single line must be an integer or half-integer.")
        else:
            b["side"], b["line"] = "PARLAY", None
        # Linking is explicit; model/quote availability must precede placement.
        b["link_status"] = "UNLINKED"
        qid = b.get("quote_id")
        if qid:
            q = next((q for q in self.quote_list() if q["id"] == qid), None)
            if not q or stamp(q["captured_at"]) > stamp(b["placed_at"]):
                raise ValueError("Quote is missing or was captured after placement.")
            if (b["kind"] != "SINGLE" or b["book"].casefold() != q["book"].casefold()
                or b["side"] != q["side"] or b["line"] != q["line"] or b["odds"] != q["odds"]):
                raise ValueError("Linked quote does not match this ticket's book, side, line, and odds.")
            b.update(game_id=q["game_id"], player_id=q.get("player_id", ""), player_name=q["player_name"],
                     market=q["market"], quote_snapshot_id=q["snapshot_id"], link_status="QUOTE_LINKED")
            if q.get("historical_backfill"):
                b["link_status"] = "HISTORICAL_REFERENCE_ONLY"
            b["quote_provenance"] = q.get("provenance", "SOURCE_REPORTED_CAPTURE_TIME")
        b["model_snapshot_id"] = ""
        if b.get("player_id") and b.get("game_id"):
            f = self.find_forecast(b["game_id"],b["player_id"],b["placed_at"])
            if f:
                b["model_snapshot_id"] = f["input_snapshot_id"]
                b["model_link_provenance"] = ("LOCALLY_RECORDED_BY_PLACEMENT" if
                    stamp(f["forecast_received_at"]) <= stamp(b["placed_at"]) else "SOURCE_REPORTED_TIME_ONLY")
        bid = "bet_" + uuid.uuid4().hex[:20]
        key = b["book"].strip().casefold() + "|" + b["ticket_id"].strip()
        try:
            with self.tx() as c:
                c.execute("INSERT INTO bets VALUES(?,?,?,?,?)", (bid, key, b["placed_at"], now(), canonical(b)))
        except sqlite3.IntegrityError:
            raise ValueError("This book + ticket ID is already in your ledger.") from None
        return {"id": bid}

    def settle_bet(self, bid, data):
        with self.tx() as c:
            row = c.execute("SELECT payload FROM bets WHERE id=?", (bid,)).fetchone()
            if not row:
                raise ValueError("Bet not found.")
            b = json.loads(row[0])
            for correction in c.execute("SELECT payload FROM bet_events WHERE bet_id=? AND kind='TICKET_CORRECTION' ORDER BY id",(bid,)):
                b.update(json.loads(correction[0])["changes"])
            result = str(data.get("result", "")).upper()
            if result not in {"WIN", "LOSS", "PUSH", "VOID", "CASHOUT", "OPEN"}:
                raise ValueError("Invalid settlement result.")
            if not str(data.get("source", "")).strip():
                raise ValueError("Add a settlement source or correction reason.")
            if result == "WIN":
                price = Decimal(str(b["odds"]))
                profit = Decimal(100)/abs(price) if price < 0 else price/100
                payout = b["stake_cents"] + int((Decimal(b["stake_cents"])*profit).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            elif result == "LOSS":
                payout = 0
            elif result == "CASHOUT":
                amount = bounded(data.get("payout"), 0, 100000000)
                if Decimal(str(amount))*100 != (Decimal(str(amount))*100).to_integral_value():
                    raise ValueError("Return must have at most two decimal places.")
                payout = cents(amount)
            elif result == "OPEN":
                payout = 0
            else:
                payout = b["stake_cents"]
            event = {"result": result, "payout_cents": payout, "source": str(data["source"])[:800]}
            c.execute("INSERT INTO bet_events(bet_id,kind,at,payload) VALUES(?,?,?,?)", (bid, "SETTLEMENT", now(), canonical(event)))
        return event

    def amend_bet(self, bid, data):
        with self.tx() as c:
            b = next((b for b in self.bet_list() if b['id']==bid),None)
            if not b: raise ValueError("Bet not found.")
            if b['result'] != 'OPEN': raise ValueError("Reopen the ticket before correcting stake or odds.")
            if not str(data.get('source','')).strip(): raise ValueError("Correction reason is required.")
            stake = bounded(data.get('stake'),.01,1000000)
            if Decimal(str(stake))*100 != (Decimal(str(stake))*100).to_integral_value(): raise ValueError("Stake must have at most two decimal places.")
            changes = {'stake_cents':cents(stake),'stake':stake,'odds':odds(data.get('odds'))}
            # An edited price is no longer the original quote selection.
            if changes['odds'] != b['odds']:
                changes.update(quote_id='',quote_snapshot_id='',link_status='CORRECTED_UNLINKED')
            event={'changes':changes,'source':str(data['source'])[:800]}
            c.execute("INSERT INTO bet_events(bet_id,kind,at,payload) VALUES(?,?,?,?)",(bid,'TICKET_CORRECTION',now(),canonical(event)))
        return event

    def bet_list(self):
        with self.lock:
            rows = list(self.db.execute("SELECT * FROM bets ORDER BY placed_at DESC"))
            events = list(self.db.execute("SELECT * FROM bet_events ORDER BY id"))
        qs = self.quote_list()
        by = defaultdict(list)
        for e in events:
            by[e["bet_id"]].append(dict(json.loads(e["payload"]), at=e["at"], kind=e["kind"]))
        out = []
        for row in rows:
            b = dict(json.loads(row["payload"]), id=row["id"], recorded_at=row["recorded_at"], events=by[row["id"]])
            for event in b['events']:
                if event['kind']=='TICKET_CORRECTION': b.update(event['changes'])
            settlements = [e for e in b['events'] if e['kind']=='SETTLEMENT']
            last = settlements[-1] if settlements else {"result": "OPEN", "payout_cents": 0}
            b.update(result=last["result"], payout_cents=last["payout_cents"], pnl_cents=0 if last["result"] == "OPEN" else last["payout_cents"]-b["stake_cents"])
            b["clv"] = None
            if b.get("player_id") and b.get("game_id") and b["kind"] == "SINGLE":
                candidates = [q for q in qs if q.get("player_id") == b["player_id"] and q["game_id"] == b["game_id"]
                              and q["market"] == b.get("market", "tackles_assists") and q["side"] == b["side"]
                              and q["line"] == b["line"] and q["book"].casefold() == b["book"].casefold()
                              and q.get("kickoff_utc") and stamp(b["placed_at"]) <= stamp(q["captured_at"]) < stamp(q["kickoff_utc"])]
                if candidates:
                    close = max(candidates, key=lambda q: stamp(q["captured_at"]))
                    b["clv"] = {"price": close["odds"], "implied_probability_delta": break_even(close["odds"])-break_even(b["odds"]),
                                "observed_at": close["captured_at"], "label": "LAST_CAPTURED_SAME_LINE", "quote_id": close["id"],
                                "historical_recovery": bool(close.get("historical_backfill"))}
            out.append(b)
        return out

    def state(self):
        active = self.setting('active_forecast')
        with self.lock:
            f = self.db.execute("SELECT * FROM snapshots WHERE id=?",(active,)).fetchone() if active else self.latest("forecasts")
            f = dict(f) if f else None
        with self.lock:
            snapshots = [dict(r) for r in self.db.execute("SELECT id,kind,name,received_at,sha256,length(CAST(raw AS BLOB)) AS bytes FROM snapshots ORDER BY rowid DESC")]
            logs = [dict(r) for r in self.db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 30")]
        return {"version": VERSION, "now": now(), "forecast_snapshot": {k:v for k,v in f.items() if k != "raw"} if f else None,
                "forecasts": self.records("forecasts"), "scores": self.records("scores"), "historical_market": self.records("legacy_market"),
                "definitions": self.records("definition"), "availability": self.records("availability"), "quotes": self.quote_list(),
                "bets": self.bet_list(), "snapshots": snapshots, "logs": logs,
                "capture": self.setting("capture", {"enabled": False, "interval_seconds": 900, "max_events": 16, "daily_call_cap": 60}),
                "poly_watch": self.setting("poly_watch", []), "poly_last": self.setting("poly_last", {}),
                "wallet_watch": self.setting("wallet_watch", []), "wallet_last": self.setting("wallet_last", {}),
                "poly_auto": self.setting("poly_auto", False), "last_simulation": self.setting("last_simulation", None),
                "data_path": str(self.path), "inbox": str(self.path.parent/"inbox"),
                "validation":self.setting('last_validation'),"health":self.setting('collector_health',{})}

    def database_backup(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'backup.sqlite3'
            dest=sqlite3.connect(str(target))
            try:
                with self.lock: self.db.backup(dest)
            finally: dest.close()
            return target.read_bytes()

    def backup(self):
        with self.lock:
            return {"app": "OMEGA Next", "schema": 2, "exported_at": now(),
                    "tables": {t: [dict(r) for r in self.db.execute(f"SELECT * FROM {t}")] for t in ("snapshots", "quotes", "bets", "bet_events", "settings", "logs")}}


def normalize_quote(row):
    r = dict(row)
    required = ("game_id", "player_name", "book", "side", "line", "captured_at")
    for k in required:
        if r.get(k) is None or str(r[k]).strip() == "":
            raise ValueError(f"Quote missing {k}.")
    r["side"] = r["side"].upper()
    if r["side"] not in {"OVER", "UNDER"}:
        raise ValueError("Quote side must be OVER or UNDER.")
    r["line"] = bounded(r["line"], 0, 1000)
    if r["line"]*2 != int(r["line"]*2):
        raise ValueError("Quote line must be an integer or half-integer.")
    r["odds"] = odds(r.get("odds", r.get("price_american", r.get("price"))))
    r["captured_at"] = stamp(r["captured_at"]).isoformat().replace("+00:00", "Z")
    if stamp(r["captured_at"]) > datetime.now(UTC):
        raise ValueError("Quote capture cannot be in the future.")
    if r.get("kickoff_utc"):
        r["kickoff_utc"] = stamp(r["kickoff_utc"]).isoformat().replace("+00:00", "Z")
        r["phase"] = "PREGAME" if stamp(r["captured_at"]) < stamp(r["kickoff_utc"]) else "LIVE_OR_POSTGAME"
    else:
        r["phase"] = "KICKOFF_UNKNOWN"
    r["player_id"] = str(r.get("player_id", ""))
    r["market"] = r.get("market") or "tackles_assists"
    r["source"] = r.get("source") or "USER_IMPORT"
    r['historical_backfill'] = truth(r.get('historical_backfill')) or r['source']=='THE_ODDS_API_HISTORICAL'
    r['provenance'] = 'HISTORICAL_RECOVERY' if r['historical_backfill'] else 'SOURCE_REPORTED_CAPTURE_TIME'
    if r.get('retrieved_at'):
        r['retrieved_at'] = stamp(r['retrieved_at']).isoformat().replace('+00:00','Z')
        if stamp(r['retrieved_at']) < stamp(r['captured_at']) or stamp(r['retrieved_at']) > datetime.now(UTC):
            raise ValueError('Quote retrieval time must be after capture and not in the future.')
    r["settlement_definition"] = r.get("settlement_definition") or "UNVERIFIED_BOOK_RULES"
    r["identity_status"] = "EXACT_ID" if r["player_id"] else "NAME_ONLY"
    return r

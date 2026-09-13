#!/usr/bin/env python3
"""MODEL v2 local market service.

Purpose:
- Keep OddsPapi credentials outside Chrome.
- Fetch/normalize current market observations.
- Join MLB OddsPapi fixtures to official MLB gamePk identities.
- Persist immutable market snapshots plus a latest pointer.
- Expose a tiny localhost JSON API to the extension.

This v2.3.6 service uses OddsPapi only for supported MLB game markets.
The user's OddsPapi free plan does not include player props, so starter-K
market discovery is deliberately disabled to protect the 250-request monthly
quota. K market comparison is owned by the structured PropsMadness pipeline
in the Chrome extension; OddsPapi remains the post-model game-market source.
"""
from __future__ import annotations

import csv
import json
import math
import hmac
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

VERSION = "2.3.7"
HOST = "127.0.0.1"
PORT = int(os.environ.get("MODEL_SERVICE_PORT", "8765"))
APP_DIR = Path.home() / "Library" / "Application Support" / "MODEL"
CONFIG_PATH = APP_DIR / "config.json"
CACHE_DIR = APP_DIR / "cache"
DATA_DIR = APP_DIR / "market_data"
SERVICE_TOKEN_PATH = APP_DIR / "service_token"
LATEST_MLB = DATA_DIR / "mlb" / "latest.json"
KEYCHAIN_SERVICE = "MODEL_ODDSPAPI_API_KEY"
ODDSPAPI_V4 = "https://api.oddspapi.io/v4"
MLB_SCHEDULE = "https://statsapi.mlb.com/api/v1/schedule"
ET = ZoneInfo("America/New_York")

DEFAULT_CONFIG = {
    "schemaVersion": 1,
    "serviceVersion": VERSION,
    "provider": {
        "oddspapi": {
            "baseUrl": ODDSPAPI_V4,
            # OddsPapi is reserved for supported game markets on this plan.
            "books": ["pinnacle", "circasports", "fanduel"],  # legacy compatibility
            "sharpBooks": ["pinnacle", "circasports"],       # legacy compatibility
            "moneylineBooks": ["pinnacle", "circasports", "fanduel"],
            "moneylineSharpBooks": ["pinnacle", "circasports"],
            "minRefreshSeconds": 60,
            "consensusMaxBookSkewSeconds": 120,
        }
    },
    "sports": {
        "mlb": {
            "enabled": True,
            "sportId": 13,
            "tournamentId": 109,
            "markets": {"moneyline": 131},
            "officialIdentity": "MLB gamePk",
            "modelAdaptersAvailable": ["mlb-moneyline-v0.8.0-offense-strength-2026-09-06", "mlb-k-v0.8.3-sample-shrinkage-workload-2026-09-07"],
            "marketTruthAdapters": ["moneyline"],
        },
        "nfl": {
            "enabled": False,
            "sportId": None,
            "tournamentId": None,
            "markets": {},
            "officialIdentity": "pending adapter configuration",
            "modelAdaptersAvailable": [],
            "marketTruthAdapters": [],
        },
        "cfb": {
            "enabled": False,
            "sportId": None,
            "tournamentId": None,
            "markets": {},
            "officialIdentity": "pending adapter configuration",
            "modelAdaptersAvailable": [],
            "marketTruthAdapters": [],
        },
    },
    "trust": {
        "marketFreshSeconds": 180,
        "marketBlockSeconds": 300,
        "anomalyEdgePP": 12.0,
        "verifiedMinEdgePP": 2.5,
        "verifiedMinEV": 0.02,
        "mlbModelFreshMinutes": 90,
        "mlbModelWatchMinutes": 45,
        "mlbModelMaxSkewMinutes": 30,
        "propModelFreshMinutes": 30,
        "propModelMaxSkewMinutes": 10,
    },
}

TEAM_ALIASES = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS", "Chicago Cubs": "CHC", "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE", "Colorado Rockies": "COL",
    "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN", "New York Mets": "NYM",
    "New York Yankees": "NYY", "Oakland Athletics": "OAK", "Athletics": "OAK",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SD",
    "San Francisco Giants": "SF", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB", "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
    "AZ": "ARI", "ARI": "ARI", "ATH": "OAK", "OAK": "OAK", "CHW": "CWS", "CWS": "CWS",
    "KCR": "KC", "KC": "KC", "SDP": "SD", "SD": "SD", "SFG": "SF", "SF": "SF",
    "TBR": "TB", "TB": "TB", "WSN": "WSH", "WSH": "WSH", "NYA": "NYY", "NYY": "NYY",
    "NYN": "NYM", "NYM": "NYM", "LAA": "LAA", "LAD": "LAD", "SEA": "SEA",
    "TOR": "TOR", "TEX": "TEX", "STL": "STL", "PHI": "PHI", "PIT": "PIT",
    "MIL": "MIL", "MIN": "MIN", "MIA": "MIA", "HOU": "HOU", "DET": "DET",
    "COL": "COL", "CLE": "CLE", "CIN": "CIN", "CHC": "CHC", "BOS": "BOS", "BAL": "BAL",
}

_lock = threading.Lock()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_utc()).isoformat().replace("+00:00", "Z")


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_config() -> dict:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        atomic_json(CONFIG_PATH, DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    # Shallow/deep merge defaults so upgrades add new fields without destroying user config.
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    def merge(dst, src):
        for k, v in (src or {}).items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v
    merge(merged, raw)
    # Runtime-owned metadata must describe the running code, not stale persisted config.
    merged["serviceVersion"] = VERSION
    try:
        merged["sports"]["mlb"]["modelAdaptersAvailable"] = list(DEFAULT_CONFIG["sports"]["mlb"]["modelAdaptersAvailable"])
    except Exception:
        pass
    return merged



def get_service_token() -> str:
    try:
        token = SERVICE_TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        token = ""
    if len(token) < 32:
        raise RuntimeError("MODEL service token is missing. Re-run install_model_v2.command.")
    return token


def get_api_key() -> str:
    env = os.environ.get("ODDSPAPI_API_KEY", "").strip()
    if env:
        return env
    security = shutil.which("security") or "/usr/bin/security"
    user = os.environ.get("USER") or ""
    cmds = [
        [security, "find-generic-password", "-w", "-s", KEYCHAIN_SERVICE, "-a", user],
        [security, "find-generic-password", "-w", "-s", KEYCHAIN_SERVICE],
    ]
    for cmd in cmds:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            if p.returncode == 0 and p.stdout.strip():
                return p.stdout.strip()
        except Exception:
            pass
    raise RuntimeError(
        "OddsPapi API key is not configured. Re-run install_model_v2.command or store it in macOS Keychain "
        f"under service {KEYCHAIN_SERVICE}."
    )


def curl_json(url: str, *, timeout: int = 60) -> Any:
    curl = shutil.which("curl") or "/usr/bin/curl"
    if not Path(curl).exists():
        raise RuntimeError("macOS curl was not found")
    safe_url = url.replace("\\", "\\\\").replace('"', '\\"')
    cfg = (
        f'url = "{safe_url}"\n'
        'header = "Accept: application/json"\n'
        'silent\nshow-error\nfail-with-body\nlocation\n'
        f'max-time = {int(timeout)}\n'
    )
    p = subprocess.run([curl, "--config", "-"], input=cfg, capture_output=True, text=True, timeout=timeout + 5)
    if p.returncode != 0:
        msg = (p.stderr or p.stdout or "curl failed").strip()
        raise RuntimeError(msg[:500])
    try:
        return json.loads(p.stdout)
    except Exception as exc:
        raise RuntimeError(f"Non-JSON response: {p.stdout[:300]}") from exc


def oddspapi_get(path: str, params: dict, key: str) -> Any:
    q = dict(params)
    q["apiKey"] = key
    return curl_json(f"{ODDSPAPI_V4}/{path}?{urllib.parse.urlencode(q)}")


def official_mlb_schedule(date_iso: str) -> list[dict]:
    params = {
        "sportId": 1,
        "date": date_iso,
        "hydrate": "probablePitcher",
    }
    payload = curl_json(f"{MLB_SCHEDULE}?{urllib.parse.urlencode(params)}")
    games = []
    for d in payload.get("dates") or []:
        for g in d.get("games") or []:
            away_obj = ((g.get("teams") or {}).get("away") or {}).get("team") or {}
            home_obj = ((g.get("teams") or {}).get("home") or {}).get("team") or {}
            status = g.get("status") or {}
            games.append({
                "gamePk": str(g.get("gamePk") or ""),
                "startTime": g.get("gameDate"),
                "away": canonical_team(away_obj.get("abbreviation") or away_obj.get("name")),
                "home": canonical_team(home_obj.get("abbreviation") or home_obj.get("name")),
                "abstractState": status.get("abstractGameState"),
                "detailedState": status.get("detailedState"),
                "awayStarter": ((((g.get("teams") or {}).get("away") or {}).get("probablePitcher") or {}).get("fullName")),
                "homeStarter": ((((g.get("teams") or {}).get("home") or {}).get("probablePitcher") or {}).get("fullName")),
            })
    return games


def canonical_team(value: Any) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    if s in TEAM_ALIASES:
        return TEAM_ALIASES[s]
    up = s.upper()
    if up in TEAM_ALIASES:
        return TEAM_ALIASES[up]
    return up if 2 <= len(up) <= 4 else None


def participant_name_from_fixture(fx: dict, n: int) -> str | None:
    for key in (f"participant{n}Name", f"participant{n}ShortName", f"participant{n}Abbr"):
        if fx.get(key):
            return str(fx[key])
    return None


def participant_cache_path(sport_id: int) -> Path:
    return CACHE_DIR / f"oddspapi_participants_sport_{sport_id}.json"


def ensure_participant_names(fixtures: list[dict], sport_id: int, key: str, request_log: list[dict]) -> dict[str, str]:
    direct: dict[str, str] = {}
    missing: set[str] = set()
    for fx in fixtures:
        for n in (1, 2):
            pid = fx.get(f"participant{n}Id")
            if pid is None:
                continue
            pid = str(pid)
            nm = participant_name_from_fixture(fx, n)
            if nm:
                direct[pid] = nm
            else:
                missing.add(pid)

    cache = {}
    cp = participant_cache_path(sport_id)
    if cp.exists():
        try:
            cache = json.loads(cp.read_text(encoding="utf-8")).get("names") or {}
        except Exception:
            cache = {}
    merged = {**cache, **direct}
    unresolved = [pid for pid in missing if pid not in merged]
    if unresolved:
        started = iso()
        payload = oddspapi_get("participants", {"sportId": sport_id, "language": "en"}, key)
        request_log.append({"endpoint": "participants", "purpose": f"sport {sport_id} identity cache", "startedAt": started, "completedAt": iso(), "outcome": "ok"})
        names = {}
        if isinstance(payload, dict):
            # v4 observed shape: {participantId: participantName}
            for k, v in payload.items():
                if isinstance(v, str):
                    names[str(k)] = v
                elif isinstance(v, dict):
                    nm = v.get("participantName") or v.get("name") or v.get("participantNameShort")
                    if nm:
                        names[str(k)] = str(nm)
        elif isinstance(payload, list):
            for row in payload:
                if not isinstance(row, dict):
                    continue
                pid = row.get("participantId") or row.get("id")
                nm = row.get("participantName") or row.get("name") or row.get("participantNameShort")
                if pid is not None and nm:
                    names[str(pid)] = str(nm)
        merged.update(names)
        atomic_json(cp, {"sportId": sport_id, "savedAt": iso(), "names": merged})
    return merged


def dict_get_flexible(obj: dict, key: Any):
    if not isinstance(obj, dict):
        return None
    return obj.get(str(key), obj.get(key))


def active_price_node(outcome: dict) -> dict | None:
    if not isinstance(outcome, dict):
        return None
    players = outcome.get("players") or {}
    node = players.get("0") if isinstance(players, dict) else None
    if node is None and isinstance(players, dict):
        node = players.get(0)
    if node is None and isinstance(players, dict) and len(players) == 1:
        node = next(iter(players.values()))
    if not isinstance(node, dict) or node.get("active") is False:
        return None
    try:
        price = float(node.get("price"))
    except Exception:
        return None
    if not math.isfinite(price) or price <= 1.0:
        return None
    return node


def decimal_to_american(decimal_odds: float) -> int:
    if decimal_odds >= 2:
        return int(round((decimal_odds - 1) * 100))
    return int(round(-100 / (decimal_odds - 1)))


def extract_moneyline(fixture: dict, book_slug: str, market_id: int) -> dict | None:
    book = (fixture.get("bookmakerOdds") or {}).get(book_slug)
    if not isinstance(book, dict) or book.get("suspended") is True:
        return None
    market = dict_get_flexible(book.get("markets") or {}, market_id)
    if not isinstance(market, dict) or market.get("marketActive") is False:
        return None
    sides: dict[str, dict] = {}
    for outcome_id, outcome in (market.get("outcomes") or {}).items():
        node = active_price_node(outcome)
        if not node:
            continue
        label = str(node.get("bookmakerOutcomeId") or "").strip().lower()
        side = None
        if "home" in label:
            side = "home"
        elif "away" in label:
            side = "away"
        else:
            oid = str(outcome_id)
            if oid == str(market_id):
                side = "home"
            elif oid == str(market_id + 1):
                side = "away"
        if side:
            sides[side] = node
    if "home" not in sides or "away" not in sides:
        return None
    hd = float(sides["home"]["price"])
    ad = float(sides["away"]["price"])
    hraw, araw = 1 / hd, 1 / ad
    denom = hraw + araw
    if denom <= 0:
        return None
    changed_values = [sides["home"].get("changedAt"), sides["away"].get("changedAt"), sides["home"].get("bookmakerChangedAt"), sides["away"].get("bookmakerChangedAt")]
    changed = next((v for v in changed_values if v), None)
    return {
        "book": book_slug,
        "homeDecimal": hd,
        "awayDecimal": ad,
        "homeAmerican": int(sides["home"].get("priceAmerican") or decimal_to_american(hd)),
        "awayAmerican": int(sides["away"].get("priceAmerican") or decimal_to_american(ad)),
        "homeNoVig": hraw / denom,
        "awayNoVig": araw / denom,
        "vig": denom - 1.0,
        "homeLimit": sides["home"].get("limit"),
        "awayLimit": sides["away"].get("limit"),
        "changedAt": changed,
        "marketId": market_id,
        "marketActive": True,
    }



def status_is_pregame(fx: dict) -> bool:
    status_id = fx.get("statusId")
    if status_id is not None:
        try:
            if int(status_id) == 0:
                return True
            if int(status_id) > 0:
                return False
        except Exception:
            pass
    text = " ".join(str(fx.get(k) or "") for k in ("statusName", "status", "fixtureStatus")).lower()
    return any(token in text for token in ("pre-game", "pregame", "not started", "scheduled", "preview"))


def match_official_game(away: str, home: str, start_time: str | None, official: list[dict]) -> tuple[dict | None, str]:
    candidates = [g for g in official if g.get("away") == away and g.get("home") == home]
    if not candidates:
        return None, "team_pair_not_found"
    if len(candidates) == 1:
        return candidates[0], "team_pair_unique"
    target = parse_iso(start_time)
    if not target:
        return None, "doubleheader_without_start_time"
    scored = []
    for g in candidates:
        gt = parse_iso(g.get("startTime"))
        if gt:
            scored.append((abs((gt - target).total_seconds()), g))
    if not scored:
        return None, "doubleheader_without_official_times"
    scored.sort(key=lambda x: x[0])
    if len(scored) > 1 and scored[1][0] - scored[0][0] < 900:
        return None, "doubleheader_ambiguous_time"
    if scored[0][0] > 4 * 3600:
        return None, "start_time_mismatch"
    return scored[0][1], "team_pair_plus_start_time"


def fixture_map(payload: Any) -> dict[str, dict]:
    if isinstance(payload, list):
        return {str(x.get("fixtureId")): x for x in payload if isinstance(x, dict) and x.get("fixtureId")}
    if isinstance(payload, dict):
        # tolerate wrappers
        rows = payload.get("fixtures") or payload.get("data") or payload.get("rows")
        if isinstance(rows, list):
            return {str(x.get("fixtureId")): x for x in rows if isinstance(x, dict) and x.get("fixtureId")}
    return {}


def latest_snapshot_age_seconds() -> float | None:
    if not LATEST_MLB.exists():
        return None
    try:
        data = json.loads(LATEST_MLB.read_text(encoding="utf-8"))
        dt = parse_iso(data.get("observedAt"))
        if dt:
            return max(0.0, (now_utc() - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        pass
    return None


def load_latest_mlb() -> dict | None:
    if not LATEST_MLB.exists():
        return None
    try:
        return json.loads(LATEST_MLB.read_text(encoding="utf-8"))
    except Exception:
        return None


def refresh_mlb(force: bool = False) -> dict:
    """Refresh supported MLB game-market truth with quota-aware OddsPapi use.

    Important plan constraint: the configured OddsPapi account has 250 requests
    per month and no player-prop entitlement. This function therefore makes no
    /markets strikeout-catalogue calls, no per-fixture /odds prop probes, and no
    retail player-prop bookmaker requests. K props are handled downstream from
    PropsMadness structured data in the extension.
    """
    with _lock:
        cfg = load_config()
        provider = cfg["provider"]["oddspapi"]
        min_refresh = int(provider.get("minRefreshSeconds", 60))
        age = latest_snapshot_age_seconds()
        if not force and age is not None and age < min_refresh:
            cached = load_latest_mlb()
            if cached and str(cached.get("serviceVersion") or "") == VERSION:
                cached = dict(cached)
                cached["cacheHit"] = True
                cached["cacheAgeSeconds"] = age
                return cached

        sport = cfg["sports"]["mlb"]
        key = get_api_key()
        moneyline_books = list(provider.get("moneylineBooks") or provider.get("books") or ["pinnacle", "circasports", "fanduel"])
        moneyline_sharp_books = list(provider.get("moneylineSharpBooks") or provider.get("sharpBooks") or ["pinnacle", "circasports"])
        books = list(dict.fromkeys(moneyline_books))
        tournament_id = int(sport["tournamentId"])
        market_id = int(sport["markets"]["moneyline"])
        request_log = []
        by_book = {}
        by_book_observed: dict[str, str] = {}
        book_coverage = {
            book: {
                "requestOutcome": "pending",
                "fixturesReturned": 0,
                "officialJoined": 0,
                "moneylineQuotesParsed": 0,
                "error": None,
            }
            for book in books
        }

        last_odds_call_mono = None
        for book in books:
            if last_odds_call_mono is not None:
                wait = 1.05 - (time.monotonic() - last_odds_call_mono)
                if wait > 0:
                    time.sleep(wait)
            started = iso()
            try:
                payload = oddspapi_get("odds-by-tournaments", {
                    "bookmaker": book,
                    "tournamentIds": tournament_id,
                    "language": "en",
                    "verbosity": 3,
                    "oddsFormat": "decimal",
                }, key)
                completed = iso()
                last_odds_call_mono = time.monotonic()
                request_log.append({"endpoint": "odds-by-tournaments", "book": book, "purpose": "MLB supported game markets", "startedAt": started, "completedAt": completed, "outcome": "ok"})
                by_book_observed[book] = completed
                fm = fixture_map(payload)
                by_book[book] = fm
                book_coverage[book]["requestOutcome"] = "ok"
                book_coverage[book]["fixturesReturned"] = len(fm)
            except Exception as exc:
                last_odds_call_mono = time.monotonic()
                err = str(exc)[:300]
                request_log.append({"endpoint": "odds-by-tournaments", "book": book, "purpose": "MLB supported game markets", "startedAt": started, "completedAt": iso(), "outcome": "error", "error": err})
                by_book[book] = {}
                book_coverage[book]["requestOutcome"] = "error"
                book_coverage[book]["error"] = err

        # OddsPapi fixture IDs are bookmaker-scoped. Resolve each bookmaker's
        # fixture independently to the official MLB game, then aggregate quotes
        # by canonical MLB gamePk. Never assume a fixtureId is shared across books.
        fixtures = [fx for fm in by_book.values() for fx in fm.values()]
        names = ensure_participant_names(fixtures, int(sport["sportId"]), key, request_log) if fixtures else {}
        today = now_utc().astimezone(ET).date().isoformat()
        official = official_mlb_schedule(today)
        snapshot_observed = iso()
        max_sharp_skew = int(provider.get("consensusMaxBookSkewSeconds", 120))
        canonical_games: dict[str, dict] = {}
        rejected = []

        for book in books:
            for fid, fx in by_book.get(book, {}).items():
                if not status_is_pregame(fx):
                    continue
                start = parse_iso(fx.get("startTime"))
                if start and start <= now_utc():
                    continue
                p1 = str(fx.get("participant1Id") or "")
                p2 = str(fx.get("participant2Id") or "")
                home = canonical_team(participant_name_from_fixture(fx, 1) or names.get(p1))
                away = canonical_team(participant_name_from_fixture(fx, 2) or names.get(p2))
                if not home or not away:
                    rejected.append({"book": book, "fixtureId": fid, "reason": "participant_identity_unresolved", "participant1Id": p1, "participant2Id": p2})
                    continue
                game, identity_reason = match_official_game(away, home, fx.get("startTime"), official)
                if not game:
                    rejected.append({"book": book, "fixtureId": fid, "away": away, "home": home, "reason": identity_reason})
                    continue
                if str(game.get("abstractState") or "").lower() not in ("preview", ""):
                    rejected.append({"book": book, "fixtureId": fid, "gamePk": game.get("gamePk"), "reason": "official_game_not_pregame"})
                    continue

                pk = str(game["gamePk"])
                entry = canonical_games.get(pk)
                if entry is None:
                    entry = {
                        "game": game,
                        "away": away,
                        "home": home,
                        "identityReasons": [],
                        "fixtureIds": {},
                        "quotes": {},
                    }
                    canonical_games[pk] = entry
                elif entry["away"] != away or entry["home"] != home:
                    rejected.append({"book": book, "fixtureId": fid, "gamePk": pk, "away": away, "home": home, "reason": "canonical_gamePk_team_conflict"})
                    continue

                entry["identityReasons"].append(identity_reason)
                entry["fixtureIds"][book] = fid
                book_coverage[book]["officialJoined"] += 1
                q = extract_moneyline(fx, book, market_id)
                if q:
                    q["observedAt"] = by_book_observed.get(book) or snapshot_observed
                    q["fixtureId"] = fid
                    entry["quotes"][book] = q
                    book_coverage[book]["moneylineQuotesParsed"] += 1

        rows = []
        for pk, entry in canonical_games.items():
            game = entry["game"]
            away = entry["away"]
            home = entry["home"]
            quotes = entry["quotes"]
            fixture_ids = entry["fixtureIds"]
            sharp_quotes = [quotes[b] for b in moneyline_sharp_books if b in quotes]
            consensus = None
            sharp_skew_seconds = None
            consensus_rejection = None
            if len(sharp_quotes) >= 2:
                sharp_times = [parse_iso(q.get("observedAt")) for q in sharp_quotes]
                sharp_times = [t for t in sharp_times if t]
                if len(sharp_times) == len(sharp_quotes):
                    sharp_skew_seconds = (max(sharp_times) - min(sharp_times)).total_seconds()
                if sharp_skew_seconds is not None and sharp_skew_seconds > max_sharp_skew:
                    consensus_rejection = f"sharp_capture_skew_{round(sharp_skew_seconds)}s_exceeds_{max_sharp_skew}s"
                else:
                    consensus = {
                        "homeNoVig": sum(q["homeNoVig"] for q in sharp_quotes) / len(sharp_quotes),
                        "awayNoVig": sum(q["awayNoVig"] for q in sharp_quotes) / len(sharp_quotes),
                        "books": [q["book"] for q in sharp_quotes],
                        "bookGapPP": (max(q["homeNoVig"] for q in sharp_quotes) - min(q["homeNoVig"] for q in sharp_quotes)) * 100,
                        "captureSkewSeconds": sharp_skew_seconds,
                        "kind": "sharp_consensus",
                    }
            elif len(sharp_quotes) == 1:
                consensus = {
                    "homeNoVig": sharp_quotes[0]["homeNoVig"],
                    "awayNoVig": sharp_quotes[0]["awayNoVig"],
                    "books": [sharp_quotes[0]["book"]],
                    "bookGapPP": None,
                    "captureSkewSeconds": 0,
                    "kind": "single_sharp_reference",
                }

            age_basis = sharp_quotes or list(quotes.values())
            age_times = [parse_iso(q.get("observedAt")) for q in age_basis]
            age_times = [t for t in age_times if t]
            market_observed = iso(min(age_times)) if age_times else snapshot_observed

            def best(side: str):
                key_dec = f"{side}Decimal"
                key_am = f"{side}American"
                vals = [(q.get(key_dec), q.get(key_am), b) for b, q in quotes.items() if isinstance(q.get(key_dec), (int, float))]
                if not vals:
                    return None
                vals.sort(key=lambda x: x[0], reverse=True)
                dec, american, best_book = vals[0]
                return {"book": best_book, "decimal": dec, "american": american}

            identity_reasons = [x for x in entry["identityReasons"] if x]
            identity_reason = identity_reasons[0] if identity_reasons else "official MLB gamePk match"
            preferred_fid = fixture_ids.get(moneyline_sharp_books[0]) if moneyline_sharp_books else None
            if not preferred_fid and fixture_ids:
                preferred_fid = next(iter(fixture_ids.values()))

            rows.append({
                "internalEventId": f"mlb:{pk}",
                "sport": "MLB",
                "officialEventId": pk,
                "gamePk": pk,
                "oddsPapiFixtureId": preferred_fid,
                "oddsPapiFixtureIds": dict(fixture_ids),
                "canonicalAggregation": "MLB_GAMEPK",
                "identityStatus": "VERIFIED",
                "identityReason": identity_reason,
                "away": away,
                "home": home,
                "startTime": game.get("startTime"),
                "officialState": game.get("abstractState"),
                "awayStarter": game.get("awayStarter"),
                "homeStarter": game.get("homeStarter"),
                "market": "moneyline",
                "marketId": market_id,
                "quotes": quotes,
                "quoteBookCount": len(quotes),
                "sharpBookCount": len(sharp_quotes),
                "sharp": consensus,
                "sharpCaptureSkewSeconds": sharp_skew_seconds,
                "sharpConsensusRejection": consensus_rejection,
                "bestAvailable": {"away": best("away"), "home": best("home")},
                "observedAt": market_observed,
            })

        rows.sort(key=lambda r: (r.get("startTime") or "", r.get("gamePk") or ""))

        snapshot = {
            "schemaVersion": 1,
            "serviceVersion": VERSION,
            "provider": "OddsPapi",
            "sport": "MLB",
            "observedAt": snapshot_observed,
            "cacheHit": False,
            "requestCount": len(request_log),
            "tournamentRequestCount": len([r for r in request_log if r.get("endpoint") == "odds-by-tournaments"]),
            "requestLog": request_log,
            "booksRequested": books,
            "moneylineBooks": moneyline_books,
            "moneylineSharpBooks": moneyline_sharp_books,
            "bookCoverage": book_coverage,
            "sharpReadyRowCount": len([r for r in rows if r.get("sharp")]),
            "twoSharpConsensusRowCount": len([r for r in rows if len((r.get("sharp") or {}).get("books") or []) >= 2]),
            "multiBookMergedRowCount": len([r for r in rows if len(r.get("quotes") or {}) >= 2]),
            "canonicalGameCount": len(rows),
            "officialScheduleVerification": "PASS",
            "rows": rows,
            "quotaPolicy": {
                "monthlyRequestLimit": 250,
                "playerPropsIncluded": False,
                "playerPropRequestsThisRefresh": 0,
                "playerPropDiscoveryDisabled": True,
                "usage": "supported game markets only",
            },
            "rejected": rejected,
        }
        stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
        market_date = now_utc().astimezone(ET).strftime("%Y-%m-%d")
        immutable = DATA_DIR / "mlb" / market_date / f"market_snapshot_{stamp}.json"
        atomic_json(immutable, snapshot)
        atomic_json(LATEST_MLB, snapshot)
        snapshot["immutablePath"] = str(immutable)
        return snapshot



def _model_repo_candidates() -> list[Path]:
    out=[]
    env=os.environ.get("MODEL_REPO_ROOT")
    if env:
        out.append(Path(env).expanduser())
    # Canonical local-development location used by MODEL. This is only a
    # read-only research bridge; absence simply returns NOT_AVAILABLE.
    out.append(Path.home()/"Developer"/"MODEL")
    # When running directly from the canonical source tree, infer its root.
    try:
        here=Path(__file__).resolve()
        if len(here.parents)>=4:
            out.append(here.parents[3])
    except Exception:
        pass
    seen=set(); dedup=[]
    for root in out:
        key=str(root)
        if key in seen: continue
        seen.add(key); dedup.append(root)
    return dedup


def _find_model_repo() -> Path | None:
    for root in _model_repo_candidates():
        if (root/"data/prospective/nfl/omega").is_dir():
            return root
    return None


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _as_float(v: Any) -> float | None:
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except Exception:
        return None


def _omega_game_parts(game_id: str) -> tuple[str | None,str | None]:
    parts=str(game_id or "").split("_")
    if len(parts)<4:
        return None,None
    return parts[-2] or None,parts[-1] or None


def load_omega_nfl_current(repo_root: Path | None = None) -> dict:
    """Read the current OMEGA tackle probability + market comparison ledgers.

    This is a local, read-only bridge for Matchup Center. It performs no
    network requests, makes no OddsPapi calls, and never mutates OMEGA files.
    """
    root=repo_root or _find_model_repo()
    if root is None:
        return {"provider":"OMEGA local prospective files","status":"NOT_AVAILABLE","reason":"MODEL repository with OMEGA data was not found","probabilityMutation":False,"games":[]}
    base=root/"data/prospective/nfl/omega"
    prob_ptr=base/"CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER"
    cmp_ptr=base/"CURRENT_OMEGA_TACKLE_MARKET_COMPARISON"
    prob_id=prob_ptr.read_text(encoding="utf-8").strip() if prob_ptr.is_file() else ""
    cmp_id=cmp_ptr.read_text(encoding="utf-8").strip() if cmp_ptr.is_file() else ""
    prob_path=base/"tackle_probability_016"/prob_id/"OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv" if prob_id else Path("/__missing__")
    cmp_path=base/"market_comparison_0180"/cmp_id/"OMEGA_0.18.0_MARKET_COMPARISON.csv" if cmp_id else Path("/__missing__")
    prob_rows=_read_csv_rows(prob_path)
    cmp_rows=_read_csv_rows(cmp_path)
    if not prob_rows and not cmp_rows:
        return {"provider":"OMEGA local prospective files","status":"NOT_AVAILABLE","repoRoot":str(root),"probabilityLedgerId":prob_id or None,"marketComparisonId":cmp_id or None,"reason":"Current OMEGA ledgers are missing or empty","probabilityMutation":False,"games":[]}
    games: dict[str,dict] = {}
    def game_entry(game_id: str, team: str | None=None, opponent: str | None=None):
        away,home=_omega_game_parts(game_id)
        if not away and team and opponent:
            away,home=team,opponent
        e=games.setdefault(game_id,{"gameId":game_id,"away":away,"home":home,"kickoffUtc":None,"modelRows":[],"marketRows":[]})
        return e
    for r in prob_rows:
        gid=str(r.get("game_id") or "")
        if not gid: continue
        e=game_entry(gid,r.get("team"),r.get("opponent"))
        e["kickoffUtc"]=e.get("kickoffUtc") or r.get("kickoff_utc") or None
        e["modelRows"].append({
            "player":r.get("player_name") or None,
            "team":r.get("team") or None,
            "opponent":r.get("opponent") or None,
            "position":r.get("position") or None,
            "roleTier":r.get("distribution_role_tier") or None,
            "predictedXtc":_as_float(r.get("predicted_xtc")),
            "predictedSnapShare":_as_float(r.get("predicted_snap_share")),
            "verifiedReady":str(r.get("verified_ready") or "").upper()=="TRUE",
            "verifiedBlockReason":r.get("verified_block_reason") or None,
            "gameStatus":r.get("game_status") or None,
            "injuryDesignation":r.get("injury_designation") or None,
            "listedStarter":str(r.get("listed_starter") or "").upper()=="TRUE",
        })
    for r in cmp_rows:
        gid=str(r.get("game_id_model") or "")
        if not gid: continue
        e=game_entry(gid,r.get("team"),r.get("opponent"))
        over_gap=_as_float(r.get("model_vs_novig_over")); under_gap=_as_float(r.get("model_vs_novig_under"))
        one_side=(r.get("one_sided_side") or "").upper() or None
        if one_side in ("OVER","UNDER"):
            side=one_side; prob=_as_float(r.get("model_p_"+side.lower())); market_prob=_as_float(r.get("one_sided_break_even")); gap=_as_float(r.get("one_sided_prob_edge")); price=_as_float(r.get("one_sided_price"))
        elif over_gap is not None or under_gap is not None:
            side="OVER" if abs(over_gap or 0)>=abs(under_gap or 0) else "UNDER"
            prob=_as_float(r.get("model_p_"+side.lower())); market_prob=_as_float(r.get("market_novig_"+side.lower())); gap=over_gap if side=="OVER" else under_gap; price=_as_float(r.get(("over" if side=="OVER" else "under")+"_price"))
        else:
            side=None; prob=None; market_prob=None; gap=None; price=None
        e["marketRows"].append({
            "player":r.get("player_name") or None,
            "team":r.get("team") or None,
            "opponent":r.get("opponent") or None,
            "line":_as_float(r.get("line")),
            "predictedXtc":_as_float(r.get("predicted_xtc")),
            "predictedSnapShare":_as_float(r.get("predicted_snap_share")),
            "roleTier":r.get("distribution_role_tier") or None,
            "side":side,
            "modelProbability":prob,
            "marketProbability":market_prob,
            "probabilityEdge":gap,
            "priceAmerican":price,
            "book":r.get("book") or None,
            "marketReferenceQuality":r.get("market_reference_quality") or None,
            "actionability":r.get("actionability") or None,
            "blockers":[x for x in str(r.get("actionability_blockers") or "").split(";") if x],
            "verifiedReady":str(r.get("verified_ready") or "").upper()=="TRUE",
            "verifiedBlockReason":r.get("verified_block_reason") or None,
        })
    out=[]
    for e in games.values():
        e["modelRows"].sort(key=lambda x:(not bool(x.get("verifiedReady")),-(x.get("predictedSnapShare") or 0),-(x.get("predictedXtc") or 0)))
        e["marketRows"].sort(key=lambda x:(str(x.get("actionability") or "")!="ACTIONABLE", -abs(x.get("probabilityEdge") or 0)))
        e["modelRows"]=e["modelRows"][:8]
        e["marketRows"]=e["marketRows"][:8]
        e["counts"]={
            "modelRows":len([r for r in prob_rows if str(r.get("game_id") or "")==e["gameId"]]),
            "verifiedReady":sum(1 for r in e["modelRows"] if r.get("verifiedReady")),
            "marketRows":len([r for r in cmp_rows if str(r.get("game_id_model") or "")==e["gameId"]]),
            "actionable":sum(1 for r in e["marketRows"] if r.get("actionability")=="ACTIONABLE"),
        }
        out.append(e)
    out.sort(key=lambda x:(str(x.get("kickoffUtc") or ""),str(x.get("gameId") or "")))
    return {
        "provider":"OMEGA tackle model local bridge",
        "status":"PASS",
        "serviceVersion":VERSION,
        "repoRoot":str(root),
        "probabilityLedgerId":prob_id or None,
        "marketComparisonId":cmp_id or None,
        "gameCount":len(out),
        "games":out,
        "readOnly":True,
        "oddsPapiRequests":0,
        "probabilityMutation":False,
    }


def health() -> dict:
    cfg = load_config()
    latest = load_latest_mlb()
    age = latest_snapshot_age_seconds()
    try:
        _ = get_api_key()
        key_status = "configured"
    except Exception:
        key_status = "missing"
    return {
        "ok": True,
        "service": "MODEL Local Market Service",
        "version": VERSION,
        "time": iso(),
        "oddspapiKey": key_status,
        "latestMlbAgeSeconds": age,
        "latestMlbObservedAt": latest.get("observedAt") if latest else None,
        "sports": cfg.get("sports"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MODELService/2.3"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def _origin(self):
        return str(self.headers.get("Origin") or "")

    def _headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        origin = self._origin()
        if origin.startswith("chrome-extension://"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Model-Token")
        self.end_headers()

    def _authorized(self):
        supplied = str(self.headers.get("X-Model-Token") or "")
        try:
            expected = get_service_token()
        except Exception:
            return False
        return bool(supplied) and hmac.compare_digest(supplied, expected)

    def _send(self, data, status=200):
        self._headers(status)
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        origin = self._origin()
        if origin and not origin.startswith("chrome-extension://"):
            return self._headers(403)
        self._headers(204)

    def do_GET(self):
        try:
            if not self._authorized():
                return self._send({"error": "unauthorized"}, 401)
            u = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(u.query)
            if u.path == "/v1/health":
                return self._send(health())
            if u.path == "/v1/config":
                cfg = load_config()
                # never expose secrets (none are stored here by design)
                return self._send(cfg)
            if u.path == "/v1/nfl/omega/current":
                return self._send(load_omega_nfl_current())
            if u.path == "/v1/markets/latest":
                sport = (qs.get("sport") or ["mlb"])[0].lower()
                if sport != "mlb":
                    return self._send({"error": "sport adapter not enabled", "sport": sport}, 501)
                latest = load_latest_mlb()
                if not latest:
                    return self._send({"error": "no snapshot yet"}, 404)
                latest["cacheAgeSeconds"] = latest_snapshot_age_seconds()
                return self._send(latest)
            if u.path == "/v1/markets/refresh":
                sport = (qs.get("sport") or ["mlb"])[0].lower()
                force = (qs.get("force") or ["0"])[0] == "1"
                if sport != "mlb":
                    return self._send({"error": "sport adapter not enabled", "sport": sport}, 501)
                return self._send(refresh_mlb(force=force))
            if u.path == "/v1/audit":
                cfg = load_config()
                latest = load_latest_mlb()
                return self._send({
                    "serviceVersion": VERSION,
                    "credentialBoundary": "OddsPapi key in macOS Keychain; per-install localhost token authenticates the extension",
                    "provider": "OddsPapi",
                    "persistence": "immutable timestamped snapshots + latest pointer",
                    "canonicalIdentity": "MLB gamePk; bookmaker-specific OddsPapi fixtureIds are joined independently and merged under the canonical game",
                    "failClosedIdentity": True,
                    "productionModelMutation": False,
                    "marketComparisonStage": "post-model only",
                    "localhostAuthentication": "required X-Model-Token; browser CORS restricted to chrome-extension origins",
                    "sportsRegistry": cfg.get("sports"),
                    "latest": {
                        "observedAt": latest.get("observedAt") if latest else None,
                        "rows": len(latest.get("rows") or []) if latest else 0,
                        "booksRequested": latest.get("booksRequested") if latest else [],
                        "requestCount": latest.get("requestCount") if latest else 0,
                        "tournamentRequestCount": latest.get("tournamentRequestCount") if latest else 0,
                        "requestLog": latest.get("requestLog") if latest else [],
                        "bookCoverage": latest.get("bookCoverage") if latest else {},
                        "sharpReadyRowCount": latest.get("sharpReadyRowCount") if latest else 0,
                        "twoSharpConsensusRowCount": latest.get("twoSharpConsensusRowCount") if latest else 0,
                        "multiBookMergedRowCount": latest.get("multiBookMergedRowCount") if latest else 0,
                        "canonicalGameCount": latest.get("canonicalGameCount") if latest else 0,
                        "quotaPolicy": latest.get("quotaPolicy") if latest else None,
                        "rejected": len(latest.get("rejected") or []) if latest else 0,
                        "ageSeconds": latest_snapshot_age_seconds(),
                    },
                })
            return self._send({"error": "not found", "path": u.path}, 404)
        except RuntimeError as exc:
            return self._send({"error": str(exc)}, 503)
        except Exception as exc:
            return self._send({"error": str(exc), "type": type(exc).__name__}, 500)


def main():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    load_config()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"MODEL Local Market Service v{VERSION} listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

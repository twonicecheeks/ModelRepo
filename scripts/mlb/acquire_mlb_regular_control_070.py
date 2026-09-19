#!/usr/bin/env python3
"""Acquire late-regular-season MLB control cohort for postseason regime research.

Cohort:
- seasons represented in the current postseason outcome ledger
- final N calendar days of each regular season (default 7)
- games where at least one participant made that season's postseason

Purpose:
Create a leakage-safe K-control package that can reconstruct pitcher/batter
season-to-date K/Whiff/Swing skill immediately before each control game.

Data:
- MLB regular-season schedules and completed-game boxscores
- MLB starter regular-season game logs
- Baseball Savant full-season reconstruction leaderboards
- Baseball Savant pitch-level Statcast for only the final control-window dates

No betting markets are acquired. No production code is mutated.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import argparse
import csv
import hashlib
import io
import json
import os
import ssl
import subprocess
import time
import uuid

VERSION = "0.7.4"
LINEAGE = "mlb-late-regular-control-v0.7.4-dedupe-coverage-2026-09-19"
MLB_BASE = "https://statsapi.mlb.com/api/v1"
SAVANT_CUSTOM = "https://baseballsavant.mlb.com/leaderboard/custom"
SAVANT_SEARCH = "https://baseballsavant.mlb.com/statcast_search/csv"

RECON_SELECTIONS = [
    "pa",
    "strikeout",
    "walk",
    "k_percent",
    "bb_percent",
    "whiff_percent",
    "swing_percent",
    "pitch_count",
    "in_zone_swing_miss",
    "in_zone_swing",
    "out_zone_swing_miss",
    "out_zone_swing",
]

def tls_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

def certificate_verify_error(exc: BaseException) -> bool:
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ssl.SSLCertVerificationError):
            return True
        if "CERTIFICATE_VERIFY_FAILED" in str(cur).upper():
            return True
        nxt = getattr(cur, "reason", None)
        if isinstance(nxt, BaseException):
            cur = nxt
            continue
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    return False

def curl_bytes(url: str) -> bytes:
    curl = Path("/usr/bin/curl")
    if not curl.exists():
        raise RuntimeError("Python TLS failed and /usr/bin/curl unavailable")
    proc = subprocess.run(
        [
            str(curl), "--fail", "--silent", "--show-error", "--location",
            "--connect-timeout", "20", "--max-time", "180",
            "--header", f"User-Agent: MODEL-MLB-RegularControl/{VERSION}",
            "--header", "Accept: */*", url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl GET failed ({proc.returncode}): {err}")
    return proc.stdout

def fetch_bytes(url: str, retries: int = 4) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": f"MODEL-MLB-RegularControl/{VERSION}",
                    "Accept": "*/*",
                },
            )
            with urlopen(req, timeout=180, context=tls_context()) as resp:
                return resp.read()
        except Exception as exc:
            last = exc
            if certificate_verify_error(exc):
                try:
                    return curl_bytes(url)
                except Exception as curl_exc:
                    last = RuntimeError(
                        f"Python TLS failed ({exc}); curl fallback failed ({curl_exc})"
                    )
            if attempt + 1 < retries:
                time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last}")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)

def fetch_cached(root: Path, rel: str, url: str, kind: str) -> dict:
    path = root / rel
    hit = path.exists()
    if hit:
        data = path.read_bytes()
    else:
        data = fetch_bytes(url)
        atomic_write(path, data)
    validate_payload(kind, data)
    return {
        "path": rel,
        "url": url,
        "kind": kind,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "cache_hit": hit,
    }

def validate_payload(kind: str, data: bytes) -> None:
    if len(data) < 20:
        raise ValueError(f"{kind}: response too small ({len(data)} bytes)")
    if kind == "json":
        obj = json.loads(data.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("JSON response is not an object")
    elif kind in {"csv", "statcast_csv"}:
        text = data[:3000].decode("utf-8", errors="replace").lower()
        if "," not in text:
            raise ValueError(f"{kind}: CSV header not recognized")
        if kind == "statcast_csv" and not all(x in text for x in ("game_pk", "pitcher", "batter")):
            raise ValueError("statcast_csv: required columns absent")

def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise ValueError(f"{path}:{n}: invalid JSON: {exc}") from exc
    if not rows:
        raise ValueError(f"no rows in {path}")
    return rows

def resolve_postseason_outcomes(root: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        return p
    pointer = root / "data/normalized/mlb/CURRENT_HISTORICAL_OUTCOMES_030"
    if not pointer.exists():
        raise FileNotFoundError(pointer)
    out_dir = root / pointer.read_text(encoding="utf-8").strip()
    p = out_dir / "MLB_HISTORICAL_OUTCOMES.jsonl"
    if not p.exists():
        raise FileNotFoundError(p)
    return p

def schedule_url(season: int) -> str:
    q = {
        "sportId": 1,
        "season": str(season),
        "gameTypes": "R",
        "hydrate": "team,linescore,probablePitcher,venue",
    }
    return f"{MLB_BASE}/schedule?{urlencode(q)}"

def boxscore_url(game_pk: int) -> str:
    return f"{MLB_BASE}/game/{int(game_pk)}/boxscore"

def player_game_log_url(player_id: str, season: int) -> str:
    q = {"stats": "gameLog", "group": "pitching", "season": str(season), "gameType": "R"}
    return f"{MLB_BASE}/people/{player_id}/stats?{urlencode(q)}"

def savant_recon_url(year: int, player_type: str) -> str:
    q = {
        "year": str(year),
        "type": player_type,
        "filter": "",
        "min": "1",
        "selections": ",".join(RECON_SELECTIONS),
        "chart": "false",
        "x": "pa",
        "y": "pa",
        "r": "no",
        "chartType": "beeswarm",
        "sort": "pa",
        "sortDir": "desc",
        "csv": "true",
    }
    return f"{SAVANT_CUSTOM}?{urlencode(q)}"

def statcast_day_url(year: int, iso_date: str) -> str:
    # Regular season only. Same-day gt/lt semantics are the convention used
    # by public Statcast clients such as pybaseball/baseballr.
    q = {
        "all": "true",
        "hfPT": "",
        "hfAB": "",
        "hfBBT": "",
        "hfPR": "",
        "hfZ": "",
        "stadium": "",
        "hfBBL": "",
        "hfNewZones": "",
        "hfGT": "R|",
        "hfSea": f"{year}|",
        "hfSit": "",
        "player_type": "pitcher",
        "hfOuts": "",
        "opponent": "",
        "pitcher_throws": "",
        "batter_stands": "",
        "hfSA": "",
        "game_date_gt": iso_date,
        "game_date_lt": iso_date,
        "team": "",
        "position": "",
        "hfRO": "",
        "home_road": "",
        "hfFlag": "",
        "metric_1": "",
        "hfInn": "",
        "min_pitches": "0",
        "min_results": "0",
        "group_by": "name",
        "sort_col": "pitches",
        "player_event_sort": "h_launch_speed",
        "sort_order": "desc",
        "min_abs": "0",
        "type": "details",
    }
    return f"{SAVANT_SEARCH}?{urlencode(q)}"

def final_game(g: dict) -> bool:
    st = g.get("status") or {}
    abstract = str(st.get("abstractGameState") or "").lower()
    coded = str(st.get("codedGameState") or "").upper()
    return abstract == "final" or coded in {"F", "O"}

def flatten_schedule(payload: dict) -> list[dict]:
    out = []
    for d in payload.get("dates") or []:
        for g in d.get("games") or []:
            if final_game(g):
                out.append(g)
    return out

def _game_quality(g: dict) -> tuple[int, str]:
    teams = g.get("teams") or {}
    away = teams.get("away") or {}
    home = teams.get("home") or {}
    score = 0
    if away.get("score") is not None:
        score += 2
    if home.get("score") is not None:
        score += 2
    if (away.get("team") or {}).get("id") is not None:
        score += 1
    if (home.get("team") or {}).get("id") is not None:
        score += 1
    if g.get("gameDate"):
        score += 1
    if (g.get("venue") or {}).get("id") is not None:
        score += 1
    return score, str(g.get("officialDate") or "")

def dedupe_schedule_games(games: list[dict]) -> tuple[list[dict], int]:
    grouped: dict[int, list[dict]] = {}
    for g in games:
        pk = int(g["gamePk"])
        grouped.setdefault(pk, []).append(g)
    out = []
    duplicate_rows = 0
    for pk, rows in grouped.items():
        duplicate_rows += max(0, len(rows) - 1)
        # Prefer the most complete final representation. For equally complete
        # representations use the earliest official date to preserve the
        # original game placement rather than a later resume/completion listing.
        best = sorted(rows, key=lambda g: (-_game_quality(g)[0], _game_quality(g)[1]))[0]
        if len(rows) > 1:
            dates = sorted(
                str(g.get("officialDate") or "")[:10]
                for g in rows
                if g.get("officialDate")
            )
            starts = sorted(
                str(g.get("gameDate") or "")
                for g in rows
                if g.get("gameDate")
            )
            best = dict(best)
            if dates:
                best["officialDate"] = dates[0]
            if starts:
                best["gameDate"] = starts[0]
        out.append(best)
    out.sort(key=lambda g: (str(g.get("officialDate") or ""), int(g["gamePk"])))
    return out, duplicate_rows

def original_starter_from_box(team_box: dict) -> dict | None:
    pitchers = [str(x) for x in (team_box.get("pitchers") or [])]
    players = team_box.get("players") or {}
    for pid in pitchers:
        p = players.get("ID" + pid) or {}
        st = ((p.get("stats") or {}).get("pitching") or {})
        if int(float(st.get("gamesStarted") or 0)) == 1:
            return {
                "mlb_id": pid,
                "name": (p.get("person") or {}).get("fullName"),
                "strikeouts": safe_num(st.get("strikeOuts")),
                "innings_pitched": st.get("inningsPitched"),
                "batters_faced": safe_num(st.get("battersFaced")),
                "pitches": safe_num(st.get("numberOfPitches")),
                "hits": safe_num(st.get("hits")),
                "earned_runs": safe_num(st.get("earnedRuns")),
                "walks": safe_num(st.get("baseOnBalls")),
            }
    if pitchers:
        pid = pitchers[0]
        p = players.get("ID" + pid) or {}
        st = ((p.get("stats") or {}).get("pitching") or {})
        return {
            "mlb_id": pid,
            "name": (p.get("person") or {}).get("fullName"),
            "strikeouts": safe_num(st.get("strikeOuts")),
            "innings_pitched": st.get("inningsPitched"),
            "batters_faced": safe_num(st.get("battersFaced")),
            "pitches": safe_num(st.get("numberOfPitches")),
            "hits": safe_num(st.get("hits")),
            "earned_runs": safe_num(st.get("earnedRuns")),
            "walks": safe_num(st.get("baseOnBalls")),
        }
    return None

def safe_num(v):
    try:
        n = float(v)
        return int(n) if n.is_integer() else n
    except Exception:
        return None

def control_target(g: dict, box: dict, postseason_team_ids: set[int], season_end: date) -> dict:
    game_pk = int(g["gamePk"])
    teams = g.get("teams") or {}
    away = teams.get("away") or {}
    home = teams.get("home") or {}
    away_team = away.get("team") or {}
    home_team = home.get("team") or {}
    away_score = safe_num(away.get("score"))
    home_score = safe_num(home.get("score"))
    if away_score is None or home_score is None:
        raise ValueError(f"game {game_pk}: final score unavailable")
    tied = away_score == home_score
    bt = box.get("teams") or {}
    ast = original_starter_from_box(bt.get("away") or {})
    hst = original_starter_from_box(bt.get("home") or {})
    if not ast or not hst:
        raise ValueError(f"game {game_pk}: starter resolution failed")
    a_id = int(away_team["id"])
    h_id = int(home_team["id"])
    n_post = int(a_id in postseason_team_ids) + int(h_id in postseason_team_ids)
    iso = str(g.get("officialDate") or "")[:10]
    gd = date.fromisoformat(iso)
    return {
        "source": "MLB Stats API late-regular-season control",
        "source_role": "OUTCOME_TARGET_ONLY",
        "control_cohort": "LATE_REG_POSTSEASON_TEAM",
        "control_match_quality": "BOTH_POSTSEASON_TEAMS" if n_post == 2 else "ONE_POSTSEASON_TEAM",
        "postseason_team_count": n_post,
        "game_pk": game_pk,
        "game_id": str(game_pk),
        "game_date": iso,
        "game_datetime": g.get("gameDate"),
        "season": int(str(g.get("season") or iso[:4])),
        "game_type": "R",
        "season_type": "REG",
        "days_to_regular_season_end": (season_end - gd).days,
        "venue_id": (g.get("venue") or {}).get("id"),
        "venue_name": (g.get("venue") or {}).get("name"),
        "away": {
            "team_id": a_id,
            "name": away_team.get("name"),
            "score": away_score,
            "starter": ast,
        },
        "home": {
            "team_id": h_id,
            "name": home_team.get("name"),
            "score": home_score,
            "starter": hst,
        },
        "actual_home_win": None if tied else (1 if home_score > away_score else 0),
        "outcome_tied": tied,
        "outcome_is_postgame_only": True,
    }

def main() -> int:
    ap = argparse.ArgumentParser(description="Acquire late regular-season MLB control cohort")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--postseason-outcomes", default=None)
    ap.add_argument("--window-days", type=int, default=7)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    postseason_path = resolve_postseason_outcomes(root, args.postseason_outcomes)
    post = [r for r in load_jsonl(postseason_path) if str(r.get("season_type")).upper() == "POST"]
    if not post:
        raise ValueError("no postseason rows")

    postseason_teams: dict[int, set[int]] = {}
    for r in post:
        season = int(r["season"])
        postseason_teams.setdefault(season, set())
        postseason_teams[season].update([int(r["away"]["team_id"]), int(r["home"]["team_id"])])
    seasons = sorted(postseason_teams)

    assets: list[dict] = []
    source_errors: list[dict] = []
    target_exclusions: list[dict] = []
    schedules: dict[int, dict] = {}
    selected_games: list[tuple[int, dict, date]] = []
    duplicate_schedule_rows = 0

    for season in seasons:
        rel = f"data/raw/mlb/regular_control_070/mlb/schedule/{season}.json"
        a = fetch_cached(root, rel, schedule_url(season), "json")
        assets.append(a)
        payload = json.loads((root / rel).read_text(encoding="utf-8"))
        schedules[season] = payload
        games_raw = flatten_schedule(payload)
        games, dupes = dedupe_schedule_games(games_raw)
        duplicate_schedule_rows += dupes
        if not games:
            raise ValueError(f"{season}: no completed regular-season games")
        end = max(date.fromisoformat(str(g["officialDate"])[:10]) for g in games)
        start = end - timedelta(days=max(1, args.window_days) - 1)
        team_ids = postseason_teams[season]
        sel = []
        for g in games:
            gd = date.fromisoformat(str(g["officialDate"])[:10])
            if gd < start or gd > end:
                continue
            teams = g.get("teams") or {}
            ids = {
                int((teams.get(side) or {}).get("team", {}).get("id"))
                for side in ("away", "home")
                if (teams.get(side) or {}).get("team", {}).get("id") is not None
            }
            if ids.intersection(team_ids):
                sel.append(g)
                selected_games.append((season, g, end))
        print(
            f"CONTROL {season}: postseason teams {len(team_ids)} · "
            f"season end {end} · selected {len(sel)} games"
        )

    # Preload Savant reconstruction leaderboards for current and previous years.
    years = sorted(set(seasons) | {s - 1 for s in seasons if s - 1 >= 2015})
    recon_requests: dict[str, tuple[str, str]] = {}
    for year in years:
        for player_type in ("pitcher", "batter"):
            rel = f"data/raw/mlb/regular_control_070/savant_recon/{year}/{player_type}.csv"
            recon_requests[rel] = (savant_recon_url(year, player_type), "csv")

    # Daily Statcast only for dates that can be at/after a selected control game.
    day_requests: dict[str, tuple[str, str]] = {}
    for season in seasons:
        games = flatten_schedule(schedules[season])
        end = max(date.fromisoformat(str(g["officialDate"])[:10]) for g in games)
        start = end - timedelta(days=max(1, args.window_days) - 1)
        d = start
        while d <= end:
            iso = d.isoformat()
            rel = f"data/raw/mlb/regular_control_070/statcast_day/{season}/{iso}.csv"
            day_requests[rel] = (statcast_day_url(season, iso), "statcast_csv")
            d += timedelta(days=1)

    def run_requests(reqs: dict[str, tuple[str, str]], label: str):
        items = sorted(reqs.items())
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 6))) as ex:
            futs = {
                ex.submit(fetch_cached, root, rel, url, kind): rel
                for rel, (url, kind) in items
            }
            for i, fut in enumerate(as_completed(futs), 1):
                rel = futs[fut]
                try:
                    assets.append(fut.result())
                except Exception as exc:
                    source_errors.append({"path": rel, "error": str(exc)})
                if i % 25 == 0 or i == len(items):
                    print(f"{label} {i}/{len(items)} · source errors {len(source_errors)}")

    run_requests(recon_requests, "SAVANT RECON")
    run_requests(day_requests, "STATCAST DAYS")

    # Control-game boxscores.
    box_reqs = {}
    for season, g, _ in selected_games:
        pk = int(g["gamePk"])
        rel = f"data/raw/mlb/regular_control_070/mlb/boxscore/{pk}.json"
        box_reqs[rel] = (boxscore_url(pk), "json")
    run_requests(box_reqs, "CONTROL BOXSCORES")

    # Build targets and discover starter game logs.
    targets = []
    starter_reqs: dict[str, tuple[str, str]] = {}
    for season, g, season_end in selected_games:
        pk = int(g["gamePk"])
        bp = root / f"data/raw/mlb/regular_control_070/mlb/boxscore/{pk}.json"
        if not bp.exists():
            target_exclusions.append({"game_pk": pk, "error": "boxscore missing after acquisition"})
            continue
        try:
            row = control_target(g, json.loads(bp.read_text(encoding="utf-8")), postseason_teams[season], season_end)
            row["boxscore_cache_path"] = str(bp.relative_to(root))
            targets.append(row)
            for side in ("away", "home"):
                pid = str(row[side]["starter"]["mlb_id"])
                rel = f"data/raw/mlb/regular_control_070/mlb/starter_gamelog/{season}/{pid}.json"
                starter_reqs.setdefault(rel, (player_game_log_url(pid, season), "json"))
        except Exception as exc:
            target_exclusions.append({"game_pk": pk, "error": str(exc)})

    run_requests(starter_reqs, "STARTER GAMELOGS")

    targets.sort(key=lambda r: (r["game_date"], r["game_pk"]))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/normalized/mlb/regular_control_070" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    out = out_dir / "MLB_REGULAR_CONTROL_TARGETS.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for row in targets:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    schedule_index = {}
    for season, payload in schedules.items():
        schedule_index[str(season)] = [
            {
                "game_pk": int(g["gamePk"]),
                "game_datetime": g.get("gameDate"),
                "game_date": str(g.get("officialDate") or "")[:10],
                "away_team_id": (g.get("teams") or {}).get("away", {}).get("team", {}).get("id"),
                "home_team_id": (g.get("teams") or {}).get("home", {}).get("team", {}).get("id"),
            }
            for g in flatten_schedule(payload)
        ]
    sched_out = out_dir / "REGULAR_SCHEDULE_INDEX.json"
    sched_out.write_text(json.dumps(schedule_index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # De-duplicate assets.
    by_path = {a["path"]: a for a in assets}
    assets = [by_path[k] for k in sorted(by_path)]
    manifest = {
        "version": VERSION,
        "lineage": LINEAGE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "postseason_outcomes_path": str(postseason_path),
        "postseason_outcomes_sha256": sha256_file(postseason_path),
        "seasons": seasons,
        "window_days": args.window_days,
        "control_definition": "final N calendar days; at least one team made same-season postseason",
        "target_games": len(targets),
        "both_postseason_team_games": sum(1 for r in targets if r["control_match_quality"] == "BOTH_POSTSEASON_TEAMS"),
        "one_postseason_team_games": sum(1 for r in targets if r["control_match_quality"] == "ONE_POSTSEASON_TEAM"),
        "assets": assets,
        "asset_count": len(assets),
        "cache_hits": sum(1 for a in assets if a["cache_hit"]),
        "downloads": sum(1 for a in assets if not a["cache_hit"]),
        "source_errors": source_errors,
        "source_error_count": len(source_errors),
        "target_exclusions": target_exclusions,
        "target_exclusion_count": len(target_exclusions),
        "duplicate_schedule_rows_removed": duplicate_schedule_rows,
        "errors": source_errors,
        "error_count": len(source_errors),
        "target_path": str(out.relative_to(root)),
        "target_sha256": sha256_file(out),
        "schedule_index_path": str(sched_out.relative_to(root)),
        "schedule_index_sha256": sha256_file(sched_out),
        "historical_betting_market": "NOT_ACQUIRED",
        "pregame_reconstruction": {
            "method": "full-season Savant raw-count aggregate minus target-and-future final-window Statcast events",
            "same_game_removed": True,
            "future_games_removed": True,
            "raw_statcast_scope": "regular season only",
        },
        "oddsPapi_requests": 0,
        "production_model_mutation": False,
        "model_refit_performed": False,
    }
    mp = out_dir / "REGULAR_CONTROL_MANIFEST.json"
    mp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    atomic_write(
        root / "data/normalized/mlb/CURRENT_REGULAR_CONTROL_070",
        (str(out_dir.relative_to(root)) + "\n").encode("utf-8"),
    )

    print()
    print(f"MLB LATE REGULAR CONTROL {VERSION}")
    print(
        f"Targets: {len(targets):,} · BOTH postseason teams {manifest['both_postseason_team_games']:,} · "
        f"ONE postseason team {manifest['one_postseason_team_games']:,}"
    )
    print(
        f"Assets: {len(assets):,} · cache hits {manifest['cache_hits']:,} · "
        f"downloads {manifest['downloads']:,} · source errors {len(source_errors)} · "
        f"target exclusions {len(target_exclusions)}"
    )
    print(f"Duplicate schedule rows removed: {duplicate_schedule_rows}")
    for x in target_exclusions[:20]:
        print(f"EXCLUDED target {x.get('game_pk')}: {x.get('error')}")
    print("Historical betting markets: NOT ACQUIRED")
    print("OddsPapi: 0 · production mutation: NO · refit: NO")
    print(f"Targets: {out}")
    print(f"Manifest: {mp}")
    return 1 if source_errors else 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Acquire leakage-safe raw priors for MLB postseason historical replay 0.4.0.

This collector intentionally separates pregame-eligible priors from outcome targets.
It downloads only sources that can be known before each postseason game:
- completed regular-season Baseball Savant skill leaderboards (current + prior season)
- completed regular-season FanGraphs wRC+ leaderboards
- season-end Baseball Savant park factors
- historical active rosters as of each postseason game date
- regular-season team pitching stats for bullpen quality
- starter regular-season game logs for workload/history proxies
- prior-day MLB schedules/boxscores for bullpen-rest state

It does NOT acquire or synthesize historical betting markets.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import argparse
import hashlib
import json
import os
import ssl
import subprocess
import time
import uuid

VERSION = "0.4.1"
LINEAGE = "mlb-postseason-pregame-priors-v0.4.1-statcast-boundary-2026-09-19"
MLB_BASE = "https://statsapi.mlb.com/api/v1"
SAVANT_CUSTOM = "https://baseballsavant.mlb.com/leaderboard/custom"
SAVANT_PARK = "https://baseballsavant.mlb.com/leaderboard/statcast-park-factors"
FANGRAPHS_WRC = "https://www.fangraphs.com/api/leaders/major-league/data"
SAVANT_SELECTIONS = [
    "pa","k_percent","bb_percent","batting_avg","xba","xslg","xwoba",
    "isolated_power","hard_hit_percent","barrel_batted_rate",
    "whiff_percent","swing_percent",
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
        raise RuntimeError("Python TLS failed and /usr/bin/curl is unavailable")
    proc = subprocess.run(
        [
            str(curl), "--fail", "--silent", "--show-error", "--location",
            "--connect-timeout", "20", "--max-time", "120",
            "--header", f"User-Agent: MODEL-MLB-PostseasonPriors/{VERSION}",
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
                    "User-Agent": f"MODEL-MLB-PostseasonPriors/{VERSION}",
                    "Accept": "*/*",
                },
            )
            with urlopen(req, timeout=120, context=tls_context()) as resp:
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


def validate_payload(kind: str, data: bytes) -> None:
    if len(data) < 20:
        raise ValueError(f"{kind}: response too small ({len(data)} bytes)")
    if kind in {"mlb_json", "fangraphs_json"}:
        obj = json.loads(data.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError(f"{kind}: expected JSON object")
    elif kind == "savant_csv":
        head = data[:1000].decode("utf-8", errors="replace").lower()
        if "," not in head or ("player" not in head and "last_name" not in head):
            raise ValueError("savant_csv: CSV header not recognized")
    elif kind == "park_html":
        head = data[:5000].decode("utf-8", errors="replace").lower()
        if "<html" not in head and "park" not in head:
            raise ValueError("park_html: HTML response not recognized")


def cache_asset(root: Path, rel: str, url: str, kind: str) -> dict:
    path = root / rel
    cache_hit = path.exists()
    if cache_hit:
        data = path.read_bytes()
        validate_payload(kind, data)
    else:
        data = fetch_bytes(url)
        validate_payload(kind, data)
        atomic_write(path, data)
    return {
        "kind": kind,
        "path": rel,
        "url": url,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "cache_hit": cache_hit,
    }


def savant_custom_url(year: int, player_type: str) -> str:
    q = {
        "year": str(year),
        "type": player_type,
        "filter": "",
        "min": "1",
        "selections": ",".join(SAVANT_SELECTIONS),
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


def fangraphs_wrc_url(year: int) -> str:
    q = {
        "age": "", "pos": "all", "stats": "bat", "lg": "all", "qual": "0",
        "season": str(year), "season1": str(year), "startdate": "", "enddate": "",
        "month": "0", "hand": "", "team": "0", "pageitems": "2000", "pagenum": "1",
        "ind": "0", "rost": "0", "players": "0", "type": "8", "postseason": "",
        "sortdir": "default", "sortstat": "WAR",
    }
    return f"{FANGRAPHS_WRC}?{urlencode(q)}"


def park_url(year: int, rolling: int) -> str:
    q = {
        "condition": "All", "parks": "mlb", "rolling": str(rolling),
        "stat": "index_wOBA", "type": "year", "year": str(year),
    }
    return f"{SAVANT_PARK}?{urlencode(q)}"


def roster_url(team_id: int, year: int, iso_date: str) -> str:
    q = {
        "rosterType": "active", "season": str(year), "date": iso_date,
        "hydrate": "person",
    }
    return f"{MLB_BASE}/teams/{team_id}/roster?{urlencode(q)}"


def team_pitching_url(team_id: int, year: int) -> str:
    q = {
        "stats": "season", "group": "pitching", "season": str(year),
        "teamId": str(team_id), "playerPool": "All", "gameType": "R",
        "limit": "100", "hydrate": "person",
    }
    return f"{MLB_BASE}/stats?{urlencode(q)}"


def player_game_log_url(player_id: str, year: int) -> str:
    q = {
        "stats": "gameLog", "group": "pitching", "season": str(year),
        "gameType": "R",
    }
    return f"{MLB_BASE}/people/{player_id}/stats?{urlencode(q)}"


def schedule_date_url(iso_date: str) -> str:
    q = {
        "sportId": "1", "date": iso_date, "gameTypes": "R,F,D,L,W",
        "hydrate": "team",
    }
    return f"{MLB_BASE}/schedule?{urlencode(q)}"


def boxscore_url(game_pk: int) -> str:
    return f"{MLB_BASE}/game/{int(game_pk)}/boxscore"


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


def resolve_outcomes(root: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        return p
    pointer = root / "data/normalized/mlb/CURRENT_HISTORICAL_OUTCOMES_030"
    if not pointer.exists():
        raise FileNotFoundError(
            f"{pointer} missing; run acquire_mlb_postseason_outcomes_030.command first"
        )
    target = root / pointer.read_text(encoding="utf-8").strip()
    p = target / "MLB_HISTORICAL_OUTCOMES.jsonl"
    if not p.exists():
        raise FileNotFoundError(p)
    return p


def prior_date(iso_date: str) -> str:
    return (date.fromisoformat(iso_date) - timedelta(days=1)).isoformat()


def asset_key(a: dict) -> tuple[str, str]:
    return a["kind"], a["path"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Acquire MLB postseason pregame priors 0.4.0")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--outcomes", default=None)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    outcomes_path = resolve_outcomes(root, args.outcomes)
    rows = load_jsonl(outcomes_path)
    rows = [r for r in rows if str(r.get("season_type", "")).upper() == "POST"]
    if not rows:
        raise ValueError("outcome ledger contains no postseason rows")

    seasons = sorted({int(r["season"]) for r in rows})
    years_needed = sorted(set(seasons) | {s - 1 for s in seasons})
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]

    requests: dict[str, tuple[str, str]] = {}

    def add(rel: str, url: str, kind: str):
        requests.setdefault(rel, (url, kind))

    # Season-end priors. For postseason dates, the current season's regular
    # season is complete, so these are pregame-eligible.
    for year in years_needed:
        if year >= 2015:
            for ptype in ("pitcher", "batter"):
                add(
                    f"data/raw/mlb/historical_priors_040/savant/{year}/{ptype}.csv",
                    savant_custom_url(year, ptype),
                    "savant_csv",
                )
        add(
            f"data/raw/mlb/historical_priors_040/fangraphs/{year}/wrc.json",
            fangraphs_wrc_url(year),
            "fangraphs_json",
        )
    for year in seasons:
        for rolling in (3, 2, 1):
            add(
                f"data/raw/mlb/historical_priors_040/park/{year}/rolling_{rolling}.html",
                park_url(year, rolling),
                "park_html",
            )

    team_seasons: set[tuple[int, int]] = set()
    starter_seasons: set[tuple[str, int]] = set()
    game_team_dates: set[tuple[int, int, str]] = set()
    prior_dates: set[str] = set()
    postseason_team_ids: set[int] = set()

    for r in rows:
        season = int(r["season"])
        iso = str(r["game_date"])[:10]
        for side in ("away", "home"):
            team = r.get(side) or {}
            tid = int(team["team_id"])
            postseason_team_ids.add(tid)
            team_seasons.add((tid, season))
            game_team_dates.add((tid, season, iso))
            st = team.get("starter") or {}
            if st.get("mlb_id"):
                starter_seasons.add((str(st["mlb_id"]), season))
        prior_dates.add(prior_date(iso))

    for tid, season in sorted(team_seasons):
        add(
            f"data/raw/mlb/historical_priors_040/mlb/team_pitching/{season}/{tid}.json",
            team_pitching_url(tid, season),
            "mlb_json",
        )
    for tid, season, iso in sorted(game_team_dates):
        add(
            f"data/raw/mlb/historical_priors_040/mlb/roster/{iso}/{tid}.json",
            roster_url(tid, season, iso),
            "mlb_json",
        )
    for pid, season in sorted(starter_seasons):
        add(
            f"data/raw/mlb/historical_priors_040/mlb/starter_gamelog/{season}/{pid}.json",
            player_game_log_url(pid, season),
            "mlb_json",
        )
    for iso in sorted(prior_dates):
        add(
            f"data/raw/mlb/historical_priors_040/mlb/prior_day_schedule/{iso}.json",
            schedule_date_url(iso),
            "mlb_json",
        )

    print(
        f"POSTSEASON PRIOR REQUEST PLAN: {len(rows)} games · "
        f"{seasons[0]}-{seasons[-1]} · {len(requests)} base assets"
    )

    assets: list[dict] = []
    errors: list[dict] = []

    def work(item):
        rel, (url, kind) = item
        return cache_asset(root, rel, url, kind)

    items = sorted(requests.items())
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 6))) as ex:
        futs = {ex.submit(work, item): item[0] for item in items}
        for i, fut in enumerate(as_completed(futs), 1):
            rel = futs[fut]
            try:
                assets.append(fut.result())
            except Exception as exc:
                errors.append({"path": rel, "error": str(exc)})
            if i % 50 == 0 or i == len(items):
                print(
                    f"PRIORS {i}/{len(items)} · ok {len(assets)} · errors {len(errors)}"
                )

    # Parse prior-day schedules after they are cached and add only boxscores
    # involving teams present in this postseason sample.
    prior_box_requests: dict[str, tuple[str, str]] = {}
    for iso in sorted(prior_dates):
        p = root / f"data/raw/mlb/historical_priors_040/mlb/prior_day_schedule/{iso}.json"
        if not p.exists():
            continue
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append({"path": str(p.relative_to(root)), "error": f"schedule parse: {exc}"})
            continue
        for d in payload.get("dates") or []:
            for g in d.get("games") or []:
                teams = g.get("teams") or {}
                ids = {
                    int((teams.get(side) or {}).get("team", {}).get("id"))
                    for side in ("away", "home")
                    if (teams.get(side) or {}).get("team", {}).get("id") is not None
                }
                if not ids.intersection(postseason_team_ids):
                    continue
                pk = g.get("gamePk")
                if pk is None:
                    continue
                rel = f"data/raw/mlb/historical_priors_040/mlb/prior_day_boxscore/{int(pk)}.json"
                prior_box_requests.setdefault(rel, (boxscore_url(int(pk)), "mlb_json"))

    if prior_box_requests:
        box_items = sorted(prior_box_requests.items())
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 6))) as ex:
            futs = {ex.submit(work, item): item[0] for item in box_items}
            for i, fut in enumerate(as_completed(futs), 1):
                rel = futs[fut]
                try:
                    assets.append(fut.result())
                except Exception as exc:
                    errors.append({"path": rel, "error": str(exc)})
                if i % 25 == 0 or i == len(box_items):
                    print(
                        f"PRIOR-DAY BOXES {i}/{len(box_items)} · "
                        f"total ok {len(assets)} · errors {len(errors)}"
                    )

    # De-duplicate in case future refactors cause overlap.
    dedup = {}
    for a in assets:
        dedup[asset_key(a)] = a
    assets = sorted(dedup.values(), key=lambda x: x["path"])

    manifest_dir = root / "data/normalized/mlb/postseason_priors_040" / run_id
    manifest_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "version": VERSION,
        "lineage": LINEAGE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "outcomes_path": str(outcomes_path),
        "outcomes_sha256": sha256_file(outcomes_path),
        "postseason_games": len(rows),
        "seasons": seasons,
        "season_end_skill_years": years_needed,
        "statcast_skill_years": [y for y in years_needed if y >= 2015],
        "statcast_boundary_note": "Statcast skill acquisition begins in 2015; no 2014 Statcast fallback is fabricated.",
        "assets": assets,
        "asset_count": len(assets),
        "cache_hits": sum(1 for a in assets if a["cache_hit"]),
        "downloads": sum(1 for a in assets if not a["cache_hit"]),
        "errors": errors,
        "error_count": len(errors),
        "eligibility": {
            "savant_skill": "PREGAME_SAFE_FOR_POSTSEASON_REGULAR_SEASON_COMPLETE",
            "fangraphs_wrc": "PREGAME_SAFE_FOR_POSTSEASON_REGULAR_SEASON_COMPLETE",
            "park_factors": "PREGAME_SAFE_FOR_POSTSEASON_REGULAR_SEASON_COMPLETE",
            "active_roster": "PREGAME_DATE_SCOPED",
            "team_pitching": "REGULAR_SEASON_ONLY",
            "starter_gamelog": "REGULAR_SEASON_ONLY",
            "prior_day_usage": "PAST_GAMES_ONLY",
            "historical_betting_market": "NOT_ACQUIRED",
        },
        "historical_market_dependency": False,
        "oddsPapi_requests": 0,
        "production_model_mutation": False,
        "model_refit_performed": False,
    }
    manifest_path = manifest_dir / "POSTSEASON_PRIORS_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    atomic_write(
        root / "data/normalized/mlb/CURRENT_POSTSEASON_PRIORS_040",
        (str(manifest_dir.relative_to(root)) + "\n").encode("utf-8"),
    )

    print()
    print(f"MLB POSTSEASON PRIORS {VERSION}")
    print(f"Games: {len(rows):,} · seasons {seasons[0]}-{seasons[-1]}")
    print(
        f"Assets: {len(assets):,} · cache hits {manifest['cache_hits']:,} · "
        f"downloads {manifest['downloads']:,} · errors {len(errors)}"
    )
    print("Historical betting markets: NOT ACQUIRED")
    print("OddsPapi: 0 · production mutation: NO · refit: NO")
    print(f"Manifest: {manifest_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""Acquire immutable MLB historical outcome targets from the public MLB Stats API.

Postseason-first by design: --scope postseason fetches only F/D/L/W games.
This source supplies RESULTS only. It must never be used as a pregame feature source.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
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

BASE = "https://statsapi.mlb.com/api/v1"
POST_TYPES = ("F", "D", "L", "W")
REG_TYPES = ("R",)
VERSION = "0.3.2"
LINEAGE = "mlb-statsapi-historical-outcomes-v0.3.2-venue-2026-09-19"


def tls_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


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


def fetch_json_with_curl(url: str) -> dict:
    curl = Path("/usr/bin/curl")
    if not curl.exists():
        raise RuntimeError("Python TLS verification failed and /usr/bin/curl is unavailable")
    proc = subprocess.run(
        [
            str(curl),
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--connect-timeout",
            "20",
            "--max-time",
            "60",
            "--header",
            "User-Agent: MODEL-MLB-HistoricalValidation/0.3.2",
            "--header",
            "Accept: application/json",
            url,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl GET failed ({proc.returncode}): {err}")
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"curl returned invalid JSON from {url}: {exc}") from exc


def fetch_json(url: str, retries: int = 4) -> dict:
    last = None
    for attempt in range(retries):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": "MODEL-MLB-HistoricalValidation/0.3.2",
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=60, context=tls_context()) as resp:
                return json.load(resp)
        except Exception as exc:
            last = exc
            if certificate_verify_error(exc):
                # macOS Python installations can lack the system trust chain even
                # while the OS-native curl transport verifies the same HTTPS peer.
                # Preserve certificate verification; never use an unverified context.
                try:
                    return fetch_json_with_curl(url)
                except Exception as curl_exc:
                    last = RuntimeError(f"Python TLS failed ({exc}); curl fallback failed ({curl_exc})")
            if attempt + 1 < retries:
                time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last}")


def parse_seasons(spec: str) -> list[int]:
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a), int(b)
            out.update(range(min(lo, hi), max(lo, hi) + 1))
        else:
            out.add(int(part))
    vals = sorted(out)
    if not vals:
        raise ValueError("no seasons selected")
    return vals


def schedule_for_season(season: int, game_types: tuple[str, ...]) -> list[dict]:
    params = urlencode(
        {
            "sportId": 1,
            "season": season,
            "gameTypes": ",".join(game_types),
            "hydrate": "team,linescore,probablePitcher,venue",
        }
    )
    payload = fetch_json(f"{BASE}/schedule?{params}")
    games = []
    for d in payload.get("dates") or []:
        for g in d.get("games") or []:
            games.append(g)
    return games


def final_game(g: dict) -> bool:
    st = g.get("status") or {}
    abstract = str(st.get("abstractGameState") or "").lower()
    coded = str(st.get("codedGameState") or "").upper()
    return abstract == "final" or coded in {"F", "O"}


def boxscore_cached(root: Path, game_pk: int) -> tuple[dict, Path, bool]:
    cache = root / "data/raw/mlb/statsapi/boxscore" / f"{game_pk}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8")), cache, True
    payload = fetch_json(f"{BASE}/game/{game_pk}/boxscore")
    atomic_write(cache, json.dumps(payload, sort_keys=True).encode("utf-8"))
    return payload, cache, False


def n(v, default=None):
    try:
        return int(v)
    except Exception:
        try:
            return float(v)
        except Exception:
            return default


def starter_from_team(team_box: dict) -> dict | None:
    pitchers = [str(x) for x in (team_box.get("pitchers") or [])]
    players = team_box.get("players") or {}
    if not pitchers:
        return None

    chosen = None
    for pid in pitchers:
        p = players.get("ID" + pid) or {}
        pitching = ((p.get("stats") or {}).get("pitching") or {})
        if n(pitching.get("gamesStarted"), 0) == 1:
            chosen = pid
            break
    if chosen is None:
        chosen = pitchers[0]

    p = players.get("ID" + chosen) or {}
    person = p.get("person") or {}
    pitching = ((p.get("stats") or {}).get("pitching") or {})
    return {
        "mlb_id": chosen,
        "name": person.get("fullName") or p.get("namefield") or None,
        "strikeouts": n(pitching.get("strikeOuts")),
        "innings_pitched": pitching.get("inningsPitched"),
        "batters_faced": n(pitching.get("battersFaced")),
        "pitches": n(pitching.get("numberOfPitches")),
        "hits": n(pitching.get("hits")),
        "runs": n(pitching.get("runs")),
        "earned_runs": n(pitching.get("earnedRuns")),
        "walks": n(pitching.get("baseOnBalls")),
        "games_started": n(pitching.get("gamesStarted")),
    }


def game_target(schedule_game: dict, box: dict) -> dict:
    game_pk = int(schedule_game["gamePk"])
    teams = schedule_game.get("teams") or {}
    away_s = teams.get("away") or {}
    home_s = teams.get("home") or {}
    away_team = (away_s.get("team") or {})
    home_team = (home_s.get("team") or {})
    away_score = n(away_s.get("score"))
    home_score = n(home_s.get("score"))
    if away_score is None or home_score is None:
        raise ValueError(f"game {game_pk}: final score missing")
    if away_score == home_score:
        raise ValueError(f"game {game_pk}: tied completed MLB game unsupported")

    box_teams = box.get("teams") or {}
    away_starter = starter_from_team(box_teams.get("away") or {})
    home_starter = starter_from_team(box_teams.get("home") or {})
    if not away_starter or not home_starter:
        raise ValueError(f"game {game_pk}: starter resolution failed")

    game_type = str(schedule_game.get("gameType") or "")
    return {
        "source": "MLB Stats API schedule + completed-game boxscore",
        "source_role": "OUTCOME_TARGET_ONLY",
        "game_pk": game_pk,
        "game_id": str(game_pk),
        "game_date": str(schedule_game.get("officialDate") or "")[:10],
        "game_datetime": schedule_game.get("gameDate"),
        "season": int(str(schedule_game.get("season") or str(schedule_game.get("officialDate") or "")[:4])),
        "game_type": game_type,
        "season_type": "REG" if game_type == "R" else "POST",
        "venue_id": (schedule_game.get("venue") or {}).get("id"),
        "venue_name": (schedule_game.get("venue") or {}).get("name"),
        "away": {
            "team_id": away_team.get("id"),
            "name": away_team.get("name"),
            "score": away_score,
            "starter": away_starter,
        },
        "home": {
            "team_id": home_team.get("id"),
            "name": home_team.get("name"),
            "score": home_score,
            "starter": home_starter,
        },
        "actual_home_win": 1 if home_score > away_score else 0,
        "winning_team_id": home_team.get("id") if home_score > away_score else away_team.get("id"),
        "outcome_is_postgame_only": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Acquire MLB historical result/K targets")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2015-2025")
    ap.add_argument("--scope", choices=["postseason", "regular", "all"], default="postseason")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    seasons = parse_seasons(args.seasons)
    if args.scope == "postseason":
        types = POST_TYPES
    elif args.scope == "regular":
        types = REG_TYPES
    else:
        types = REG_TYPES + POST_TYPES

    schedules = []
    for season in seasons:
        games = schedule_for_season(season, types)
        schedules.extend(g for g in games if final_game(g))
        print(f"SCHEDULE {season}: {len(games)} listed · {sum(final_game(g) for g in games)} final")

    uniq = {}
    for g in schedules:
        uniq[int(g["gamePk"])] = g
    games = [uniq[k] for k in sorted(uniq)]

    rows = []
    errors = []
    cache_hits = 0
    downloads = 0

    def work(g):
        box, cache, hit = boxscore_cached(root, int(g["gamePk"]))
        return game_target(g, box), str(cache.relative_to(root)), hit

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as ex:
        futs = {ex.submit(work, g): g for g in games}
        for i, fut in enumerate(as_completed(futs), 1):
            g = futs[fut]
            try:
                row, cache_rel, hit = fut.result()
                row["boxscore_cache_path"] = cache_rel
                rows.append(row)
                cache_hits += int(hit)
                downloads += int(not hit)
            except Exception as exc:
                errors.append({"game_pk": g.get("gamePk"), "error": str(exc)})
            if i % 50 == 0 or i == len(games):
                print(f"BOXSCORES {i}/{len(games)} · rows {len(rows)} · errors {len(errors)}")

    rows.sort(key=lambda r: (r["game_date"], r["game_pk"]))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/normalized/mlb/historical_outcomes_030" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    out = out_dir / "MLB_HISTORICAL_OUTCOMES.jsonl"
    with out.open("wb") as f:
        for row in rows:
            f.write(canonical_bytes(row))

    manifest = {
        "version": VERSION,
        "lineage": LINEAGE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "scope": args.scope,
        "seasons": seasons,
        "game_types": list(types),
        "schedule_final_games": len(games),
        "target_rows": len(rows),
        "error_rows": len(errors),
        "errors": errors,
        "boxscore_cache_hits": cache_hits,
        "boxscore_downloads": downloads,
        "output_path": str(out.relative_to(root)),
        "output_sha256": sha256_file(out),
        "source_role": "OUTCOME_TARGET_ONLY",
        "pregame_feature_eligible": False,
        "market_dependency": False,
        "oddsPapi_requests": 0,
        "production_model_mutation": False,
    }
    manifest_path = out_dir / "SOURCE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    pointer = root / "data/normalized/mlb/CURRENT_HISTORICAL_OUTCOMES_030"
    atomic_write(pointer, (str(out_dir.relative_to(root)) + "\n").encode("utf-8"))

    print()
    print(f"MLB HISTORICAL OUTCOMES {VERSION}")
    print(f"Scope: {args.scope} · seasons {seasons[0]}-{seasons[-1]}")
    print(f"Rows: {len(rows):,} · errors {len(errors)}")
    print(f"Boxscore cache hits: {cache_hits:,} · downloads {downloads:,}")
    print("Source role: OUTCOME TARGET ONLY · pregame features: NO")
    print("OddsPapi: 0 · production mutation: NO")
    print(f"Outcomes: {out}")
    print(f"Manifest: {manifest_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

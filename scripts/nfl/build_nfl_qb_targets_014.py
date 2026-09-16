#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import json
import os
import sys
import uuid

try:
    import pyarrow.parquet as pq
except Exception as exc:
    raise SystemExit(f"pyarrow required; run scripts/nfl/bootstrap_phase1_python.command: {exc}")


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def pct(n: int | float, d: int | float) -> float | None:
    return None if not d else 100.0 * float(n) / float(d)


def mean(vals) -> float | None:
    xs = [float(x) for x in vals if x is not None]
    return None if not xs else sum(xs) / len(xs)


def asset_index(manifest: dict) -> dict[tuple[str, int | None], dict]:
    return {(str(a.get("source") or ""), a.get("season")): dict(a) for a in manifest.get("assets", [])}


def main() -> int:
    ap = argparse.ArgumentParser(description="Build NFL QB State 0.1.4 observed-starter target/decomposition snapshot")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    provider_dir = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(model_dir))
    sys.path.insert(0, str(provider_dir))
    import qb_target_decomposition_014 as q
    import contract

    seasons = q.assert_development_only(parse_seasons(args.seasons))
    season_set = set(seasons)

    raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    phase_ptr = root / "data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"
    if not raw_ptr.exists() or not phase_ptr.exists():
        raise FileNotFoundError("current raw/Phase1 snapshot pointer missing")
    sid = raw_ptr.read_text(encoding="utf-8").strip()
    if phase_ptr.read_text(encoding="utf-8").strip() != sid:
        raise ValueError("Phase1/raw snapshot mismatch")
    manifest_path = root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = asset_index(manifest)
    phase1 = root / "data/normalized/nfl/phase1" / sid

    # Canonical regular-season team-game universe from schedule identity only.
    game_meta: dict[str, dict] = {}
    expected_team_games = 0
    with (phase1 / "game_identity.csv").open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            season = int(r.get("season") or 0)
            if season not in season_set or str(r.get("game_type") or "").upper() != "REG":
                continue
            gid = str(r["game_id"])
            home = str(r.get("home_team") or "").upper()
            away = str(r.get("away_team") or "").upper()
            game_meta[gid] = {"season": season, "week": int(r.get("week") or 0), "home_team": home, "away_team": away}
            expected_team_games += 2

    all_targets: list[dict] = []
    schema_by_season: dict[str, dict] = {}
    for season in seasons:
        asset = assets.get(("play_by_play", season))
        if not asset:
            raise ValueError(f"raw snapshot missing play_by_play {season}")
        path = root / asset["blobPath"]
        pf = pq.ParquetFile(path)
        names = set(pf.schema_arrow.names)
        missing = [c for c in q.REQUIRED_PBP_FIELDS if c not in names]
        if missing:
            raise ValueError(f"{path.name} missing QB target fields: {', '.join(missing)}")
        cols = list(q.REQUIRED_PBP_FIELDS) + [c for c in q.OPTIONAL_PBP_FIELDS if c in names]
        rows = pf.read(columns=cols).to_pylist()
        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in rows:
            gid = str(r.get("game_id") or "")
            if gid not in game_meta:
                continue
            team_raw = str(r.get("posteam") or "").strip().upper()
            if not team_raw:
                continue
            team = contract.normalize_team_abbr(team_raw)
            rr = dict(r)
            rr["posteam"] = team
            grouped[(gid, team)].append(rr)
        season_targets = []
        for (gid, team), grows in grouped.items():
            x = q.aggregate_observed_starter_team_game(grows)
            if x is not None:
                season_targets.append(x)
        season_targets.sort(key=lambda r: (r["week"], r["game_id"], r["team"]))
        all_targets.extend(season_targets)
        schema_by_season[str(season)] = {
            "selectedFields": cols,
            "optionalFieldsPresent": [c for c in q.OPTIONAL_PBP_FIELDS if c in names],
            "targetRows": len(season_targets),
        }
        print(f"PASS QB targets {season} · team-games {len(season_targets):,}")

    all_targets.sort(key=lambda r: (r["season"], r["week"], r["game_id"], r["team"]))

    n = len(all_targets)
    component_exact = sum(int(r["dropback_component_residual"]) == 0 for r in all_targets)
    max_component_abs = max((abs(int(r["dropback_component_residual"])) for r in all_targets), default=0)
    completions = sum(int(r["completions"]) for r in all_targets)
    decomp_completions = sum(int(r["decomposable_completions"]) for r in all_targets)
    decomp_residual = sum(float(r["completion_yards_decomp_residual"]) for r in all_targets)
    starter_primary = sum(int(r["start_equals_primary"]) for r in all_targets)
    low_share = sum((r["starter_dropback_share"] is not None and float(r["starter_dropback_share"]) < 0.80) for r in all_targets)

    by_season = {}
    for season in seasons:
        sr = [r for r in all_targets if int(r["season"]) == season]
        by_season[str(season)] = {
            "rows": len(sr),
            "startEqualsPrimaryPct": pct(sum(int(r["start_equals_primary"]) for r in sr), len(sr)),
            "meanStarterDropbacks": mean(r["starter_dropbacks"] for r in sr),
            "meanPassAttempts": mean(r["pass_attempts"] for r in sr),
            "meanPassingYards": mean(r["passing_yards"] for r in sr),
            "meanScrambles": mean(r["scrambles"] for r in sr),
            "meanSacks": mean(r["sacks"] for r in sr),
        }

    audit = {
        "version": q.VERSION,
        "lineage": q.LINEAGE,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceSnapshotId": sid,
        "developmentSeasons": list(seasons),
        "sealedHoldoutSeason": 2025,
        "holdoutOpened": False,
        "prospectiveSeason": 2026,
        "prospectiveRead": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "modelFitPerformed": False,
        "historicalTargetIdentityPolicy": "observed first attributed eligible-dropback QB; retrospective label only",
        "pregameIdentityPolicy": "QB State 0.1.3 STRICT resolver or later verified starter source; unresolved cases quarantine",
        "antiLeakagePolicy": "do not filter historical model-fitting rows based on whether the pregame resolver happened to match same-game PBP",
        "expectedRegularSeasonTeamGames": expected_team_games,
        "targetRows": n,
        "targetCoveragePct": pct(n, expected_team_games),
        "startEqualsPrimaryPct": pct(starter_primary, n),
        "starterDropbackShareBelow80Pct": pct(low_share, n),
        "meanStarterDropbackShare": mean(r["starter_dropback_share"] for r in all_targets),
        "dropbackDecomposition": {
            "identity": "starter_dropbacks = pass_attempts + sacks + scrambles",
            "exactRows": component_exact,
            "exactPct": pct(component_exact, n),
            "maxAbsoluteResidual": max_component_abs,
        },
        "passingYardDecomposition": {
            "identity": "on completions with both components: passing_yards = air_yards + YAC",
            "completions": completions,
            "decomposableCompletions": decomp_completions,
            "coveragePct": pct(decomp_completions, completions),
            "aggregateResidualYards": decomp_residual,
        },
        "targetDistributions": {
            "starterDropbacks": q.quantiles(r["starter_dropbacks"] for r in all_targets),
            "passAttempts": q.quantiles(r["pass_attempts"] for r in all_targets),
            "completions": q.quantiles(r["completions"] for r in all_targets),
            "passingYards": q.quantiles(r["passing_yards"] for r in all_targets),
            "sacks": q.quantiles(r["sacks"] for r in all_targets),
            "scrambles": q.quantiles(r["scrambles"] for r in all_targets),
            "designedQbRushAttempts": q.quantiles(r["designed_qb_rush_attempts"] for r in all_targets),
        },
        "bySeason": by_season,
        "schemaBySeason": schema_by_season,
    }

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/normalized/nfl/qb_targets_014" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    targets_path = out_dir / "NFL_QB_OBSERVED_START_TARGETS.jsonl"
    with targets_path.open("w", encoding="utf-8") as f:
        for row in all_targets:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    audit_path = out_dir / "NFL_QB_TARGET_DECOMPOSITION_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    ptr = root / "data/normalized/nfl/CURRENT_NFL_QB_TARGETS_014"
    ptr.parent.mkdir(parents=True, exist_ok=True)
    tmp = ptr.with_name("." + ptr.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
    os.replace(tmp, ptr)

    print("\nNFL QB STATE 0.1.4 — OBSERVED-STARTER TARGET / DECOMPOSITION AUDIT")
    print(f"Source snapshot: {sid}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print(f"Regular-season team-games: {expected_team_games:,}")
    print(f"Observed-starter target rows: {n:,} ({audit['targetCoveragePct']:.2f}%)")
    print(f"Observed starter remains primary QB: {audit['startEqualsPrimaryPct']:.2f}%")
    print(f"Starter dropback share <80%: {audit['starterDropbackShareBelow80Pct']:.2f}%")
    print("\nSTRUCTURAL IDENTITIES")
    dd = audit["dropbackDecomposition"]
    print(f"  dropbacks = attempts + sacks + scrambles: exact {dd['exactPct']:.2f}% · max abs residual {dd['maxAbsoluteResidual']}")
    yd = audit["passingYardDecomposition"]
    print(f"  completed air yards + YAC coverage: {yd['coveragePct']:.2f}% · aggregate residual {yd['aggregateResidualYards']:.1f} yd")
    print("\nTARGET DISTRIBUTION MEDIANS")
    td = audit["targetDistributions"]
    print(f"  dropbacks {td['starterDropbacks']['0.5']:.1f} · attempts {td['passAttempts']['0.5']:.1f} · completions {td['completions']['0.5']:.1f}")
    print(f"  passing yards {td['passingYards']['0.5']:.1f} · sacks {td['sacks']['0.5']:.1f} · scrambles {td['scrambles']['0.5']:.1f}")
    print("\nMODEL-FIT BOUNDARY")
    print("  historical QB target identity: observed first attributed QB (label only)")
    print("  prospective QB identity: pregame resolver / verified starter source")
    print("  resolver correctness is NOT used to select historical fit rows")
    print(f"Targets: {targets_path}")
    print(f"Audit: {audit_path}")
    print("PASS QB State 0.1.4 target foundation · no model fit · 2025 sealed · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

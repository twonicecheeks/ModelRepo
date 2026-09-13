#!/usr/bin/env python3
"""Build the OMEGA tackle-event research foundation from the existing NFL snapshot.

Key integrity rules:
* 2025 OMEGA tackle holdout is not opened.
* postseason is excluded from this first regular-season model universe.
* no sportsbook/market data is read.
* no OddsPapi requests are made.
* tackle settlement semantics are preserved, not guessed.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from typing import Any

OMEGA_SCHEMA = "OMEGA_TACKLE_FOUNDATION_0.1"
DEV_SEASONS = tuple(range(2016, 2025))
HOLDOUT_SEASON = 2025


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | tuple[str, ...] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for r in rows:
            for k in r:
                if k not in fields:
                    fields.append(k)
    fields = list(fields)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def parquet_rows(path: Path, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> tuple[list[dict[str, Any]], set[str]]:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    missing = [c for c in required if c not in names]
    if missing:
        raise ValueError(f"{path.name} missing required parquet column(s): {', '.join(missing)}")
    cols = list(required) + [c for c in optional if c in names and c not in required]
    return pf.read(columns=cols).to_pylist(), names


def latest_snap_manifest(root: Path, source_sid: str) -> Path | None:
    base = root / "data/raw/nfl/nflverse/phase2c_context/snapshots"
    if not base.exists():
        return None
    candidates = []
    for p in base.glob("*/SOURCE_MANIFEST.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("sourcePhase1SnapshotId") == source_sid:
                candidates.append((d.get("createdAt", ""), p))
        except Exception:
            pass
    return max(candidates)[1] if candidates else None


def load_player_meta(root: Path, asset: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    import pyarrow.parquet as pq
    path = root / asset["blobPath"]
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    required = {"gsis_id", "display_name", "position", "position_group"}
    missing = required - names
    if missing:
        raise ValueError(f"players parquet missing: {sorted(missing)}")
    cols = ["gsis_id", "display_name", "position", "position_group"]
    if "pfr_id" in names:
        cols.append("pfr_id")
    rows = pf.read(columns=cols).to_pylist()
    by_gsis: dict[str, dict[str, Any]] = {}
    pfr_to_gsis: dict[str, str] = {}
    for r in rows:
        gsis = str(r.get("gsis_id") or "").strip()
        if not gsis:
            continue
        pfr = str(r.get("pfr_id") or "").strip()
        by_gsis[gsis] = {
            "display_name": str(r.get("display_name") or "").strip(),
            "position": str(r.get("position") or "").strip(),
            "position_group": str(r.get("position_group") or "").strip(),
            "pfr_id": pfr,
        }
        if pfr:
            pfr_to_gsis[pfr] = gsis
    return by_gsis, pfr_to_gsis


def load_snap_meta(root: Path, snap_manifest: Path | None, pfr_to_gsis: dict[str, str]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    if snap_manifest is None:
        return {}, {"available": False, "reason": "Phase2C snap-count manifest not found"}
    d = json.loads(snap_manifest.read_text(encoding="utf-8"))
    assets = [x for x in d.get("assets", []) if x.get("source") == "snap_counts" and int(x.get("season") or 0) in DEV_SEASONS]
    out: dict[tuple[str, str], dict[str, Any]] = {}
    raw_rows = resolved = 0
    for a in assets:
        rows, names = parquet_rows(
            root / a["blobPath"],
            ("game_id", "pfr_player_id", "defense_snaps", "defense_pct"),
            ("special_teams_snaps", "special_teams_pct"),
        )
        for r in rows:
            raw_rows += 1
            pfr = str(r.get("pfr_player_id") or "").strip()
            gsis = pfr_to_gsis.get(pfr, "")
            if not gsis:
                continue
            resolved += 1
            out[(str(r.get("game_id") or "").strip(), gsis)] = {
                "defense_snaps": r.get("defense_snaps"),
                "defense_pct": r.get("defense_pct"),
                "special_teams_snaps": r.get("special_teams_snaps"),
                "special_teams_pct": r.get("special_teams_pct"),
            }
    return out, {
        "available": True,
        "manifest": str(snap_manifest.relative_to(root)),
        "assets": len(assets),
        "rawRows": raw_rows,
        "resolvedRows": resolved,
        "resolvedPct": round(100.0 * resolved / raw_rows, 3) if raw_rows else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    py = root / "packages/models/nfl/omega"
    sys.path.insert(0, str(py))
    import tackle_events as te

    phase1_ptr = root / "data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"
    if not phase1_ptr.exists():
        raise SystemExit("FAIL CURRENT_PHASE1_SNAPSHOT missing")
    sid = phase1_ptr.read_text(encoding="utf-8").strip()
    norm = root / "data/normalized/nfl/phase1" / sid
    raw_manifest_path = root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json"
    if not raw_manifest_path.exists():
        raise SystemExit(f"FAIL source manifest missing: {raw_manifest_path}")
    manifest = json.loads(raw_manifest_path.read_text(encoding="utf-8"))
    if HOLDOUT_SEASON not in [int(x) for x in manifest.get("analysisSeasons", [])]:
        raise SystemExit("FAIL expected 2025 source coverage in Phase1 snapshot")
    assets = {(x["source"], x.get("season")): x for x in manifest.get("assets", [])}

    games = [r for r in read_csv(norm / "game_identity.csv") if int(r["season"]) in DEV_SEASONS and r.get("game_type") == "REG"]
    game_meta = {r["game_id"]: r for r in games}
    allowed_game_ids = set(game_meta)
    if not allowed_game_ids:
        raise SystemExit("FAIL no regular-season development games")

    player_meta, pfr_to_gsis = load_player_meta(root, assets[("players", None)])
    snap_manifest = latest_snap_manifest(root, sid)
    snap_meta, snap_audit = load_snap_meta(root, snap_manifest, pfr_to_gsis)

    out = root / "data/normalized/nfl/omega_tackle" / sid
    if out.exists():
        raise SystemExit(f"Refusing overwrite immutable OMEGA tackle foundation: {out}")
    staging = out.parent / ("." + sid + ".staging")
    staging.mkdir(parents=True, exist_ok=False)

    event_fields = [
        "game_id", "play_id", "season", "week", "posteam", "defteam",
        "player_id", "player_name_source", "credit_team", "credit_team_role",
        "credit_role", "source_slot", "solo_tackle_credit", "tackle_with_assist_credit",
        "assist_credit", "combined_credit_unit", "play_family", "is_special_teams",
        "is_nullified_or_deleted", "is_original_defense_credit", "is_standard_def_scrimmage_credit",
    ]
    play_fields = [
        "game_id", "play_id", "season", "week", "posteam", "defteam", "play_type", "play_family",
        "down", "ydstogo", "yardline_100", "qtr", "game_seconds_remaining", "score_differential",
        "score_differential_post", "yards_gained", "air_yards", "yards_after_catch", "run_location",
        "run_gap", "pass_location", "pass_length", "shotgun", "no_huddle", "qb_scramble", "sack",
        "complete_pass", "interception", "fumble", "fumble_lost", "special_teams_play",
        "is_nullified_or_deleted", "all_credit_units", "original_defense_credit_units",
        "original_defense_solo", "original_defense_primary_with_assist", "original_defense_assists",
    ]

    all_player_games: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    role_counts = Counter()
    family_counts = Counter()
    season_counts: dict[str, dict[str, Any]] = {}
    schema_by_season: dict[str, Any] = {}
    identity_total = identity_resolved = 0
    snap_total = snap_resolved = 0
    nullified_credit_events = 0
    original_def_credit_events = 0
    special_credit_events = 0
    play_rows_total = 0

    try:
        with (staging / "omega_tackle_credit_events.csv").open("w", newline="", encoding="utf-8") as ef, \
             (staging / "omega_tackle_play_opportunities.csv").open("w", newline="", encoding="utf-8") as pf:
            ew = csv.DictWriter(ef, fieldnames=event_fields, extrasaction="ignore", lineterminator="\n")
            pw = csv.DictWriter(pf, fieldnames=play_fields, extrasaction="ignore", lineterminator="\n")
            ew.writeheader(); pw.writeheader()

            required = ("game_id", "play_id", "season", "week", "posteam", "defteam")
            optional = (
                "play_type", "no_play", "play_deleted", "special_teams_play", "qtr", "down", "ydstogo",
                "yardline_100", "game_seconds_remaining", "score_differential", "score_differential_post",
                "yards_gained", "air_yards", "yards_after_catch", "run_location", "run_gap", "pass_location",
                "pass_length", "shotgun", "no_huddle", "qb_scramble", "sack", "rush", "rush_attempt",
                "pass_attempt", "qb_dropback", "complete_pass", "interception", "fumble", "fumble_lost",
            ) + te.TACKLE_ID_COLUMNS + te.TACKLE_NAME_COLUMNS + te.TACKLE_TEAM_COLUMNS

            for season in DEV_SEASONS:
                asset = assets.get(("play_by_play", season))
                if not asset:
                    raise ValueError(f"source snapshot missing play_by_play {season}")
                rows, names = parquet_rows(root / asset["blobPath"], required, optional)
                schema_by_season[str(season)] = te.validate_tackle_schema(names)
                season_events: list[dict[str, Any]] = []
                season_plays = season_credit_events = 0
                for r in rows:
                    if str(r.get("game_id") or "") not in allowed_game_ids:
                        continue
                    credit_events = te.extract_credit_events(r)
                    for e in credit_events:
                        ew.writerow({k: "" if e.get(k) is None else e.get(k) for k in event_fields})
                    pr = te.build_play_opportunity_row(r, credit_events)
                    pw.writerow({k: "" if pr.get(k) is None else pr.get(k) for k in play_fields})
                    season_events.extend(credit_events)
                    season_plays += 1
                    season_credit_events += len(credit_events)
                play_rows_total += season_plays
                for e in season_events:
                    role_counts[e["credit_role"]] += 1
                    family_counts[e["play_family"]] += 1
                    nullified_credit_events += int(e["is_nullified_or_deleted"])
                    original_def_credit_events += int(e["is_original_defense_credit"])
                    special_credit_events += int(e["is_special_teams"])
                    identity_total += 1
                    if e["player_id"] in player_meta:
                        identity_resolved += 1
                pg = te.aggregate_player_games(season_events, player_meta=player_meta, game_meta=game_meta, snap_meta=snap_meta)
                for r in pg:
                    snap_total += 1
                    if r.get("defense_snaps") not in (None, ""):
                        snap_resolved += 1
                all_player_games.extend(pg)
                season_anom = te.duplicate_credit_anomalies(season_events)
                anomalies.extend(season_anom)
                season_counts[str(season)] = {
                    "regularSeasonPlayRows": season_plays,
                    "creditEvents": season_credit_events,
                    "playerGameRows": len(pg),
                    "duplicateCreditAnomalies": len(season_anom),
                }
                print(f"PASS OMEGA {season}: plays {season_plays} · credits {season_credit_events} · player-games {len(pg)}")

        write_csv(staging / "omega_tackle_player_games.csv", all_player_games)
        write_csv(staging / "omega_duplicate_credit_anomalies.csv", anomalies,
                  ["game_id", "play_id", "player_id", "credit_role", "count"])

        # Pre-registered hypotheses. These are research questions, not fitted conclusions.
        hypotheses = [
            {"id":"H001","name":"Situational snap composition","mechanism":"Tackle opportunity depends on types of snaps, not raw snap percentage alone","expected_direction":"State-conditioned exposure improves xT+A vs raw snap share","status":"PRE_REGISTERED"},
            {"id":"H002","name":"Tackle funnel rigidity","mechanism":"Some defenses allocate tackle credit to a stable set of players across opponents","expected_direction":"High rigidity lowers player-level forecast error","status":"PRE_REGISTERED"},
            {"id":"H003","name":"Replacement-role convexity","mechanism":"A backup inheriting a starter role changes alignment/responsibility as well as snap share","expected_direction":"Role promotion effect can exceed linear snap-share scaling","status":"PRE_REGISTERED"},
            {"id":"H004","name":"Assist competition","mechanism":"Teammate configuration changes solo vs assisted credit allocation","expected_direction":"Teammate absence can move solo and T+A markets differently","status":"PRE_REGISTERED"},
            {"id":"H005","name":"Venue / credit environment","mechanism":"Human scoring may create persistent venue-level solo/assist tendencies","expected_direction":"Any effect must persist out of sample after player/team mix adjustment","status":"PRE_REGISTERED"},
            {"id":"H006","name":"Early-week information asymmetry","mechanism":"Role/injury information reaches niche prop prices asynchronously","expected_direction":"Earlier captured prices show more CLV dispersion than close","status":"PRE_REGISTERED"},
            {"id":"H007","name":"xT+A residual persistence","mechanism":"Some apparent over/under-performance may represent repeatable involvement/credit skill","expected_direction":"Residual persistence survives shrinkage only for identifiable mechanisms","status":"PRE_REGISTERED"},
            {"id":"H008","name":"Offensive tackle-opportunity footprint","mechanism":"Rush location, short-middle completions, scrambles and screens funnel tackles by position","expected_direction":"Topology-conditioned opponent features outperform positional tackles allowed","status":"PRE_REGISTERED"},
            {"id":"H009","name":"Game-script elasticity","mechanism":"Score state changes both offensive play mix and defensive personnel","expected_direction":"Player tackle expectation is nonlinear in projected game script","status":"PRE_REGISTERED"},
            {"id":"H010","name":"Information-source disagreement","mechanism":"Derived pressure/coverage labels differ by vendor and can inject measurement error","expected_direction":"Transparent raw/event features should be preferred unless vendor signal proves incremental","status":"PRE_REGISTERED"},
        ]
        write_csv(staging / "OMEGA_HYPOTHESIS_REGISTRY.csv", hypotheses)

        unresolved_identity = identity_total - identity_resolved
        audit = {
            "schemaVersion": OMEGA_SCHEMA,
            "generatedAt": now(),
            "sourcePhase1SnapshotId": sid,
            "developmentSeasons": list(DEV_SEASONS),
            "developmentGameType": "REG",
            "postseasonPolicy": "EXCLUDED_SEPARATE_REGIME",
            "omegaHoldoutSeason": HOLDOUT_SEASON,
            "omegaHoldoutPbpRowsRead": 0,
            "omegaHoldoutTackleOutcomesRead": 0,
            "marketFieldsRead": 0,
            "oddsPapiRequests": 0,
            "modelFitPerformed": False,
            "settlementConventionAssumed": False,
            "playRows": play_rows_total,
            "creditEvents": int(sum(role_counts.values())),
            "creditRoleCounts": dict(role_counts),
            "playFamilyCreditCounts": dict(family_counts),
            "originalDefenseCreditEvents": original_def_credit_events,
            "specialTeamsCreditEvents": special_credit_events,
            "nullifiedOrDeletedCreditEvents": nullified_credit_events,
            "playerIdentity": {
                "events": identity_total,
                "resolved": identity_resolved,
                "unresolved": unresolved_identity,
                "resolvedPct": round(100.0 * identity_resolved / identity_total, 4) if identity_total else None,
            },
            "snapJoin": {
                **snap_audit,
                "playerGameRows": snap_total,
                "playerGameRowsWithDefenseSnaps": snap_resolved,
                "playerGameCoveragePct": round(100.0 * snap_resolved / snap_total, 4) if snap_total else None,
            },
            "duplicateCreditAnomalies": len(anomalies),
            "schemaBySeason": schema_by_season,
            "seasonCounts": season_counts,
            "integrity": {
                "holdoutUnopened": True,
                "marketIsolation": True,
                "postseasonSeparated": True,
                "rawCreditSemanticsPreserved": True,
            },
        }
        (staging / "OMEGA_TACKLE_FOUNDATION_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

        md = [
            "# OMEGA Tackle Model 0.1 — Event Foundation Audit", "",
            f"Generated: {audit['generatedAt']}", "",
            "**RESEARCH FOUNDATION ONLY. NO BETTING MODEL IS FIT IN THIS PHASE.**", "",
            "## Integrity", "",
            f"- Source Phase1 snapshot: `{sid}`",
            "- OMEGA development: **2016–2024 REG only**",
            "- OMEGA 2025 tackle holdout PBP rows read: **0**",
            "- OMEGA 2025 tackle outcomes read: **0**",
            "- Postseason: **EXCLUDED — separate future regime**",
            "- Market fields read: **0**",
            "- OddsPapi requests: **0**",
            "- Model fitting performed: **NO**",
            "- Sportsbook settlement convention assumed: **NO**", "",
            "## Event ledger", "",
            f"- Regular-season play rows: **{play_rows_total}**",
            f"- Tackle-credit events: **{sum(role_counts.values())}**",
            f"- SOLO credits: **{role_counts.get('SOLO',0)}**",
            f"- PRIMARY_WITH_ASSIST credits: **{role_counts.get('PRIMARY_WITH_ASSIST',0)}**",
            f"- ASSIST credits: **{role_counts.get('ASSIST',0)}**",
            f"- Original-defense credit events: **{original_def_credit_events}**",
            f"- Special-teams credit events: **{special_credit_events}**",
            f"- Nullified/deleted-play credit events surfaced: **{nullified_credit_events}**",
            f"- Same-player/same-role duplicate-credit anomalies surfaced: **{len(anomalies)}**", "",
            "## Identity / exposure", "",
            f"- Tackle-credit player identity resolution: **{audit['playerIdentity']['resolvedPct']}%** ({identity_resolved}/{identity_total})",
        ]
        if snap_audit.get("available"):
            md += [f"- Player-game defensive-snap join coverage: **{audit['snapJoin']['playerGameCoveragePct']}%** ({snap_resolved}/{snap_total})"]
        else:
            md += [f"- Defensive snap join: **NOT AVAILABLE** — {snap_audit.get('reason')}"]
        md += ["", "## Critical semantic rule", "",
               "OMEGA preserves three separate NFL/nflverse credit classes: `SOLO`, `PRIMARY_WITH_ASSIST`, and `ASSIST`. It does **not** assume that a sportsbook's 'tackles', 'solo tackles', or 'tackles + assists' market maps to any particular formula. That settlement mapping must be explicit per book before EV can be computed.", "",
               "## Research discipline", "",
               "The build writes `OMEGA_HYPOTHESIS_REGISTRY.csv`. Every new feature family must start as a football mechanism/hypothesis before it is tested. Blind ROI-mining is prohibited.", "",
               "## Next gate", "",
               "Review schema/identity/snap coverage and duplicate/nullified anomalies. Then build the first xTackle-Opportunity baseline on 2016–2023, use 2024 as chronological validation, and keep 2025 sealed for OMEGA until the tackle specification is frozen.", ""]
        (staging / "OMEGA_TACKLE_FOUNDATION_AUDIT.md").write_text("\n".join(md), encoding="utf-8")

        # Immutable output manifest.
        files = []
        for p in sorted(staging.iterdir()):
            if p.is_file():
                files.append({"filename": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size})
        (staging / "OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({
            "schemaVersion": OMEGA_SCHEMA,
            "sourcePhase1SnapshotId": sid,
            "createdAt": now(),
            "files": files,
        }, indent=2) + "\n", encoding="utf-8")

        os.replace(staging, out)
        (root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION").write_text(sid + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print("OMEGA TACKLE MODEL 0.1 — EVENT FOUNDATION")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS regular-season development universe: 2016-2024 · plays {play_rows_total}")
    print(f"PASS tackle-credit events: {sum(role_counts.values())}")
    print(f"PASS player identity resolution: {audit['playerIdentity']['resolvedPct']}%")
    if snap_audit.get("available"):
        print(f"PASS defensive snap join: {audit['snapJoin']['playerGameCoveragePct']}%")
    else:
        print("WARN defensive snap join unavailable; event foundation still valid")
    print("PASS OMEGA 2025 tackle holdout: NOT READ")
    print("PASS market isolation · OddsPapi requests 0 · model fit NO")
    print(f"REPORT: {out/'OMEGA_TACKLE_FOUNDATION_AUDIT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

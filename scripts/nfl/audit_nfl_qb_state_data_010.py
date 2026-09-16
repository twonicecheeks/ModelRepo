#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import sys
import uuid

try:
    import pyarrow.parquet as pq
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"pyarrow required; run scripts/nfl/bootstrap_phase1_python.command: {exc}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def _asset_index(manifest: dict) -> dict[tuple[str, int | None], dict]:
    out: dict[tuple[str, int | None], dict] = {}
    for asset in manifest.get("assets", []):
        key = (str(asset.get("source") or ""), asset.get("season"))
        if key in out:
            raise ValueError(f"duplicate asset {key}")
        out[key] = dict(asset)
    return out


def _is_no_play(row: dict) -> bool:
    if "no_play" in row and row.get("no_play") is not None:
        try:
            return float(row.get("no_play")) == 1.0
        except Exception:
            pass
    return str(row.get("play_type") or "").strip().lower() == "no_play"


def _is_kneel(row: dict) -> bool:
    if "qb_kneel" in row and row.get("qb_kneel") is not None:
        try:
            return float(row.get("qb_kneel")) == 1.0
        except Exception:
            pass
    return str(row.get("play_type") or "").strip().lower() == "qb_kneel"


def _bool1(value) -> bool:
    try:
        return float(value) == 1.0
    except Exception:
        return False


def _fmt_pct(value) -> str:
    return "NA" if value is None else f"{float(value):.2f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="QB State 0.1.0 immutable nflverse data/identity capability audit")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    provider_dir = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(model_dir))
    sys.path.insert(0, str(provider_dir))
    import qb_state_data_audit_010 as qa
    import contract
    import snapshot

    seasons = list(qa.assert_development_only(parse_seasons(args.seasons)))

    ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    if not ptr.exists():
        raise FileNotFoundError("CURRENT_RAW_SNAPSHOT missing")
    sid = ptr.read_text(encoding="utf-8").strip()
    manifest_path = root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json"
    manifest = snapshot.load_manifest(manifest_path, root=root)
    assets = _asset_index(manifest)

    print("NFL QB STATE 0.1.0 — DATA & IDENTITY CAPABILITY AUDIT")
    print(f"Source snapshot: {sid}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print()

    # Identity crosswalk. This reads only stable identity/position columns from the
    # snapshot-wide players table; no game outcome or holdout labels are consulted.
    players_asset = assets.get(("players", None))
    if not players_asset:
        raise ValueError("players asset missing")
    players_pf = pq.ParquetFile(root / players_asset["blobPath"])
    player_names = set(players_pf.schema_arrow.names)
    required_player_cols = [c for c in ("gsis_id", "position", "position_group") if c in player_names]
    if "gsis_id" not in required_player_cols:
        raise ValueError("players parquet missing gsis_id")
    player_rows = players_pf.read(columns=required_player_cols).to_pylist()
    player_ids: set[str] = set()
    qb_player_ids: set[str] = set()
    for row in player_rows:
        gid = qa.clean(row.get("gsis_id"))
        if not gid:
            continue
        player_ids.add(gid)
        pos = qa.clean(row.get("position")).upper()
        grp = qa.clean(row.get("position_group")).upper()
        if pos == "QB" or grp == "QB":
            qb_player_ids.add(gid)

    coverage: dict[str, dict[str, int | float | bool | None]] = {
        f: {"existsSeasons": 0, "nonNull": 0, "denominator": 0} for f in qa.PBP_FIELDS
    }
    per_season_pbp: list[dict] = []
    unique_passers: set[str] = set()
    resolved_passers: set[str] = set()
    attributed_dropbacks = 0
    resolved_dropbacks = 0
    total_rows = total_dropbacks = total_attempts = total_completions = 0
    total_rushes = total_qb_rushes = total_designed_qb_rushes = 0

    for season in seasons:
        asset = assets.get(("play_by_play", season))
        if not asset:
            raise ValueError(f"play_by_play {season} asset missing")
        path = root / asset["blobPath"]
        pf = pq.ParquetFile(path)
        names = set(pf.schema_arrow.names)
        selected = [f for f in qa.PBP_FIELDS if f in names]
        for f in selected:
            coverage[f]["existsSeasons"] = int(coverage[f]["existsSeasons"]) + 1
        # Fail closed on the minimum predicates needed for a useful QB audit.
        must = {"game_id", "season", "week", "posteam", "qb_dropback", "sack"}
        missing = sorted(must - names)
        if missing:
            raise ValueError(f"PBP {season} missing audit-critical fields: {','.join(missing)}")
        rows = pf.read(columns=selected).to_pylist()
        row_n = len(rows)
        db_n = att_n = comp_n = rush_n = qb_rush_n = designed_qb_rush_n = 0
        for row in rows:
            no_play = _is_no_play(row)
            kneel = _is_kneel(row)
            dropback = _bool1(row.get("qb_dropback")) and not no_play and not kneel
            attempt = _bool1(row.get("pass_attempt")) and not no_play
            complete = _bool1(row.get("complete_pass")) and attempt
            rush = _bool1(row.get("rush_attempt")) and not no_play and not kneel
            passer = qa.clean(row.get("passer_player_id"))
            rusher = qa.clean(row.get("rusher_player_id"))
            qb_rush = rush and bool(rusher) and rusher in qb_player_ids
            designed_qb_rush = qb_rush and not _bool1(row.get("qb_scramble"))

            if dropback:
                db_n += 1
                if passer:
                    attributed_dropbacks += 1
                    unique_passers.add(passer)
                    if passer in player_ids:
                        resolved_dropbacks += 1
                        resolved_passers.add(passer)
            if attempt:
                att_n += 1
            if complete:
                comp_n += 1
            if rush:
                rush_n += 1
            if qb_rush:
                qb_rush_n += 1
            if designed_qb_rush:
                designed_qb_rush_n += 1

            denom_by_field = {
                "passer_player_id": dropback,
                "passer_player_name": dropback,
                "qb_epa": dropback,
                "sack": dropback,
                "qb_scramble": dropback,
                "pass_attempt": dropback,
                "complete_pass": attempt,
                "incomplete_pass": attempt,
                "passing_yards": attempt,
                "air_yards": attempt,
                "cpoe": attempt,
                "cp": attempt,
                "receiver_player_id": attempt,
                "receiver_player_name": attempt,
                "yards_after_catch": complete,
                "xyac_mean_yardage": complete,
                "xyac_epa": complete,
                "rusher_player_id": rush,
                "rusher_player_name": rush,
            }
            for field, applies in denom_by_field.items():
                if field not in names or not applies:
                    continue
                coverage[field]["denominator"] = int(coverage[field]["denominator"]) + 1
                if qa.present(row.get(field)):
                    coverage[field]["nonNull"] = int(coverage[field]["nonNull"]) + 1

        total_rows += row_n
        total_dropbacks += db_n
        total_attempts += att_n
        total_completions += comp_n
        total_rushes += rush_n
        total_qb_rushes += qb_rush_n
        total_designed_qb_rushes += designed_qb_rush_n
        per_season_pbp.append({
            "season": season,
            "rows": row_n,
            "eligibleDropbacks": db_n,
            "passAttempts": att_n,
            "completions": comp_n,
            "rushAttempts": rush_n,
            "qbRushAttemptsIdentityResolved": qb_rush_n,
            "designedQbRushAttemptsIdentityResolved": designed_qb_rush_n,
            "schemaFields": sorted(names & set(qa.PBP_FIELDS)),
        })
        print(
            f"PASS PBP {season} · rows {row_n:,} · dropbacks {db_n:,} · "
            f"attempts {att_n:,} · completions {comp_n:,}"
        )

    field_report: dict[str, dict] = {}
    for field, c in coverage.items():
        d = int(c["denominator"])
        n = int(c["nonNull"])
        field_report[field] = {
            "existsSeasons": int(c["existsSeasons"]),
            "existsAllDevelopmentSeasons": int(c["existsSeasons"]) == len(seasons),
            "nonNull": n,
            "denominator": d,
            "coveragePct": qa.pct(n, d),
        }
    core_found = {f: field_report[f]["existsAllDevelopmentSeasons"] for f in qa.QB_CORE_FIELDS}
    pbp_status = qa.coverage_status(core_found)
    id_status = qa.identity_status(
        unique_passers=len(unique_passers),
        resolved_passers=len(resolved_passers),
        attributed_dropbacks=attributed_dropbacks,
        resolved_dropbacks=resolved_dropbacks,
    )

    # Weekly roster audit: inspect actual raw schema and profile any fields that
    # might encode starter/depth semantics. No assumption is made from names alone.
    roster_candidates: set[str] = set()
    roster_order_candidates: set[str] = set()
    roster_profiles: dict[str, dict[str, object]] = defaultdict(lambda: {"nonNull": 0, "qbRows": 0, "values": set()})
    roster_seasons: list[dict] = []
    total_qb_roster_rows = total_active_qb_roster_rows = 0

    for season in seasons:
        asset = assets.get(("weekly_rosters", season))
        if not asset:
            raise ValueError(f"weekly_rosters {season} asset missing")
        path = root / asset["blobPath"]
        pf = pq.ParquetFile(path)
        names = set(pf.schema_arrow.names)
        candidates = set(qa.candidate_starter_fields(names))
        order_candidates = set(qa.authoritative_order_candidates(names))
        roster_candidates |= candidates
        roster_order_candidates |= order_candidates
        selected = sorted(({"position", "depth_chart_position", "status", "gsis_id", "week", "team"} | candidates) & names)
        rows = pf.read(columns=selected).to_pylist()
        qb_rows = []
        for row in rows:
            pos = qa.clean(row.get("position")).upper()
            dcp = qa.clean(row.get("depth_chart_position")).upper()
            if pos == "QB" or dcp == "QB":
                qb_rows.append(row)
        active = [r for r in qb_rows if qa.clean(r.get("status")).upper() == "ACT"]
        total_qb_roster_rows += len(qb_rows)
        total_active_qb_roster_rows += len(active)
        for field in candidates:
            prof = roster_profiles[field]
            prof["qbRows"] = int(prof["qbRows"]) + len(qb_rows)
            for row in qb_rows:
                value = row.get(field)
                if qa.present(value):
                    prof["nonNull"] = int(prof["nonNull"]) + 1
                    vals = prof["values"]
                    assert isinstance(vals, set)
                    if len(vals) < 25:
                        vals.add(str(value))
        roster_seasons.append({
            "season": season,
            "schemaCandidateFields": sorted(candidates),
            "authoritativeOrderCandidates": sorted(order_candidates),
            "qbRows": len(qb_rows),
            "activeQbRows": len(active),
        })
        print(
            f"PASS ROSTER {season} · QB rows {len(qb_rows):,} · active {len(active):,} · "
            f"order fields {','.join(sorted(order_candidates)) or 'NONE'}"
        )

    roster_profile_json: dict[str, dict] = {}
    for field, prof in sorted(roster_profiles.items()):
        qb_rows = int(prof["qbRows"])
        non_null = int(prof["nonNull"])
        vals = prof["values"]
        assert isinstance(vals, set)
        roster_profile_json[field] = {
            "qbRows": qb_rows,
            "nonNull": non_null,
            "coveragePct": qa.pct(non_null, qb_rows),
            "sampleValues": sorted(vals)[:25],
        }

    roster_status = qa.roster_starter_status(sorted(roster_order_candidates))
    depth_asset_present = any(k[0] == "depth_charts" for k in assets)
    depth_spec = contract.source_specs().get("depth_charts")
    depth_status = qa.depth_chart_source_status(
        asset_present=depth_asset_present,
        contract_status=getattr(depth_spec, "status", None),
    )

    if pbp_status == "CORE_QB_PBP_SCHEMA_AVAILABLE" and id_status == "GSIS_IDENTITY_STRONG":
        if roster_status == "NO_AUTHORITATIVE_STARTER_ORDER_FIELD_OBSERVED" and not depth_asset_present:
            readiness = "PBP_READY_STARTER_SOURCE_GATED"
            next_action = "BUILD_DEPTH_CHART_ADAPTER"
        else:
            readiness = "PBP_READY_STARTER_SEMANTICS_REQUIRE_VALIDATION"
            next_action = "VALIDATE_STARTER_SOURCE_SEMANTICS"
    else:
        readiness = "QB_FOUNDATION_DATA_REVIEW_REQUIRED"
        next_action = "REPAIR_OR_QUARANTINE_QB_DATA_GAPS"

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/qb_state_010" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "version": qa.VERSION,
        "lineage": qa.LINEAGE,
        "createdAt": utc_now(),
        "runId": run_id,
        "sourceSnapshotId": sid,
        "developmentSeasons": seasons,
        "sealedHoldoutSeason": 2025,
        "prospectiveSeason": 2026,
        "holdoutOpened": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "trainingOrRefitPerformed": False,
        "pbp": {
            "status": pbp_status,
            "rows": total_rows,
            "eligibleDropbacks": total_dropbacks,
            "passAttempts": total_attempts,
            "completions": total_completions,
            "rushAttempts": total_rushes,
            "qbRushAttemptsIdentityResolved": total_qb_rushes,
            "designedQbRushAttemptsIdentityResolved": total_designed_qb_rushes,
            "fieldCoverage": field_report,
            "bySeason": per_season_pbp,
        },
        "identity": {
            "status": id_status,
            "uniqueAttributedPasserIds": len(unique_passers),
            "uniquePasserIdsResolvedInPlayers": len(resolved_passers),
            "uniqueResolutionPct": qa.pct(len(resolved_passers), len(unique_passers)),
            "attributedDropbacks": attributed_dropbacks,
            "resolvedAttributedDropbacks": resolved_dropbacks,
            "dropbackResolutionPct": qa.pct(resolved_dropbacks, attributed_dropbacks),
            "playersGsisIds": len(player_ids),
            "playersQbGsisIds": len(qb_player_ids),
            "joinPolicy": "GSIS only; no display-name fallback",
        },
        "weeklyRosters": {
            "status": roster_status,
            "qbRows": total_qb_roster_rows,
            "activeQbRows": total_active_qb_roster_rows,
            "schemaCandidateFields": sorted(roster_candidates),
            "authoritativeOrderCandidates": sorted(roster_order_candidates),
            "fieldProfiles": roster_profile_json,
            "bySeason": roster_seasons,
            "guard": "depth_chart_position=QB is position identity, not QB1/QB2 authority",
        },
        "depthCharts": {
            "status": depth_status,
            "assetPresentInCurrentRawSnapshot": depth_asset_present,
            "contractStatus": getattr(depth_spec, "status", None),
            "minimumSeason": getattr(depth_spec, "minimum_season", None),
        },
        "existingArchitectureGuard": {
            "currentGamePbpStarterInferenceAllowed": False,
            "historicalObservedPrimaryMayOnlyBeUsedAfterLagging": True,
            "rosterSingletonMayRemainProxyOnly": True,
        },
        "readiness": readiness,
        "nextAction": next_action,
    }
    json_path = out_dir / "NFL_QB_STATE_DATA_AUDIT.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    core_lines = []
    for field in qa.QB_CORE_FIELDS:
        r = field_report[field]
        core_lines.append(
            f"  {field}: schema {r['existsSeasons']}/{len(seasons)} seasons · observed coverage {_fmt_pct(r['coveragePct'])}"
        )
    candidate_lines = []
    for field in sorted(roster_candidates):
        p = roster_profile_json[field]
        candidate_lines.append(
            f"  {field}: {_fmt_pct(p['coveragePct'])} of QB roster rows · sample {','.join(p['sampleValues'][:8]) or 'NONE'}"
        )
    if not candidate_lines:
        candidate_lines = ["  NONE"]

    text = "\n".join([
        "NFL QB STATE 0.1.0 — DATA & IDENTITY CAPABILITY AUDIT",
        "",
        f"Source snapshot: {sid}",
        f"Development seasons: {seasons[0]}-{seasons[-1]}",
        "2025 holdout: SEALED / NOT READ",
        "2026 prospective: NOT READ",
        "Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO",
        "",
        "PBP FOUNDATION",
        f"  status: {pbp_status}",
        f"  rows: {total_rows:,}",
        f"  eligible dropbacks: {total_dropbacks:,}",
        f"  pass attempts: {total_attempts:,}",
        f"  completions: {total_completions:,}",
        f"  identity-resolved QB rush attempts: {total_qb_rushes:,}",
        f"  identity-resolved designed QB rush attempts: {total_designed_qb_rushes:,}",
        *core_lines,
        "",
        "GSIS IDENTITY",
        f"  status: {id_status}",
        f"  unique attributed passers resolved: {len(resolved_passers)}/{len(unique_passers)} ({_fmt_pct(qa.pct(len(resolved_passers), len(unique_passers)))})",
        f"  attributed dropbacks resolved: {resolved_dropbacks:,}/{attributed_dropbacks:,} ({_fmt_pct(qa.pct(resolved_dropbacks, attributed_dropbacks))})",
        "  join policy: GSIS only · no display-name fallback",
        "",
        "WEEKLY ROSTER STARTER/DEPTH CAPABILITY",
        f"  status: {roster_status}",
        f"  QB rows: {total_qb_roster_rows:,} · active QB rows: {total_active_qb_roster_rows:,}",
        f"  authoritative order candidates: {','.join(sorted(roster_order_candidates)) or 'NONE'}",
        "  candidate schema fields:",
        *candidate_lines,
        "  guard: depth_chart_position=QB does not by itself mean QB1",
        "",
        "DEPTH CHART SOURCE",
        f"  status: {depth_status}",
        f"  asset present in current raw snapshot: {'YES' if depth_asset_present else 'NO'}",
        f"  contract status: {getattr(depth_spec, 'status', None)}",
        "",
        "ARCHITECTURE READINESS",
        f"  {readiness}",
        f"  next action: {next_action}",
        "",
        "Interpretation guard:",
        "  No current-game PBP is used to claim a pregame starter.",
        "  This audit fits no coefficients and opens no holdout labels.",
        "  Starter/depth semantics must be sourced explicitly before the QB model is fitted.",
        "",
        f"JSON: {json_path}",
    ]) + "\n"
    txt_path = out_dir / "NFL_QB_STATE_DATA_AUDIT.txt"
    txt_path.write_text(text, encoding="utf-8")

    current = root / "data/models/nfl/CURRENT_QB_STATE_DATA_AUDIT_010"
    current.parent.mkdir(parents=True, exist_ok=True)
    tmp = current.with_name("." + current.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
    os.replace(tmp, current)

    print()
    print(text)
    print("PASS QB State 0.1.0 data/identity audit · 2025 sealed · no model fit · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import sys
import uuid


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def load_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description="NFL QB State 0.1.9 official weekly target authority audit")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    provider_dir = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(model_dir))
    sys.path.insert(0, str(provider_dir))
    import qb_official_target_authority_019 as q19
    import qb_official_stats_adapter_019 as p19

    seasons = q19.assert_development_only(parse_seasons(args.seasons))
    season_set = set(seasons)

    raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    target_ptr = root / "data/normalized/nfl/CURRENT_NFL_QB_TARGETS_015"
    prior_ptr = root / "data/models/nfl/CURRENT_QB_STATE_018"
    if not raw_ptr.exists() or not target_ptr.exists() or not prior_ptr.exists():
        raise FileNotFoundError("required raw/QB-target-0.1.5/QB-State-0.1.8 pointer missing")

    pbp_snapshot_id = raw_ptr.read_text(encoding="utf-8").strip()
    target_dir = root / target_ptr.read_text(encoding="utf-8").strip()
    prior_dir = root / prior_ptr.read_text(encoding="utf-8").strip()
    target_audit = json.loads((target_dir / "NFL_QB_TARGET_SEMANTICS_AUDIT.json").read_text(encoding="utf-8"))
    prior_audit = json.loads((prior_dir / "NFL_QB_SEMANTIC_RECONCILIATION_AUDIT.json").read_text(encoding="utf-8"))

    if target_audit.get("sourceSnapshotId") != pbp_snapshot_id:
        raise ValueError("QB target 0.1.5/raw snapshot mismatch")
    if target_audit.get("holdoutOpened") is not False:
        raise ValueError("QB target 0.1.5 holdout boundary drift")
    if prior_audit.get("sourceSnapshotId") != pbp_snapshot_id:
        raise ValueError("QB State 0.1.8/raw snapshot mismatch")
    if prior_audit.get("holdoutOpened") is not False:
        raise ValueError("QB State 0.1.8 holdout boundary drift")
    if prior_audit.get("modelFitAuthorizedForNextVersion") is not False:
        raise ValueError("0.1.9 expected unresolved 0.1.8 authority blocker")
    if prior_audit.get("disposition") != "OFFICIAL_STAT_RECONCILIATION_REQUIRES_REVIEW":
        raise ValueError("0.1.9 expected 0.1.8 OFFICIAL_STAT_RECONCILIATION_REQUIRES_REVIEW")

    targets = [
        r for r in load_jsonl(target_dir / "NFL_QB_OBSERVED_START_TARGETS.jsonl")
        if int(r.get("season") or 0) in season_set
    ]
    targets.sort(key=lambda r: (int(r.get("season") or 0), int(r.get("week") or 0), str(r.get("game_id") or ""), str(r.get("team") or "")))
    if not targets:
        raise ValueError("no 0.1.5 QB target rows in requested seasons")
    target_keys = [q19.target_key(r) for r in targets]
    if any(not gid or not pid for gid, pid in target_keys):
        raise ValueError("0.1.5 target row missing game_id or observed-start GSIS ID")
    if len(set(target_keys)) != len(target_keys):
        raise ValueError("duplicate 0.1.5 target game/player key")

    target_player_ids = {pid for _, pid in target_keys}
    official_dir = p19.acquire_and_normalize(root, seasons, target_player_ids)
    official_source_audit = json.loads((official_dir / "NFL_QB_OFFICIAL_WEEKLY_STATS_AUDIT.json").read_text(encoding="utf-8"))
    official_snapshot_id = str(official_source_audit["snapshotId"])
    official_rows = load_jsonl(official_dir / "NFL_QB_OFFICIAL_WEEKLY_STATS.jsonl")

    official_buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in official_rows:
        if int(row.get("season") or 0) not in season_set:
            continue
        official_buckets[q19.official_key(row)].append(row)
    duplicate_keys = {k: v for k, v in official_buckets.items() if len(v) > 1}

    canonical_rows: list[dict] = []
    mismatch_rows: list[dict] = []
    missing_keys: list[tuple[str, str]] = []
    missing_required_cells = 0
    missing_required_rows = 0
    team_mismatches = 0
    cmp_inputs: dict[str, list[dict]] = {name: [] for name, _, _ in q19.COMPARISONS}

    for target in targets:
        key = q19.target_key(target)
        bucket = official_buckets.get(key, [])
        if len(bucket) != 1:
            missing_keys.append(key)
            continue
        official = bucket[0]
        row_missing = False
        for field in q19.REQUIRED_OFFICIAL_FIELDS:
            if q19.num(official.get(field)) is None:
                missing_required_cells += 1
                row_missing = True
        if row_missing:
            missing_required_rows += 1
        if q19.clean(target.get("team")).upper() != q19.clean(official.get("team")).upper():
            team_mismatches += 1

        canonical = q19.attach_official_target(target, official)
        canonical["official_stats_snapshot_id"] = official_snapshot_id
        canonical_rows.append(canonical)

        for name, pbp_field, official_field in q19.COMPARISONS:
            cmp_inputs[name].append({"pbp": target.get(pbp_field), "official": official.get(official_field)})
            p = q19.num(target.get(pbp_field))
            o = q19.num(official.get(official_field))
            if p is not None and o is not None and abs(p - o) >= 1e-9:
                mismatch_rows.append({
                    "comparison": name,
                    "season": int(target.get("season") or 0),
                    "week": int(target.get("week") or 0),
                    "game_id": target.get("game_id"),
                    "team": target.get("team"),
                    "qb_gsis_id": target.get("observed_start_qb_gsis_id"),
                    "pbp_value": p,
                    "official_value": o,
                    "delta": p - o,
                })

    comparisons = {
        name: q19.comparison_summary(rows, "pbp", "official")
        for name, rows in cmp_inputs.items()
    }

    authorized, disposition = q19.authorization(
        target_rows=len(targets),
        joined_rows=len(canonical_rows),
        duplicate_official_keys=len(duplicate_keys),
        missing_required_values=missing_required_cells,
        team_mismatches=team_mismatches,
        comparisons=comparisons,
    )

    by_season = {}
    for season in seasons:
        season_targets = [r for r in targets if int(r.get("season") or 0) == season]
        season_canonical = [r for r in canonical_rows if int(r.get("season") or 0) == season]
        season_cmp = {}
        for name, pbp_field, _ in q19.COMPARISONS:
            pairs = [
                {"pbp": r.get(pbp_field), "official": r.get(f"official_{'sacks_suffered' if name == 'sacks' else name}")}
                for r in season_canonical
            ]
            season_cmp[name] = q19.comparison_summary(pairs, "pbp", "official")
        by_season[str(season)] = {
            "targetRows": len(season_targets),
            "joinedRows": len(season_canonical),
            "comparisons": season_cmp,
        }

    foles = next(
        (
            r for r in canonical_rows
            if r.get("game_id") == "2022_16_LAC_IND" and str(r.get("team") or "").upper() == "IND"
        ),
        None,
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    model_out = root / "data/models/nfl/qb_state_019" / run_id
    target_out = root / "data/normalized/nfl/qb_official_targets_019" / run_id
    model_out.mkdir(parents=True, exist_ok=False)
    target_out.mkdir(parents=True, exist_ok=False)

    canonical_path = target_out / "NFL_QB_OFFICIAL_TARGETS.jsonl"
    with canonical_path.open("w", encoding="utf-8") as f:
        for row in canonical_rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    mismatch_path = model_out / "NFL_QB_OFFICIAL_TARGET_MISMATCHES.jsonl"
    with mismatch_path.open("w", encoding="utf-8") as f:
        for row in sorted(mismatch_rows, key=lambda r: (r["season"], r["week"], str(r["game_id"]), str(r["team"]), r["comparison"])):
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    report = {
        "version": q19.VERSION,
        "lineage": q19.LINEAGE,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourcePbpSnapshotId": pbp_snapshot_id,
        "sourceTarget015Directory": str(target_dir.relative_to(root)),
        "sourceQbState018Directory": str(prior_dir.relative_to(root)),
        "officialStatsSnapshotId": official_snapshot_id,
        "officialStatsDirectory": str(official_dir.relative_to(root)),
        "developmentSeasons": list(seasons),
        "sealedHoldoutSeason": 2025,
        "holdoutOpened": False,
        "prospectiveSeason": 2026,
        "prospectiveRead": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "modelFitPerformed": False,
        "targetAuthorityPolicy": "nflverse weekly player stats are authoritative for QB settlement/target totals; PBP remains mechanism/feature source and is never hand-corrected to force agreement",
        "joinPolicy": "exact nflverse game_id + GSIS player_id only; no display-name fallback; no fuzzy matching",
        "targetRows": len(targets),
        "joinedRows": len(canonical_rows),
        "joinCoveragePct": 100.0 * len(canonical_rows) / len(targets),
        "missingOfficialKeys": len(missing_keys),
        "duplicateOfficialKeys": len(duplicate_keys),
        "missingRequiredOfficialRows": missing_required_rows,
        "missingRequiredOfficialCells": missing_required_cells,
        "teamIdentityMismatches": team_mismatches,
        "sanityExactMatchFloorPct": q19.SANITY_EXACT_MATCH_FLOOR_PCT,
        "sanityFloorPurpose": "catastrophic schema/join guard only; not a model-selection threshold",
        "comparisons": comparisons,
        "bySeason": by_season,
        "folesWeek16Reconciliation": None if foles is None else {
            "game_id": foles.get("game_id"),
            "team": foles.get("team"),
            "qb_gsis_id": foles.get("observed_start_qb_gsis_id"),
            "pbp_attempts": foles.get("settlement_pass_attempts"),
            "official_attempts": foles.get("official_attempts"),
            "pbp_completions": foles.get("settlement_completions"),
            "official_completions": foles.get("official_completions"),
            "pbp_passing_yards": foles.get("passing_yards"),
            "official_passing_yards": foles.get("official_passing_yards"),
            "pbp_sacks": foles.get("structural_sacks"),
            "official_sacks_suffered": foles.get("official_sacks_suffered"),
        },
        "disposition": disposition,
        "modelFitAuthorizedForNextVersion": authorized,
        "authorizationScope": "development-only chronological QB challenger on 2016-2024; 2025 remains sealed; rare-event component quarantines from 0.1.7 remain mandatory",
    }
    audit_path = model_out / "NFL_QB_OFFICIAL_TARGET_AUTHORITY_AUDIT.json"
    audit_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    target_audit_path = target_out / "NFL_QB_OFFICIAL_TARGET_AUTHORITY_AUDIT.json"
    target_audit_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    atomic_pointer(root / "data/models/nfl/CURRENT_QB_STATE_019", str(model_out.relative_to(root)))
    atomic_pointer(root / "data/normalized/nfl/CURRENT_NFL_QB_OFFICIAL_TARGETS_019", str(target_out.relative_to(root)))

    print("\nNFL QB STATE 0.1.9 — OFFICIAL WEEKLY TARGET AUTHORITY AUDIT")
    print(f"PBP source snapshot: {pbp_snapshot_id}")
    print(f"Official weekly snapshot: {official_snapshot_id}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print(f"\nTARGET AUTHORITY JOIN")
    print(f"  target rows: {len(targets):,}")
    print(f"  exact game_id + GSIS joins: {len(canonical_rows):,}/{len(targets):,} ({report['joinCoveragePct']:.2f}%)")
    print(f"  missing keys: {len(missing_keys)} · duplicate official keys: {len(duplicate_keys)}")
    print(f"  required-value missing rows: {missing_required_rows} · cells: {missing_required_cells}")
    print(f"  team identity mismatches: {team_mismatches}")
    print("\nPBP vs OFFICIAL WEEKLY TOTALS")
    for name in ("attempts", "completions", "passing_yards", "sacks"):
        s = comparisons[name]
        print(
            f"  {name}: exact {s['exact']:,}/{s['n']:,} ({s['exactPct']:.4f}%) · "
            f"nonzero {s['nonzero']:,} · mean abs delta {s['meanAbsoluteDelta']:.4f} · max abs {s['maxAbsoluteDelta']:.1f}"
        )
    print("\nFOLES WEEK 16 RECONCILIATION")
    if foles is None:
        print("  target row not joined")
    else:
        print(
            f"  {foles['game_id']} · {foles['team']} · {foles['observed_start_qb_gsis_id']} · "
            f"PBP {foles['settlement_completions']}/{foles['settlement_pass_attempts']} {foles['passing_yards']:.0f} yd · "
            f"OFFICIAL {foles['official_completions']:.0f}/{foles['official_attempts']:.0f} {foles['official_passing_yards']:.0f} yd · "
            f"sacks PBP {foles['structural_sacks']} / official {foles['official_sacks_suffered']:.0f}"
        )
    print(f"\nDisposition: {disposition}")
    print(f"MODEL-FIT AUTHORIZATION FOR NEXT VERSION: {'YES' if authorized else 'NO'}")
    print("  official weekly totals are target authority; PBP discrepancies remain diagnostics, not hand edits")
    print(f"Canonical targets: {canonical_path}")
    print(f"Mismatch rows: {mismatch_path}")
    print(f"Audit: {audit_path}")
    print("PASS QB State 0.1.9 official target authority audit · no model fit performed · 2025 sealed · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

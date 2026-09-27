#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import sys
import uuid
import week3_scope_0380 as scope

try:
    import pyarrow.parquet as pq
except Exception as exc:
    raise SystemExit(f"pyarrow required; run scripts/nfl/bootstrap_phase2c_python.command: {exc}")


def load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_bytes(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def schedule_prior_keys(path: Path, target_week: int, contract) -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"game_id", "season", "game_type", "week", "away_team", "home_team"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError("schedule completeness source missing fields: " + ", ".join(missing))
        for raw in reader:
            if int(float(raw.get("season") or 0)) != 2026:
                continue
            if str(raw.get("game_type") or "").strip().upper() != "REG":
                continue
            week = int(float(raw.get("week") or 0))
            if week >= int(target_week):
                continue
            gid = str(raw.get("game_id") or "").strip()
            parsed = contract.parse_game_id(gid)
            if parsed["season"] != 2026 or parsed["week"] != week:
                raise ValueError(f"schedule game identity mismatch: {gid}")
            away = contract.normalize_team_abbr(str(raw.get("away_team") or "").strip().upper())
            home = contract.normalize_team_abbr(str(raw.get("home_team") or "").strip().upper())
            expected.add((gid, away)); expected.add((gid, home))
    return expected


def main() -> int:
    ap = argparse.ArgumentParser(description="Score frozen NFL QB passing yards as-of a 2026 target week")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--code-root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--kickoff-utc", required=True)
    ap.add_argument("--game-id", required=True, help="nflverse game_id, e.g. 2026_03_BUF_MIA")
    ap.add_argument("--team", required=True, help="target QB team abbreviation")
    ap.add_argument("--qb-gsis-id", required=True, help="verified target QB GSIS ID")
    ap.add_argument("--qb-name", default="", help="display label only; never an identity key")
    ap.add_argument("--source-manifest", default="", help="optional pre-acquired immutable 0.2.4 prospective source manifest; avoids redundant downloads in batch mode")
    ap.add_argument(
        "--identity-source", required=True,
        choices=["DIRECT_SPORTSBOOK_MARKET", "OFFICIAL_STARTER_ANNOUNCEMENT", "USER_VERIFIED_EXTERNAL"],
        help="external source that verified this target QB identity",
    )
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    code_root = Path(args.code_root).expanduser().resolve()
    selected_game = {"game_id":args.game_id, "kickoff_utc":args.kickoff_utc}
    scope.before_kickoff([selected_game])
    model_dir = code_root / "packages/models/nfl/game"
    provider_dir = code_root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(model_dir)); sys.path.insert(0, str(provider_dir))
    import contract
    import qb_passing_yards_bakeoff_020 as q20
    import qb_passing_yards_freeze_021 as q21
    import qb_passing_yards_asof_024 as q24
    import qb_target_semantics_015 as q15
    import qb_official_target_authority_019 as q19
    import qb_official_stats_adapter_019 as official_adapter
    import qb_prospective_history_adapter_024 as source024

    promotion_ptr = root / "data/models/nfl/CURRENT_QB_MODEL_023"
    if not promotion_ptr.exists():
        raise FileNotFoundError("QB 0.2.3 prospective promotion pointer missing")
    promotion_dir = root / promotion_ptr.read_text(encoding="utf-8").strip()
    promotion_path = promotion_dir / "NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.json"
    promotion_sha_path = promotion_dir / "NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.sha256"
    if not promotion_path.exists() or not promotion_sha_path.exists():
        raise FileNotFoundError("QB 0.2.3 promotion spec/hash missing")
    promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    q24.assert_promoted_spec(promotion)
    expected_promotion_sha = promotion_sha_path.read_text(encoding="utf-8").strip().split()[0]
    actual_promotion_sha = hashlib.sha256(canonical_bytes(promotion)).hexdigest()
    if expected_promotion_sha != actual_promotion_sha:
        raise ValueError("QB 0.2.3 promotion SHA drift")

    freeze_dir = root / str(promotion.get("sourceFreezeDirectory") or "")
    holdout_dir = root / str(promotion.get("sourceHoldoutDirectory") or "")
    freeze_path = freeze_dir / "NFL_QB_PASSING_YARDS_FROZEN_SPEC.json"
    holdout_audit_path = holdout_dir / "NFL_QB_PASSING_YARDS_2025_HOLDOUT_AUDIT.json"
    holdout_targets_path = holdout_dir / "NFL_QB_2025_OFFICIAL_TARGETS.jsonl"
    for p in (freeze_path, holdout_audit_path, holdout_targets_path):
        if not p.exists():
            raise FileNotFoundError(f"QB 0.2.4 source missing: {p}")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    frozen_sha = hashlib.sha256(canonical_bytes(freeze)).hexdigest()
    if frozen_sha != promotion.get("frozenSpecSha256"):
        raise ValueError("QB 0.2.4 frozen-model SHA drift")
    if promotion.get("model") != freeze.get("model") or promotion.get("featureNames") != freeze.get("featureNames"):
        raise ValueError("QB 0.2.4 promoted model/feature payload drift")

    holdout = json.loads(holdout_audit_path.read_text(encoding="utf-8"))
    if holdout.get("holdoutDisposition") != "CONFIRMATORY_HOLDOUT_PASS":
        raise ValueError("QB 0.2.4 requires confirmatory 2025 holdout pass")
    if holdout.get("modelRefitPerformed") is not False or holdout.get("candidateReselectionPerformed") is not False:
        raise ValueError("QB 0.2.4 holdout mutation drift")

    target = q24.build_target_context(
        game_id=args.game_id,
        team=args.team,
        qb_gsis_id=args.qb_gsis_id,
        qb_name=args.qb_name,
        identity_source=args.identity_source,
        contract=contract,
    )

    if target.season != 2026 or target.week != 3:
        raise ValueError("Week 3 scorer requires a 2026 Week 3 target")

    dev_target_dir = root / str(freeze.get("sourceOfficialTargetDirectory") or "")
    dev_targets_path = dev_target_dir / "NFL_QB_OFFICIAL_TARGETS.jsonl"
    if not dev_targets_path.exists():
        raise FileNotFoundError(f"development official targets missing: {dev_targets_path}")
    dev = load_jsonl(dev_targets_path)
    if not dev or any(int(r.get("season") or 0) >= 2025 for r in dev):
        raise ValueError("development target source is not strictly 2016-2024")
    holdout_rows = load_jsonl(holdout_targets_path)
    if len(holdout_rows) != int(holdout.get("targetRows") or 0) or {int(r.get("season") or 0) for r in holdout_rows} != {2025}:
        raise ValueError("2025 lagged-history source drift")

    if str(args.source_manifest or "").strip():
        source_manifest_path = Path(args.source_manifest).expanduser().resolve()
        if not source_manifest_path.exists():
            raise FileNotFoundError(f"provided prospective source manifest missing: {source_manifest_path}")
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        if str(source_manifest.get("version")) != "0.2.4":
            raise ValueError("provided prospective source manifest version drift")
        if int(source_manifest.get("prospectiveSeason") or 0) != 2026:
            raise ValueError("provided prospective source manifest season drift")
        if int(source_manifest.get("targetWeek") or 0) != int(target.week):
            raise ValueError("provided prospective source manifest target-week mismatch")
    else:
        source_manifest_path = source024.acquire(root, target_week=target.week)
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    schedule_asset = source024.asset_by_source(source_manifest, "schedules")
    pbp_asset = source024.asset_by_source(source_manifest, "play_by_play")
    stats_asset = source024.asset_by_source(source_manifest, "player_stats_weekly")
    schedule_path = root / schedule_asset["blobPath"]
    pbp_path = root / pbp_asset["blobPath"]
    stats_path = root / stats_asset["blobPath"]

    for asset in (schedule_asset, pbp_asset, stats_asset):
        if not asset.get("sha256") or sha256_file(root / asset["blobPath"]) != asset["sha256"]:
            raise ValueError("QB prospective asset hash mismatch")
    schedule = scope.read_csv(schedule_path)
    scope.prior_complete(schedule)
    target_games = [r for r in schedule if str(r.get("game_id")) == target.game_id]
    if len(target_games) != 1 or scope.kickoff(target_games[0]) != scope.aware(args.kickoff_utc):
        raise ValueError("QB kickoff/target disagrees with acquired schedule")
    scope.before_kickoff(target_games)
    expected_prior_keys = schedule_prior_keys(schedule_path, target.week, contract)

    pf = pq.ParquetFile(pbp_path)
    pnames = set(pf.schema_arrow.names)
    scope_field = "season_type" if "season_type" in pnames else ("game_type" if "game_type" in pnames else "")
    if not scope_field:
        raise ValueError("2026 PBP lacks season_type/game_type; cannot enforce REG as-of scope")
    missing_pbp = [c for c in q15.REQUIRED_PBP_FIELDS if c not in pnames]
    if missing_pbp:
        raise ValueError("2026 PBP missing scorer fields: " + ", ".join(missing_pbp))
    pcols = list(q15.REQUIRED_PBP_FIELDS) + [c for c in q15.OPTIONAL_PBP_FIELDS if c in pnames]
    if scope_field not in pcols:
        pcols.append(scope_field)
    if target.week <= 1:
        pbp_rows = []
    else:
        pbp_rows = pq.read_table(
            pbp_path,
            columns=pcols,
            filters=[("season", "=", 2026), ("week", "<", target.week), (scope_field, "=", "REG")],
        ).to_pylist()
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for raw in pbp_rows:
        gid = str(raw.get("game_id") or "").strip()
        team_raw = str(raw.get("posteam") or "").strip().upper()
        if not gid or not team_raw:
            continue
        rr = dict(raw); rr["posteam"] = contract.normalize_team_abbr(team_raw)
        grouped[(gid, rr["posteam"])].append(rr)
    mechanism_2026: list[dict] = []
    for grows in grouped.values():
        agg = q15.aggregate_team_game(grows)
        if agg is not None:
            mechanism_2026.append(agg)
    mechanism_2026.sort(key=lambda r: (int(r["week"]), r["game_id"], r["team"]))
    observed_prior_keys = {(str(r["game_id"]), str(r["team"])) for r in mechanism_2026}
    if observed_prior_keys != expected_prior_keys:
        missing_keys = sorted(expected_prior_keys - observed_prior_keys)
        extra_keys = sorted(observed_prior_keys - expected_prior_keys)
        raise ValueError(
            f"2026 prior-week PBP completeness fail expected={len(expected_prior_keys)} observed={len(observed_prior_keys)} "
            f"missing={len(missing_keys)} extra={len(extra_keys)} samples_missing={missing_keys[:8]} samples_extra={extra_keys[:8]}"
        )

    target_ids = {str(r["observed_start_qb_gsis_id"]) for r in mechanism_2026}
    opf = pq.ParquetFile(stats_path)
    onames = set(opf.schema_arrow.names)
    missing_official = [c for c in official_adapter.REQUIRED_FIELDS if c not in onames]
    if missing_official:
        raise ValueError("2026 weekly player stats missing fields: " + ", ".join(missing_official))
    ocols = list(official_adapter.REQUIRED_FIELDS) + [c for c in official_adapter.OPTIONAL_FIELDS if c in onames]
    if target.week <= 1:
        official_raw = []
    else:
        official_raw = pq.read_table(
            stats_path,
            columns=ocols,
            filters=[("season", "=", 2026), ("week", "<", target.week), ("season_type", "=", "REG")],
        ).to_pylist()
    official: list[dict] = []
    for raw in official_raw:
        if str(raw.get("player_id") or "").strip() not in target_ids:
            continue
        row = official_adapter.normalize_row(raw)
        row["source_sha256"] = stats_asset["sha256"]
        official.append(row)
    by_official: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in official:
        by_official[q19.official_key(row)].append(row)

    prior_2026: list[dict] = []
    missing_keys: list[tuple[str, str]] = []
    duplicate_keys: list[tuple[str, str]] = []
    team_mismatches: list[tuple[str, str]] = []
    for mechanism in mechanism_2026:
        key = q19.target_key(mechanism)
        matches = by_official.get(key, [])
        if not matches:
            missing_keys.append(key); continue
        if len(matches) != 1:
            duplicate_keys.append(key); continue
        off = matches[0]
        if str(off.get("team") or "").upper() != str(mechanism.get("team") or "").upper():
            team_mismatches.append(key); continue
        row = q19.attach_official_target(mechanism, off)
        prior_2026.append(row)
    if missing_keys or duplicate_keys or team_mismatches:
        raise ValueError(
            f"2026 prior-history official join failed missing={len(missing_keys)} duplicate={len(duplicate_keys)} "
            f"teamMismatch={len(team_mismatches)} samples={missing_keys[:8]}"
        )
    required = ("official_attempts", "official_completions", "official_passing_yards", "official_sacks_suffered")
    bad_required = [r for r in prior_2026 if any(r.get(f) is None for f in required)]
    if bad_required:
        raise ValueError(f"2026 prior-history required official values missing: {len(bad_required)}")

    history = q24.add_game_context(dev + holdout_rows + prior_2026, contract)
    cutoff = q24.assert_history_cutoff(history, target.week)
    asof = q24.build_asof_feature_row(history, target, q20)
    feature_names = list(promotion.get("featureNames") or [])
    if feature_names != list(q20.FEATURE_NAMES) or promotion["model"].get("featureNames") != feature_names:
        raise ValueError("QB 0.2.4 frozen feature contract mismatch")
    point = q21.predict_serialized_ridge(promotion["model"], asof.x)
    distribution = q24.predictive_distribution(point, promotion["residualCalibration"])

    scope.before_kickoff([selected_game])
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/prospective/nfl/qb_passing_yards_week3_0245" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    prior_path = out_dir / "NFL_QB_2026_PRIOR_HISTORY.jsonl"
    with prior_path.open("w", encoding="utf-8") as f:
        for row in prior_2026:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    counts_by_season: dict[str, int] = defaultdict(int)
    for row in history:
        counts_by_season[str(int(row.get("season") or 0))] += 1
    score = {
        "version": q24.VERSION,
        "lineage": q24.LINEAGE,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "operationalVersion":"0.2.4.5", "codeRoot":str(code_root),
        "runnerSha256":sha256_file(Path(__file__)), "kickoffUtc":args.kickoff_utc,
        "runId": run_id,
        "status": "PROSPECTIVE_SHADOW_SCORE_FROZEN_0.2.1",
        "promotionSpecSha256": actual_promotion_sha,
        "frozenSpecSha256": frozen_sha,
        "frozenCandidate": q24.FROZEN_CANDIDATE,
        "target": {
            "season": target.season, "week": target.week, "game_id": target.game_id,
            "team": target.team, "opponent": target.opponent, "home": target.home,
            "qb_gsis_id": target.qb_gsis_id, "qb_name": target.qb_name,
            "identitySource": target.identity_source,
        },
        "asOfPolicy": "all 2026 performance rows strictly week < target week; same-week outcomes excluded even if source asset contains them",
        "historyRowsBySeason": dict(sorted(counts_by_season.items())),
        "prior2026TeamGameRows": len(prior_2026),
        "max2026HistoryWeek": asof.max_2026_history_week,
        "scheduleExpectedPriorTeamGameRows": len(expected_prior_keys),
        "schedulePriorCompletenessPct": 100.0 if len(expected_prior_keys) == len(prior_2026) else 0.0,
        "officialPriorJoinCoveragePct": 100.0,
        "qbPriorGames": asof.qb_prior_games,
        "teamPriorGames": asof.team_prior_games,
        "defensePriorGames": asof.defense_prior_games,
        "baselineLast4PassingYards": asof.baseline_last4,
        "projectionPassingYards": float(point),
        "frozenPredictiveDistribution": distribution,
        "coefficientRefitPerformed": False,
        "candidateReselectionPerformed": False,
        "targetOrLater2026OutcomeRowsAdmitted": 0,
        "marketPriceFieldsAdmitted": 0,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "marketExecutionEligible": False,
        "sourceProspectiveManifest": str(source_manifest_path.relative_to(root)),
        "sourceHashes": {
            "promotionSpec": sha256_file(promotion_path),
            "freezeSpec": sha256_file(freeze_path),
            "developmentTargets": sha256_file(dev_targets_path),
            "holdoutTargets": sha256_file(holdout_targets_path),
            "schedule": schedule_asset["sha256"],
            "playByPlay2026": pbp_asset["sha256"],
            "playerStats2026": stats_asset["sha256"],
        },
        "nextGate": "WIRE_VERIFIED_IDENTITY_BRIDGE_AND_MARKET_LINE_PROBABILITY_WITHOUT_REFIT",
    }
    score_path = out_dir / "NFL_QB_PASSING_YARDS_ASOF_SCORE.json"
    scope.before_kickoff([selected_game])
    score_path.write_text(json.dumps(score, indent=2) + "\n", encoding="utf-8")
    scope.before_kickoff([selected_game])
    atomic_pointer(root / "data/prospective/nfl/CURRENT_QB_PASSING_YARDS_WEEK3_0245", str(out_dir.relative_to(root)))

    q = distribution["predictiveQuantiles"]
    print("\nNFL QB MODEL 0.2.4.5 — WEEK 3 AS-OF PASSING-YARDS SHADOW SCORE")
    label = f"{target.qb_name} · " if target.qb_name else ""
    print(f"Target: {target.game_id} · {target.team} vs {target.opponent} · {label}{target.qb_gsis_id}")
    print(f"Verified identity source: {target.identity_source}")
    print(f"Frozen candidate: {q24.FROZEN_CANDIDATE} · coefficients unchanged from 0.2.1")
    print(f"Feature cutoff: 2026 REG weeks strictly < {target.week} · target/same-week outcome rows admitted 0")
    print(f"2026 prior history: {len(prior_2026):,} team-games · schedule completeness 100.00% · official join 100.00% · max week {asof.max_2026_history_week}")
    print(f"QB prior games {asof.qb_prior_games} · team prior games {asof.team_prior_games} · defense prior games {asof.defense_prior_games}")
    print("Market dependency: NO PRICE DATA · OddsPapi 0 · frozen OMEGA mutation NO")
    print(f"\nPASSING-YARDS PROJECTION: {point:.1f}")
    print(f"  frozen central80: [{distribution['central80'][0]:.1f}, {distribution['central80'][1]:.1f}]")
    print(f"  frozen central90: [{distribution['central90'][0]:.1f}, {distribution['central90'][1]:.1f}]")
    print(f"  predictive p50 from frozen OOF residuals: {q['p50']:.1f}")
    print(f"  last-4 baseline context: {asof.baseline_last4:.1f}")
    print("Market execution eligible: NO · no prop line/price consumed")
    print(f"Score: {score_path}")
    print(f"Prospective source manifest: {source_manifest_path}")
    print("NEXT GATE: WIRE_VERIFIED_IDENTITY_BRIDGE_AND_MARKET_LINE_PROBABILITY_WITHOUT_REFIT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


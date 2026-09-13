#!/usr/bin/env python3
"""OMEGA 0.13.1 — controlled completion of the immutable 2025 T+A holdout score.

Integrity design:
* Pins the exact OMEGA 0.11 frozen-spec SHA256.
* Pins the exact OMEGA 0.12 blind-ledger SHA256 and row/schema coverage.
* Pins the exact 2025 PBP asset SHA256 already used by the walk-forward builder.
* Uses the blind ledger itself as the immutable participant row universe.
* Does NOT read target-game snap magnitude while scoring.
* Attaches only standard defensive-scrimmage combined tackle credits from PBP.
* Computes only the precommitted overall metrics, fixed position/history slices,
  calibration diagnostics, and paired game-cluster bootstrap.
* Marks OMEGA 2025 consumed and refuses a second scoring run.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence
import argparse
import csv
import hashlib
import json
import math
import os
import random
import shutil
import sys

SCHEMA = "OMEGA_TACKLE_HOLDOUT_SCORE_0.13.1"
LINEAGE = "omega-tackle-v0.13.1-controlled-resume-zero-scope-hotfix-2026-09-11"

EXPECTED_SID = "20260910T205221Z_58d8156a"
EXPECTED_FROZEN_SPEC_SHA256 = "c2ca80b6a144c3aa86bc41bdb82f6f5618ffa279a38f4c6d358025ed7fbd69fb"
EXPECTED_BLIND_SHA256 = "59c1a1726bb705661babe3f51fc408e389a25bece6a18df0fdf79065b08d036e"
EXPECTED_BLIND_AUDIT_SHA256 = "1e15d87999fa0ff5d7e02d1e064c866e49dfbfe9ba6c40c7c17cba72eceb0533"
EXPECTED_2025_PBP_SHA256 = "c6ecedd6d678cc37ed316b23ef84ee1ec6abb69c514bb11868a7ebd5a367df29"
EXPECTED_ROWS = 10524
EXPECTED_GAMES = 272
EXPECTED_WEEKS = tuple(range(1, 19))
EXPECTED_PBP_ROWS = 46452
EXPECTED_TACKLE_EVENTS = 36709
EXPECTED_ZERO_STANDARD_CREDIT_ROWS_ALL_SNAP_AUDIT = 1875
ORIGINAL_013_SCORER_SHA256 = "09523359bcb69bc7f377e65b5a6063afe519cb2989f1873316875c26fd02a553"
EXPECTED_ABORT_ERROR = "FAIL zero-credit row reconciliation drift: 1860 != 1875"
BOOTSTRAP_REPS = 10000
# Frozen here, before scoring 2025. It is not selected from holdout results.
BOOTSTRAP_SEED = 290013
PARTICIPANT_UNIVERSE = "TARGET_GAME_DEFENSIVE_SNAP_GT0_CONDITIONAL_ONLY"

EXPECTED_COLUMNS = [
    "game_id", "season", "week", "team", "opponent", "player_id",
    "display_name", "position", "position_group", "participant_universe",
    "prior_games", "predicted_xto", "predicted_snap_share",
    "benchmark_last4_xtc", "pred_share_RUSH", "shrunk_rate_RUSH",
    "pred_credit_RUSH", "pred_share_COMPLETE_PASS",
    "shrunk_rate_COMPLETE_PASS", "pred_credit_COMPLETE_PASS",
    "pred_share_SCRAMBLE", "shrunk_rate_SCRAMBLE", "pred_credit_SCRAMBLE",
    "pred_share_SACK", "shrunk_rate_SACK", "pred_credit_SACK",
    "pred_share_OTHER_PASS", "shrunk_rate_OTHER_PASS",
    "pred_credit_OTHER_PASS", "predicted_xtc",
]


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


def write_csv(path: Path, rows: list[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: "" if row.get(k) is None else row.get(k) for k in fields})


def num(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"non-numeric value: {v!r}")
    if not math.isfinite(x):
        raise ValueError(f"non-finite numeric value: {v!r}")
    return x


def percentile(xs: Sequence[float], p: float) -> float:
    if not xs:
        raise ValueError("percentile requires non-empty values")
    z = sorted(xs)
    if len(z) == 1:
        return z[0]
    q = max(0.0, min(1.0, p)) * (len(z) - 1)
    lo = int(math.floor(q)); hi = int(math.ceil(q))
    if lo == hi:
        return z[lo]
    w = q - lo
    return z[lo] * (1.0 - w) + z[hi] * w


def metrics(rows: Sequence[dict[str, Any]], pred_field: str) -> dict[str, float | int]:
    ys = [num(r["actual_xtc"]) for r in rows]
    ps = [max(0.0, num(r[pred_field])) for r in rows]
    if not ys:
        raise ValueError("metrics received no rows")
    return {
        "n": len(rows),
        "actualMean": fmean(ys),
        "predictedMean": fmean(ps),
        "mae": fmean(abs(y-p) for y,p in zip(ys,ps)),
        "rmse": math.sqrt(fmean((y-p)**2 for y,p in zip(ys,ps))),
        "biasPredMinusActual": fmean(p-y for y,p in zip(ys,ps)),
    }


def calibration_ols(rows: Sequence[dict[str, Any]], pred_field: str) -> dict[str, float | None]:
    xs = [max(0.0, num(r[pred_field])) for r in rows]
    ys = [num(r["actual_xtc"]) for r in rows]
    if len(xs) < 3:
        return {"intercept": None, "slope": None, "r2": None}
    mx, my = fmean(xs), fmean(ys)
    vx = sum((x-mx)**2 for x in xs)
    vy = sum((y-my)**2 for y in ys)
    if vx <= 1e-12:
        return {"intercept": None, "slope": None, "r2": None}
    cov = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    slope = cov / vx
    intercept = my - slope * mx
    r2 = (cov*cov/(vx*vy)) if vy > 1e-12 else None
    return {"intercept": intercept, "slope": slope, "r2": r2}


def history_band(n: int) -> str:
    if n == 0: return "0_COLD"
    if n == 1: return "1_PRIOR_GAME"
    if n <= 4: return "2-4_PRIOR_GAMES"
    if n <= 8: return "5-8_PRIOR_GAMES"
    return "9+_PRIOR_GAMES"


def compare(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    model = metrics(rows, "predicted_xtc")
    bench = metrics(rows, "benchmark_last4_xtc")
    return {
        "model": model,
        "benchmark": bench,
        "maeImprovement": float(bench["mae"]) - float(model["mae"]),
        "rmseImprovement": float(bench["rmse"]) - float(model["rmse"]),
    }


def grouped_compare(rows: Sequence[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(field) or "UNK")].append(r)
    return {k: compare(v) for k,v in sorted(groups.items())}


def cluster_bootstrap(rows: Sequence[dict[str, Any]], reps: int = BOOTSTRAP_REPS,
                      seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Paired game-cluster bootstrap. Positive improvement means OMEGA is better."""
    by: dict[str, list[tuple[float,float,float]]] = defaultdict(list)
    for r in rows:
        gid = str(r["game_id"])
        by[gid].append((num(r["actual_xtc"]), max(0.0,num(r["predicted_xtc"])),
                        max(0.0,num(r["benchmark_last4_xtc"]))))
    keys = sorted(by)
    if len(keys) != EXPECTED_GAMES:
        raise ValueError(f"bootstrap cluster count drift: {len(keys)} != {EXPECTED_GAMES}")
    rng = random.Random(seed)
    mae_diffs: list[float] = []
    rmse_diffs: list[float] = []
    for _ in range(reps):
        ae_m = ae_b = se_m = se_b = 0.0
        n = 0
        for _j in range(len(keys)):
            k = keys[rng.randrange(len(keys))]
            for actual, model, bench in by[k]:
                ae_m += abs(actual-model); ae_b += abs(actual-bench)
                se_m += (actual-model)**2; se_b += (actual-bench)**2
                n += 1
        mae_diffs.append((ae_b-ae_m)/n)
        rmse_diffs.append(math.sqrt(se_b/n)-math.sqrt(se_m/n))
    point = compare(rows)
    return {
        "cluster": "game_id",
        "clusters": len(keys),
        "reps": reps,
        "seed": seed,
        "maeImprovementPoint": point["maeImprovement"],
        "maeImprovementCI95": [percentile(mae_diffs,.025), percentile(mae_diffs,.975)],
        "maeProbabilityPositive": sum(x>0 for x in mae_diffs)/len(mae_diffs),
        "rmseImprovementPoint": point["rmseImprovement"],
        "rmseImprovementCI95": [percentile(rmse_diffs,.025), percentile(rmse_diffs,.975)],
        "rmseProbabilityPositive": sum(x>0 for x in rmse_diffs)/len(rmse_diffs),
    }


def precommitted_verdict(cmp: dict[str, Any], boot: dict[str, Any]) -> str:
    mi = float(cmp["maeImprovement"])
    ri = float(cmp["rmseImprovement"])
    if mi > 0 and ri > 0:
        if float(boot["maeImprovementCI95"][0]) > 0 and float(boot["rmseImprovementCI95"][0]) > 0:
            return "STRONG_PASS"
        return "DIRECTIONAL_PASS"
    if mi < 0 and ri < 0:
        return "FAIL_BOTH"
    return "MIXED"


def validate_blind_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"FAIL blind row count drift: {len(rows)} != {EXPECTED_ROWS}")
    if not rows:
        raise SystemExit("FAIL blind ledger empty")
    cols = list(rows[0].keys())
    if cols != EXPECTED_COLUMNS:
        raise SystemExit(f"FAIL blind schema drift\nexpected={EXPECTED_COLUMNS}\nfound={cols}")
    keys: set[tuple[str,str]] = set()
    games: set[str] = set(); weeks: set[int] = set()
    numeric_nonnegative = ("predicted_xtc", "benchmark_last4_xtc", "predicted_xto", "predicted_snap_share")
    for r in rows:
        if int(r["season"]) != 2025:
            raise SystemExit("FAIL non-2025 row in blind ledger")
        if r["participant_universe"] != PARTICIPANT_UNIVERSE:
            raise SystemExit("FAIL participant-universe label drift")
        key = (r["game_id"], r["player_id"])
        if not key[0] or not key[1] or key in keys:
            raise SystemExit(f"FAIL duplicate/blank blind key: {key}")
        keys.add(key); games.add(r["game_id"]); weeks.add(int(r["week"]))
        if int(r["prior_games"]) < 0:
            raise SystemExit("FAIL negative prior_games")
        for c in numeric_nonnegative:
            if num(r[c]) < 0:
                raise SystemExit(f"FAIL negative {c}")
    if len(games) != EXPECTED_GAMES:
        raise SystemExit(f"FAIL blind game count drift: {len(games)} != {EXPECTED_GAMES}")
    if tuple(sorted(weeks)) != EXPECTED_WEEKS:
        raise SystemExit(f"FAIL blind week coverage drift: {sorted(weeks)}")
    return {"rows":len(rows), "games":len(games), "weeks":sorted(weeks), "keys":keys}


def parquet_rows(path: Path, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> tuple[list[dict[str, Any]], set[str]]:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    missing = [c for c in required if c not in names]
    if missing:
        raise SystemExit(f"FAIL {path.name} missing PBP columns: {', '.join(missing)}")
    cols = list(required) + [c for c in optional if c in names and c not in required]
    return pf.read(columns=cols).to_pylist(), names


def normalize_team(contract: Any, v: Any) -> str:
    s = str(v or "").strip()
    return contract.normalize_team_abbr(s) if s else ""


def atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def preflight(root: Path, *, allow_started: bool = False) -> dict[str, Any]:
    # Freeze pointers and immutable artifacts first.
    frozen_ptr = root / "data/models/nfl/CURRENT_OMEGA_TACKLE_FROZEN"
    blind_ptr = root / "data/models/nfl/CURRENT_OMEGA_TACKLE_BLIND_2025"
    if not frozen_ptr.exists() or frozen_ptr.read_text(encoding="utf-8").strip() != EXPECTED_SID:
        raise SystemExit("FAIL frozen OMEGA pointer mismatch")
    if not blind_ptr.exists() or blind_ptr.read_text(encoding="utf-8").strip() != EXPECTED_SID:
        raise SystemExit("FAIL blind OMEGA pointer mismatch")

    frozen = root / "data/models/nfl/omega_tackle_frozen" / EXPECTED_SID
    spec = frozen / "OMEGA_TACKLE_FROZEN_SPEC.json"
    spec_sidecar = frozen / "OMEGA_TACKLE_FROZEN_SPEC.sha256"
    if not spec.exists() or not spec_sidecar.exists():
        raise SystemExit("FAIL frozen spec files missing")
    spec_hash = sha256_file(spec)
    if spec_hash != EXPECTED_FROZEN_SPEC_SHA256 or spec_sidecar.read_text(encoding="utf-8").strip() != spec_hash:
        raise SystemExit("FAIL frozen spec hash mismatch")
    spec_obj = json.loads(spec.read_text(encoding="utf-8"))
    hp = spec_obj.get("holdoutProtocol", {})
    if int(hp.get("bootstrapReps") or 0) != BOOTSTRAP_REPS or hp.get("bootstrapCluster") != "game_id":
        raise SystemExit("FAIL frozen bootstrap contract drift")
    if not hp.get("scoreExactlyOnce") or not hp.get("blindPredictionLedgerBeforeScore"):
        raise SystemExit("FAIL frozen one-shot contract drift")

    blind = root / "data/models/nfl/omega_tackle_012_blind_2025" / EXPECTED_SID
    pred = blind / "OMEGA_2025_BLIND_PREDICTIONS.csv"
    pred_sidecar = blind / "OMEGA_2025_BLIND_PREDICTIONS.sha256"
    blind_audit_path = blind / "OMEGA_0.12_BLIND_AUDIT.json"
    for p in (pred, pred_sidecar, blind_audit_path):
        if not p.exists():
            raise SystemExit(f"FAIL required blind artifact missing: {p}")
    pred_hash = sha256_file(pred)
    if pred_hash != EXPECTED_BLIND_SHA256 or pred_sidecar.read_text(encoding="utf-8").strip() != pred_hash:
        raise SystemExit("FAIL blind prediction hash mismatch")
    if sha256_file(blind_audit_path) != EXPECTED_BLIND_AUDIT_SHA256:
        raise SystemExit("FAIL blind audit hash mismatch")
    blind_audit = json.loads(blind_audit_path.read_text(encoding="utf-8"))
    integ = blind_audit.get("integrity", {})
    if (blind_audit.get("frozenSpecSha256") != EXPECTED_FROZEN_SPEC_SHA256 or
        blind_audit.get("predictionLedgerSha256") != EXPECTED_BLIND_SHA256 or
        integ.get("targetTackleOutcomesSerialized") is not False or
        integ.get("targetSnapMagnitudeUsedAsFeature") is not False or
        integ.get("scoreAttached") is not False or
        int(integ.get("marketFieldsRead") or 0) != 0 or
        int(integ.get("oddsPapiRequests") or 0) != 0 or
        int(integ.get("networkRequests") or 0) != 0):
        raise SystemExit("FAIL blind audit integrity drift")

    rows = read_csv(pred)
    blind_summary = validate_blind_rows(rows)

    consumed = root / "data/models/nfl/OMEGA_TACKLE_2025_CONSUMED.json"
    started = root / "data/models/nfl/OMEGA_TACKLE_2025_SCORING_STARTED.json"
    out = root / "data/models/nfl/omega_tackle_013_holdout_2025" / EXPECTED_SID
    if consumed.exists() or out.exists():
        raise SystemExit("FAIL OMEGA 2025 has already been scored/consumed; refusing re-evaluation")
    if started.exists() and not allow_started:
        raise SystemExit("FAIL prior OMEGA 2025 scoring-start marker exists; refusing automatic retry")

    # Verify exact 2025 outcome source by hash before reading semantic outcome rows.
    source_manifest = root / "data/raw/nfl/nflverse/snapshots" / EXPECTED_SID / "SOURCE_MANIFEST.json"
    if not source_manifest.exists():
        raise SystemExit("FAIL frozen source manifest missing")
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    assets = {(x.get("source"), x.get("season")):x for x in manifest.get("assets", [])}
    pbp_asset = assets.get(("play_by_play", 2025))
    if not pbp_asset:
        raise SystemExit("FAIL 2025 PBP asset missing from frozen source snapshot")
    pbp_path = root / str(pbp_asset.get("blobPath") or "")
    if not pbp_path.exists():
        raise SystemExit("FAIL 2025 PBP blob missing")
    if pbp_asset.get("sha256") != EXPECTED_2025_PBP_SHA256 or sha256_file(pbp_path) != EXPECTED_2025_PBP_SHA256:
        raise SystemExit("FAIL 2025 PBP asset hash mismatch")

    phase1_games = read_csv(root / "data/normalized/nfl/phase1" / EXPECTED_SID / "game_identity.csv")
    games = [r for r in phase1_games if int(r.get("season") or 0) == 2025 and str(r.get("game_type") or "") == "REG"]
    allowed = {r["game_id"] for r in games}
    if len(allowed) != EXPECTED_GAMES or allowed != {r["game_id"] for r in rows}:
        raise SystemExit("FAIL 2025 REG game universe differs from immutable blind ledger")

    # Environment/schema checks before we create the one-shot start marker.
    sys.path[:0] = [str(root/"packages/models/nfl/omega"), str(root/"packages/providers/nflverse/src")]
    try:
        import pyarrow.parquet as pq  # noqa: F401
        import tackle_events as te
        import contract
    except Exception as e:
        raise SystemExit(f"FAIL scoring dependency import: {e}")
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(pbp_path)
    names = set(pf.schema_arrow.names)
    required = {"game_id","play_id","season","week","posteam","defteam"}
    missing = required - names
    if missing:
        raise SystemExit(f"FAIL 2025 PBP schema missing: {sorted(missing)}")
    tackle_needed = set(te.TACKLE_ID_COLUMNS) | set(te.TACKLE_NAME_COLUMNS) | set(te.TACKLE_TEAM_COLUMNS)
    if not (set(te.TACKLE_ID_COLUMNS) & names):
        raise SystemExit("FAIL 2025 PBP has no tackle identity columns")

    return {
        "root":root, "spec":spec, "specObj":spec_obj, "blindDir":blind, "pred":pred,
        "rows":rows, "blindSummary":blind_summary, "blindAudit":blind_audit, "pbpAsset":pbp_asset,
        "pbpPath":pbp_path, "allowedGames":allowed, "te":te, "contract":contract,
        "consumed":consumed, "started":started, "out":out,
    }


def validate_recovery_state(root: Path) -> dict[str, Any]:
    original = root / "scripts/nfl/score_omega_tackle_013_holdout.py"
    started = root / "data/models/nfl/OMEGA_TACKLE_2025_SCORING_STARTED.json"
    aborted = root / "data/models/nfl/OMEGA_TACKLE_2025_SCORING_ABORTED.json"
    consumed = root / "data/models/nfl/OMEGA_TACKLE_2025_CONSUMED.json"
    out = root / "data/models/nfl/omega_tackle_013_holdout_2025" / EXPECTED_SID
    if not original.exists() or sha256_file(original) != ORIGINAL_013_SCORER_SHA256:
        raise SystemExit("FAIL original 0.13 scorer hash mismatch; refusing controlled resume")
    if consumed.exists() or out.exists():
        raise SystemExit("FAIL a completed OMEGA 2025 score already exists; refusing recovery")
    if not started.exists() or not aborted.exists():
        raise SystemExit("FAIL expected 0.13 start/abort markers are missing; refusing recovery")
    sj = json.loads(started.read_text(encoding="utf-8"))
    aj = json.loads(aborted.read_text(encoding="utf-8"))
    pinned = (
        sj.get("status") == "SCORING_STARTED_FAIL_CLOSED" and
        sj.get("sourceSnapshotId") == EXPECTED_SID and
        sj.get("frozenSpecSha256") == EXPECTED_FROZEN_SPEC_SHA256 and
        sj.get("blindPredictionSha256") == EXPECTED_BLIND_SHA256 and
        sj.get("pbpAssetSha256") == EXPECTED_2025_PBP_SHA256 and
        sj.get("bootstrap", {}).get("cluster") == "game_id" and
        int(sj.get("bootstrap", {}).get("reps") or 0) == BOOTSTRAP_REPS and
        int(sj.get("bootstrap", {}).get("seed") or 0) == BOOTSTRAP_SEED
    )
    if not pinned:
        raise SystemExit("FAIL original 0.13 scoring-start marker does not match frozen contract")
    if aj.get("errorType") != "SystemExit" or aj.get("error") != EXPECTED_ABORT_ERROR:
        raise SystemExit(f"FAIL abort state is not the known 0.13 reconciliation bug: {aj.get('error')!r}")
    return {"started": sj, "aborted": aj}


def resolved_zero_reconciliation(ctx: dict[str, Any], zero_rows: int) -> dict[str, int]:
    xa = ctx["blindAudit"].get("source", {}).get("2025ExposureAudit", {})
    snap_all = int(xa.get("snapDefensiveExposureRows") or -1)
    resolved = int(xa.get("resolvedSnapDefensiveExposureRows") or -1)
    unresolved = int(xa.get("unresolvedSnapDefensiveExposureRows") or -1)
    fit_eligible = int(xa.get("fitEligibleRows") or -1)
    all_snap_zero = int(xa.get("zeroStandardCreditSnapRows") or -1)
    if all_snap_zero != EXPECTED_ZERO_STANDARD_CREDIT_ROWS_ALL_SNAP_AUDIT:
        raise SystemExit("FAIL frozen 0.12 all-snap zero-credit audit count drift")
    if snap_all != resolved + unresolved:
        raise SystemExit("FAIL frozen 0.12 exposure identity reconciliation drift")
    if resolved != EXPECTED_ROWS or fit_eligible != EXPECTED_ROWS:
        raise SystemExit("FAIL frozen 0.12 resolved/fit-eligible universe differs from blind ledger")
    expected_resolved_zero = all_snap_zero - unresolved
    if zero_rows != expected_resolved_zero:
        raise SystemExit(f"FAIL resolved-ledger zero-credit reconciliation drift: {zero_rows} != {expected_resolved_zero}")
    return {
        "allSnapExposureRows": snap_all,
        "resolvedSnapExposureRows": resolved,
        "unresolvedSnapExposureRows": unresolved,
        "allSnapZeroCreditRows": all_snap_zero,
        "expectedResolvedLedgerZeroCreditRows": expected_resolved_zero,
        "observedResolvedLedgerZeroCreditRows": zero_rows,
    }

def reconstruct_actuals(ctx: dict[str, Any]) -> tuple[dict[tuple[str,str], int], dict[str, Any]]:
    te = ctx["te"]; contract = ctx["contract"]
    required = ("game_id","play_id","season","week","posteam","defteam")
    optional = (
        "play_type","no_play","play_deleted","special_teams_play","qtr","down","ydstogo",
        "yardline_100","game_seconds_remaining","score_differential","score_differential_post",
        "yards_gained","air_yards","yards_after_catch","run_location","run_gap","pass_location",
        "pass_length","shotgun","no_huddle","qb_scramble","sack","complete_pass","interception",
        "fumble","fumble_lost","rush_attempt","rush","pass_attempt","qb_dropback",
    ) + tuple(te.TACKLE_ID_COLUMNS) + tuple(te.TACKLE_NAME_COLUMNS) + tuple(te.TACKLE_TEAM_COLUMNS)
    raw, _ = parquet_rows(ctx["pbpPath"], required, optional)
    allowed = ctx["allowedGames"]
    actual: dict[tuple[str,str], int] = defaultdict(int)
    pbp_rows = 0; events = 0; standard_events = 0
    for r in raw:
        gid = str(r.get("game_id") or "")
        if gid not in allowed:
            continue
        if r.get("posteam"): r["posteam"] = normalize_team(contract, r["posteam"])
        if r.get("defteam"): r["defteam"] = normalize_team(contract, r["defteam"])
        evs = te.extract_credit_events(r)
        pbp_rows += 1; events += len(evs)
        for e in evs:
            if int(e.get("is_standard_def_scrimmage_credit") or 0) != 1:
                continue
            pid = str(e.get("player_id") or "").strip()
            if not pid:
                raise SystemExit(f"FAIL standard 2025 tackle credit without player_id in {gid}")
            unit = int(e.get("combined_credit_unit") or 1)
            if unit <= 0:
                raise SystemExit("FAIL non-positive standard tackle credit unit")
            actual[(gid,pid)] += unit
            standard_events += unit
    if pbp_rows != EXPECTED_PBP_ROWS:
        raise SystemExit(f"FAIL 2025 reconstructed PBP row drift: {pbp_rows} != {EXPECTED_PBP_ROWS}")
    if events != EXPECTED_TACKLE_EVENTS:
        raise SystemExit(f"FAIL 2025 tackle-event count drift: {events} != {EXPECTED_TACKLE_EVENTS}")
    return dict(actual), {"pbpRows":pbp_rows, "tackleEvents":events, "standardCreditUnitsAllEventKeys":standard_events}


def score_once(root: Path) -> dict[str, Any]:
    validate_recovery_state(root)
    ctx = preflight(root, allow_started=True)
    started = ctx["started"]
    recovery_started = root / "data/models/nfl/OMEGA_TACKLE_2025_SCORING_RECOVERY_STARTED.json"
    atomic_json(recovery_started, {
        "schemaVersion":SCHEMA,
        "status":"CONTROLLED_RESUME_OF_KNOWN_0.13_RECONCILIATION_BUG",
        "startedAt":now(),
        "sourceSnapshotId":EXPECTED_SID,
        "frozenSpecSha256":EXPECTED_FROZEN_SPEC_SHA256,
        "blindPredictionSha256":EXPECTED_BLIND_SHA256,
        "original013ScorerSha256":ORIGINAL_013_SCORER_SHA256,
        "originalAbortError":EXPECTED_ABORT_ERROR,
        "modelOrBenchmarkChanged":False,
        "rowUniverseChanged":False,
        "bootstrapChanged":False,
    })

    try:
        actual_map, source_audit = reconstruct_actuals(ctx)
        rows: list[dict[str, Any]] = []
        ledger_keys = ctx["blindSummary"]["keys"]
        for r in ctx["rows"]:
            x: dict[str, Any] = dict(r)
            actual = int(actual_map.get((r["game_id"], r["player_id"]), 0))
            x["actual_xtc"] = actual
            x["model_residual_actual_minus_pred"] = actual - num(r["predicted_xtc"])
            x["benchmark_residual_actual_minus_pred"] = actual - num(r["benchmark_last4_xtc"])
            x["model_abs_error"] = abs(actual - num(r["predicted_xtc"]))
            x["benchmark_abs_error"] = abs(actual - num(r["benchmark_last4_xtc"]))
            x["diagnostic_history_band"] = history_band(int(r["prior_games"]))
            rows.append(x)

        zero_rows = sum(1 for r in rows if int(r["actual_xtc"]) == 0)
        zero_scope_audit = resolved_zero_reconciliation(ctx, zero_rows)

        outside = sorted(k for k,v in actual_map.items() if v > 0 and k not in ledger_keys)
        overall = compare(rows)
        boot = cluster_bootstrap(rows)
        verdict = precommitted_verdict(overall, boot)
        calibration = {
            "omega": calibration_ols(rows, "predicted_xtc"),
            "benchmark": calibration_ols(rows, "benchmark_last4_xtc"),
        }
        by_position = grouped_compare(rows, "position_group")
        by_history = grouped_compare(rows, "diagnostic_history_band")

        report = {
            "schemaVersion":SCHEMA,
            "lineage":LINEAGE,
            "scoredAt":now(),
            "sourceSnapshotId":EXPECTED_SID,
            "holdoutSeason":2025,
            "frozenSpecSha256":EXPECTED_FROZEN_SPEC_SHA256,
            "blindPredictionSha256":EXPECTED_BLIND_SHA256,
            "pbpAssetSha256":EXPECTED_2025_PBP_SHA256,
            "integrity":{
                "scoreExactlyOnce":True,
                "controlledResumeAfterKnown013AuditScopeBug":True,
                "modelRefitOn2025":False,
                "rowUniverseChangedAfterBlindFreeze":False,
                "benchmarkChangedAfterBlindFreeze":False,
                "targetSnapMagnitudeReadForScoring":False,
                "marketFieldsRead":0,
                "oddsPapiRequests":0,
                "networkRequests":0,
                "sportsbookSettlementAssumed":False,
                "participantUniverse":PARTICIPANT_UNIVERSE,
            },
            "coverage":{
                "rows":len(rows),
                "games":len({r["game_id"] for r in rows}),
                "weeks":len({int(r["week"]) for r in rows}),
                "zeroActualRows":zero_rows,
                "positiveActualKeysOutsideFrozenLedger":len(outside),
                "positiveActualCreditsOutsideFrozenLedger":sum(actual_map[k] for k in outside),
                "sourceAudit":source_audit,
                "zeroCreditScopeReconciliation":zero_scope_audit,
            },
            "overall":overall,
            "pairedGameClusterBootstrap":boot,
            "calibration":calibration,
            "fixedDiagnostics":{
                "byPositionGroup":by_position,
                "byPriorGameBand":by_history,
            },
            "precommittedVerdict":verdict,
            "verdictRules":ctx["specObj"].get("holdoutProtocol",{}).get("verdictRules",{}),
            "participantUniverseLimitation":ctx["specObj"].get("holdoutProtocol",{}).get("participantUniverseLimitation"),
            "postHoldoutRule":"OMEGA tackle 2025 was opened by 0.13 and is CONSUMED FOREVER; 0.13.1 only completes the frozen precommitted score after a non-model audit-scope bug.",
        }

        out = ctx["out"]
        staging = out.parent / ("." + EXPECTED_SID + ".staging")
        if staging.exists():
            raise SystemExit(f"FAIL stale score staging directory exists: {staging}")
        staging.mkdir(parents=True, exist_ok=False)
        try:
            scored_fields = EXPECTED_COLUMNS + [
                "actual_xtc", "model_residual_actual_minus_pred",
                "benchmark_residual_actual_minus_pred", "model_abs_error",
                "benchmark_abs_error", "diagnostic_history_band",
            ]
            scored_path = staging / "OMEGA_2025_HOLDOUT_SCORED.csv"
            write_csv(scored_path, rows, scored_fields)
            (staging / "OMEGA_2025_HOLDOUT_SCORED.sha256").write_text(sha256_file(scored_path)+"\n", encoding="utf-8")
            report_path = staging / "OMEGA_0.13_HOLDOUT_SCORE.json"
            report_path.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")

            m = overall["model"]; b = overall["benchmark"]
            mci = boot["maeImprovementCI95"]; rci = boot["rmseImprovementCI95"]
            cal = calibration["omega"]
            lines = [
                "# OMEGA Tackle Model 0.13 — One-Shot 2025 Holdout Score", "",
                f"Generated: {report['scoredAt']}", "",
                "**OMEGA 2025 TACKLE HOLDOUT IS NOW CONSUMED. DO NOT RETUNE OR RESCUE THE MODEL WITH THESE RESULTS.**", "",
                "Recovery note: 0.13 opened outcomes but aborted before metrics on an auxiliary zero-row scope mismatch. 0.13.1 corrected only that reconciliation guard; predictions, rows, benchmark, bootstrap, and verdict rules are unchanged.", "",
                "## Immutable contract", "",
                f"- Frozen spec SHA256: `{EXPECTED_FROZEN_SPEC_SHA256}`",
                f"- Blind prediction ledger SHA256: `{EXPECTED_BLIND_SHA256}`",
                f"- Exact 2025 PBP asset SHA256: `{EXPECTED_2025_PBP_SHA256}`",
                f"- Scored rows: **{len(rows)}** across **{EXPECTED_GAMES}** games / **18** weeks",
                "- Row universe changed after blind freeze: **NO**",
                "- Target snap magnitude read for scoring: **NO**",
                "- Market fields / OddsPapi / network requests: **0 / 0 / 0**",
                f"- Zero-credit scope reconciliation: **{zero_scope_audit['observedResolvedLedgerZeroCreditRows']} resolved-ledger rows = {zero_scope_audit['allSnapZeroCreditRows']} all-snap audit rows - {zero_scope_audit['unresolvedSnapExposureRows']} unresolved snap identities**", "",
                "## Primary count result", "",
                "| Model | MAE | RMSE | Mean prediction | Bias (pred-actual) |",
                "|---|---:|---:|---:|---:|",
                f"| frozen last-4 benchmark | {b['mae']:.5f} | {b['rmse']:.5f} | {b['predictedMean']:.5f} | {b['biasPredMinusActual']:+.5f} |",
                f"| **frozen OMEGA H008+H012** | **{m['mae']:.5f}** | **{m['rmse']:.5f}** | **{m['predictedMean']:.5f}** | **{m['biasPredMinusActual']:+.5f}** |", "",
                f"- Actual mean T+A: **{m['actualMean']:.5f}**",
                f"- MAE improvement (benchmark - OMEGA): **{overall['maeImprovement']:+.5f}**",
                f"- RMSE improvement (benchmark - OMEGA): **{overall['rmseImprovement']:+.5f}**",
                f"- Game-cluster bootstrap MAE improvement 95% CI: **[{mci[0]:+.5f}, {mci[1]:+.5f}]**",
                f"- Game-cluster bootstrap RMSE improvement 95% CI: **[{rci[0]:+.5f}, {rci[1]:+.5f}]**",
                f"- Bootstrap reps / seed: **{BOOTSTRAP_REPS} / {BOOTSTRAP_SEED}**", "",
                "## Calibration", "",
                f"- OMEGA intercept: **{cal['intercept']:+.5f}**" if cal['intercept'] is not None else "- OMEGA intercept: n/a",
                f"- OMEGA slope: **{cal['slope']:.5f}**" if cal['slope'] is not None else "- OMEGA slope: n/a",
                f"- OMEGA R²: **{cal['r2']:.5f}**" if cal['r2'] is not None else "- OMEGA R²: n/a", "",
                "## Precommitted verdict", "",
                f"# **{verdict}**", "",
                "STRONG_PASS requires both MAE and RMSE improvements and both paired game-cluster bootstrap 95% CI lower bounds > 0. DIRECTIONAL_PASS requires both point estimates to improve without that full bootstrap support. FAIL_BOTH means both worsen. Anything else is MIXED.", "",
                "## Fixed diagnostics", "",
                "Position and prior-history slices are written to the JSON report exactly as precommitted. They are descriptive only and may not be used to rescue, retune, or redefine the frozen 2025 verdict.", "",
                "## Participant-universe limitation", "",
                str(report["participantUniverseLimitation"]), "",
                "This remains a conditional historical count holdout, not proof of sportsbook edge or live VERIFIED prop Trust.", "",
            ]
            (staging / "OMEGA_0.13_HOLDOUT_SCORE.md").write_text("\n".join(lines), encoding="utf-8")

            files=[]
            for p in sorted(staging.iterdir()):
                if p.is_file():
                    files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
            (staging / "OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({
                "schemaVersion":SCHEMA,"sourceSnapshotId":EXPECTED_SID,"createdAt":now(),"files":files
            }, indent=2)+"\n", encoding="utf-8")
            os.replace(staging, out)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        consumed_obj = {
            "schemaVersion":SCHEMA,
            "status":"CONSUMED_FOREVER_FOR_OMEGA_TACKLE_TUNING",
            "consumedAt":now(),
            "sourceSnapshotId":EXPECTED_SID,
            "frozenSpecSha256":EXPECTED_FROZEN_SPEC_SHA256,
            "blindPredictionSha256":EXPECTED_BLIND_SHA256,
            "pbpAssetSha256":EXPECTED_2025_PBP_SHA256,
            "scoreReportSha256":sha256_file(out/"OMEGA_0.13_HOLDOUT_SCORE.json"),
            "scoredLedgerSha256":sha256_file(out/"OMEGA_2025_HOLDOUT_SCORED.csv"),
            "verdict":verdict,
            "rule":"DO_NOT_REUSE_OMEGA_2025_TO_SELECT_FEATURES_HYPERPARAMETERS_TRANSFORMS_SUBGROUPS_OR_MARKET_THRESHOLDS",
        }
        atomic_json(ctx["consumed"], consumed_obj)
        atomic_json(root / "data/models/nfl/OMEGA_TACKLE_2025_SCORING_RECOVERY_RESOLVED.json", {
            "schemaVersion":SCHEMA,
            "resolvedAt":now(),
            "status":"CONTROLLED_RESUME_COMPLETED",
            "originalAbortError":EXPECTED_ABORT_ERROR,
            "zeroCreditScopeReconciliation":zero_scope_audit,
            "verdict":verdict,
            "rule":"No model, benchmark, row-universe, bootstrap, subgroup, threshold, or verdict-rule changes were made after 2025 outcome access.",
        })
        (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_HOLDOUT_2025").write_text(EXPECTED_SID+"\n", encoding="utf-8")

        print("OMEGA 0.13.1 — CONTROLLED RESUME / 2025 TACKLE HOLDOUT")
        print("PASS controlled recovery of known 0.13 zero-row scope bug")
        print(f"PASS immutable blind ledger scored: {len(rows)} rows · {EXPECTED_GAMES} games")
        print(f"PASS OMEGA MAE {m['mae']:.5f} vs benchmark {b['mae']:.5f} · Δ {overall['maeImprovement']:+.5f}")
        print(f"PASS OMEGA RMSE {m['rmse']:.5f} vs benchmark {b['rmse']:.5f} · Δ {overall['rmseImprovement']:+.5f}")
        print(f"PASS MAE bootstrap 95% CI [{mci[0]:+.5f}, {mci[1]:+.5f}]")
        print(f"PASS RMSE bootstrap 95% CI [{rci[0]:+.5f}, {rci[1]:+.5f}]")
        print(f"VERDICT: {verdict}")
        print("OMEGA 2025 STATUS: CONSUMED FOREVER — NO RETUNING")
        print(f"REPORT: {out/'OMEGA_0.13_HOLDOUT_SCORE.md'}")
        return report
    except BaseException as e:
        abort = root / "data/models/nfl/OMEGA_TACKLE_2025_SCORING_RECOVERY_ABORTED.json"
        if not ctx["consumed"].exists():
            try:
                atomic_json(abort, {
                    "schemaVersion":SCHEMA,"abortedAt":now(),"errorType":type(e).__name__,
                    "error":str(e),"scoringStartedMarker":str(started),
                    "rule":"FAIL_CLOSED_DO_NOT_AUTOMATICALLY_RERUN_RECOVERY; preserve original 0.13 abort markers",
                })
            except Exception:
                pass
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--preflight-only", action="store_true", help="Verify immutable inputs without attaching/scoring outcomes")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    if args.preflight_only:
        validate_recovery_state(root)
        ctx = preflight(root, allow_started=True)
        print("OMEGA 0.13.1 CONTROLLED-RECOVERY PRE-FLIGHT — PASS")
        print(f"Frozen spec SHA256: {EXPECTED_FROZEN_SPEC_SHA256}")
        print(f"Blind ledger SHA256: {EXPECTED_BLIND_SHA256}")
        print(f"Blind rows/games/weeks: {EXPECTED_ROWS}/{EXPECTED_GAMES}/18")
        print(f"2025 PBP asset SHA256: {EXPECTED_2025_PBP_SHA256}")
        print("Recovery outcome re-attachment: NOT PERFORMED")
        print("Target snap magnitude read: NO")
        return 0
    score_once(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

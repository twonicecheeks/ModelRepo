#!/usr/bin/env python3
"""Build OMEGA 0.2.3 probabilistic snap-share challenger.

Research lineage only. Frozen OMEGA remains read-only.  The H012 point exposure
model is unchanged; this phase adds a strictly pre-2024 empirical conditional
residual distribution and evaluates probability calibration on 2024.  2025 remains
sealed and no market data are read.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, random, shutil, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_TACKLE_SNAP_SHARE_DISTRIBUTION_CHALLENGER_0.2.3"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 290023


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or ["status"], extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        if rows:
            w.writerows(rows)


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        x = float(v)
        return default if not math.isfinite(x) else x
    except (TypeError, ValueError):
        return default


def metrics(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    y = [num(r.get(actual)) for r in rows]
    p = [num(r.get(pred)) for r in rows]
    return {
        "n": len(rows),
        "actualMean": fmean(y),
        "predictedMean": fmean(p),
        "mae": fmean(abs(a-b) for a,b in zip(y,p)),
        "rmse": math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),
        "biasPredMinusActual": fmean(b-a for a,b in zip(y,p)),
    }


def percentile(xs: Sequence[float], p: float) -> float:
    z = sorted(float(x) for x in xs)
    if not z:
        return 0.0
    q = max(0.0, min(1.0, p)) * (len(z)-1)
    lo = int(math.floor(q)); hi = int(math.ceil(q))
    if lo == hi:
        return z[lo]
    w = q-lo
    return z[lo]*(1-w)+z[hi]*w


def game_cluster_bootstrap(rows: Sequence[dict[str, Any]], challenger: str, baseline: str) -> dict[str, Any]:
    by: dict[str, list[tuple[float,float]]] = defaultdict(list)
    for r in rows:
        gid = str(r.get("game_id") or "")
        if gid:
            by[gid].append((num(r.get(challenger)), num(r.get(baseline))))
    keys = sorted(by)
    if not keys:
        return {"clusters": 0}
    point = fmean(num(r.get(baseline))-num(r.get(challenger)) for r in rows)
    rng = random.Random(BOOTSTRAP_SEED); draws: list[float] = []
    for _ in range(BOOTSTRAP_REPS):
        dc = db = 0.0; n = 0
        for _j in range(len(keys)):
            vals = by[keys[rng.randrange(len(keys))]]
            for c,b in vals:
                dc += c; db += b; n += 1
        draws.append((db-dc)/n)
    return {
        "cluster": "game_id",
        "clusters": len(keys),
        "reps": BOOTSTRAP_REPS,
        "seed": BOOTSTRAP_SEED,
        "improvementPoint": point,
        "improvementCI95": [percentile(draws,.025), percentile(draws,.975)],
        "probabilityPositive": sum(x>0 for x in draws)/len(draws),
    }


def pit_deciles(rows: Sequence[dict[str, Any]], field: str) -> list[int]:
    bins = [0]*10
    for r in rows:
        x = max(0.0, min(1.0, num(r.get(field))))
        idx = min(9, int(x*10))
        bins[idx] += 1
    return bins


def interval_summary(rows: Sequence[dict[str, Any]], prefix: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for level in (50,80,90):
        out[f"coverage{level}"] = fmean(num(r.get(f"{prefix}_covered_{level}")) for r in rows)
        out[f"meanWidth{level}"] = fmean(num(r.get(f"{prefix}_width_{level}")) for r in rows)
    return out


def threshold_brier(rows: Sequence[dict[str, Any]], prefix: str) -> float:
    vals=[]
    for r in rows:
        for t in ("035","065","085"):
            vals.append(num(r.get(f"{prefix}_brier_ge_{t}")))
    return fmean(vals)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    omega = root/"packages/models/nfl/omega"
    sys.path.insert(0, str(omega))
    import exposure_role_challenger as er
    import snap_share_distribution_challenger as sd
    import xto_xtc_baseline as xb

    fptr = root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION"
    eptr = root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE"
    bptr = root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE"
    for p in (fptr,eptr,bptr):
        if not p.exists():
            raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    sid = fptr.read_text(encoding="utf-8").strip()
    if eptr.read_text(encoding="utf-8").strip()!=sid or bptr.read_text(encoding="utf-8").strip()!=sid:
        raise SystemExit("FAIL OMEGA source snapshot pointers disagree")

    foundation = root/"data/normalized/nfl/omega_tackle"/sid
    exposure = root/"data/normalized/nfl/omega_tackle_exposure"/sid
    base = root/"data/models/nfl/omega_tackle_02"/sid
    required = [
        foundation/"OMEGA_TACKLE_FOUNDATION_AUDIT.json",
        exposure/"OMEGA_TACKLE_EXPOSURE_AUDIT.json",
        exposure/"omega_tackle_exposure_player_games.csv",
        base/"OMEGA_0.2_AUDIT.json",
        base/"omega_2024_player_validation.csv",
    ]
    for p in required:
        if not p.exists():
            raise SystemExit(f"FAIL required source missing: {p}")
    fa = json.loads(required[0].read_text(encoding="utf-8"))
    ea = json.loads(required[1].read_text(encoding="utf-8"))
    ba = json.loads(required[3].read_text(encoding="utf-8"))
    if fa.get("omegaHoldoutPbpRowsRead") != 0 or ea.get("omegaHoldoutRowsRead") != 0 or ba.get("integrity",{}).get("omega2025RowsRead") != 0:
        raise SystemExit("FAIL OMEGA 2025 seal not clean")
    if any(x != 0 for x in [fa.get("marketFieldsRead",0), ea.get("marketFieldsRead",0), ba.get("integrity",{}).get("marketFieldsRead",0)]):
        raise SystemExit("FAIL market contamination")

    exposure_rows = read_csv(exposure/"omega_tackle_exposure_player_games.csv")
    if any(int(num(r.get("season")))==2025 for r in exposure_rows):
        raise SystemExit("FAIL 2025 exposure row read")
    team_snap_totals = xb.estimate_team_defensive_snaps(exposure_rows)
    preg = er.build_exposure_pregame_rows(exposure_rows, team_snap_totals)
    if any(int(r["season"])==2025 for r in preg):
        raise SystemExit("FAIL 2025 pregame row emitted")

    # Keep the exact H012 point-model selection protocol.  The distribution layer
    # sees only residuals generated from target-year rows whose coefficients were
    # fit on earlier seasons; all residual calibration years precede 2024.
    selected_l2, l2_search = er.choose_l2(preg)
    oof_rows: list[dict[str, Any]] = []
    h_obs=[]; b_obs=[]
    for year in sd.CALIBRATION_YEARS:
        train = [r for r in preg if 2017 <= int(r["season"]) < year]
        val = [r for r in preg if int(r["season"]) == year]
        if not train or not val:
            raise SystemExit(f"FAIL missing chronological calibration rows for {year}")
        model = er.fit_ridge(train, selected_l2)
        for r in val:
            h_center = model.predict(r)
            b_center = float(r["baseline_last4_snap_share"])
            ho = sd.make_observation(r, h_center); bo = sd.make_observation(r, b_center)
            h_obs.append(ho); b_obs.append(bo)
            oof_rows.append({
                "game_id": r["game_id"], "season": r["season"], "week": r["week"],
                "team": r["team"], "opponent": r["opponent"], "player_id": r["player_id"],
                "display_name": r.get("display_name",""), "position_group": r["position_group"],
                "prior_games": r["prior_games"], "actual_snap_share": r["actual_snap_share"],
                "h012_center": h_center, "h012_residual": ho.residual,
                "last4_center": b_center, "last4_residual": bo.residual,
            })

    hcal = sd.EmpiricalResidualCalibrator(h_obs, min_pool=sd.MIN_POOL)
    bcal = sd.EmpiricalResidualCalibrator(b_obs, min_pool=sd.MIN_POOL)

    fit = [r for r in preg if 2017 <= int(r["season"]) <= 2023]
    val2024 = [r for r in preg if int(r["season"]) == 2024]
    if not fit or not val2024:
        raise SystemExit("FAIL missing 2017-2023 fit or 2024 validation rows")
    final_model = er.fit_ridge(fit, selected_l2)

    baseline_val = read_csv(base/"omega_2024_player_validation.csv")
    bmap = {(r.get("game_id"),r.get("team"),r.get("player_id")):r for r in baseline_val}
    vmap = {(r.get("game_id"),r.get("team"),r.get("player_id")):r for r in val2024}
    if len(bmap)!=len(baseline_val) or set(bmap)!=set(vmap):
        raise SystemExit(f"FAIL 2024 validation identity mismatch baseline={len(bmap)} exposure={len(vmap)}")

    scored: list[dict[str, Any]] = []
    for key, b in bmap.items():
        r = vmap[key]
        actual = float(r["actual_snap_share"])
        hc = final_model.predict(r)
        bc = float(r["baseline_last4_snap_share"])
        hd = hcal.summarize(r, hc, actual)
        bd = bcal.summarize(r, bc, actual)
        x = dict(b)
        x.update({
            "h012_point_snap_share": hc,
            "last4_point_snap_share": bc,
            "actual_snap_share_distribution_target": actual,
            "prior_games_distribution": r["prior_games"],
            "history_band_distribution": sd.history_band(int(r["prior_games"])),
            "h012_role_tier": sd.role_tier(hc),
            "last4_role_tier": sd.role_tier(bc),
        })
        for k,v in hd.items(): x[f"dist_{k}"] = v
        for k,v in bd.items(): x[f"baseline_dist_{k}"] = v

        # Exposure-only propagation through the frozen 0.2 team-snap and tackle-rate
        # components. This is not a new tackle model; it diagnoses whether the
        # distribution's location would improve downstream xTC.
        team_snaps = num(b.get("predicted_team_defensive_snaps"))
        rate = num(b.get("shrunk_credit_rate_per_snap"))
        x["h012_point_xtc"] = hc * team_snaps * rate
        x["dist_mean_xtc"] = num(hd.get("distribution_mean")) * team_snaps * rate
        x["dist_median_xtc"] = num(hd.get("distribution_median")) * team_snaps * rate
        x["baseline_dist_mean_xtc"] = num(bd.get("distribution_mean")) * team_snaps * rate
        scored.append(x)

    point_h = metrics(scored,"actual_snap_share_distribution_target","h012_point_snap_share")
    point_b = metrics(scored,"actual_snap_share_distribution_target","last4_point_snap_share")
    mean_h = metrics(scored,"actual_snap_share_distribution_target","dist_distribution_mean")
    mean_b = metrics(scored,"actual_snap_share_distribution_target","baseline_dist_distribution_mean")
    xtc_point = metrics(scored,"actual_xtc","h012_point_xtc")
    xtc_dist = metrics(scored,"actual_xtc","dist_mean_xtc")
    xtc_base_dist = metrics(scored,"actual_xtc","baseline_dist_mean_xtc")
    crps_h = fmean(num(r.get("dist_crps")) for r in scored)
    crps_b = fmean(num(r.get("baseline_dist_crps")) for r in scored)
    brier_h = threshold_brier(scored,"dist")
    brier_b = threshold_brier(scored,"baseline_dist")
    boot = game_cluster_bootstrap(scored,"dist_crps","baseline_dist_crps")
    interval_h = interval_summary(scored,"dist")
    interval_b = interval_summary(scored,"baseline_dist")

    pool_usage_h = Counter(str(r.get("dist_pool_key")) for r in scored)
    pool_usage_b = Counter(str(r.get("baseline_dist_pool_key")) for r in scored)
    report = {
        "schemaVersion": SCHEMA,
        "version": sd.VERSION,
        "lineage": sd.LINEAGE,
        "generatedAt": now(),
        "sourceSnapshotId": sid,
        "targetDefinition": "defensive snap share conditional on recording at least one defensive snap; availability/inactive probability is separate",
        "integrity": {
            "omega2025RowsRead": 0,
            "marketFieldsRead": 0,
            "oddsPapiRequests": 0,
            "frozenOmegaModified": False,
            "tackleRateChanged": False,
            "teamSnapModelChanged": False,
            "2024UsedForDistributionTuning": False,
        },
        "chronology": {
            "pointModelL2SelectionFolds": [2021,2022,2023],
            "distributionCalibrationYears": list(sd.CALIBRATION_YEARS),
            "calibrationPredictionRule": "each target year point prediction fit on 2017 through prior year; selected H012 L2 is fixed pre-2024",
            "finalPointFitYears": list(range(2017,2024)),
            "diagnosticDirectedConfirmation": 2024,
            "sealedHoldout": 2025,
        },
        "distribution": {
            "family": "CONDITIONAL_EMPIRICAL_RESIDUAL",
            "minPool": sd.MIN_POOL,
            "contextHierarchy": ["position+history+role","position+role","history+role","role","position","global"],
            "roleThresholds": list(sd.ROLE_THRESHOLDS),
            "residualRows": len(oof_rows),
            "h012PoolCount": len(hcal.pools),
            "baselinePoolCount": len(bcal.pools),
        },
        "validation2024": {
            "rows": len(scored),
            "pointSnapShare": {
                "h012": point_h, "last4": point_b,
                "maeImprovement": point_b["mae"]-point_h["mae"],
            },
            "distributionLocationSnapShare": {
                "h012EmpiricalMean": mean_h, "last4EmpiricalMean": mean_b,
                "maeImprovement": mean_b["mae"]-mean_h["mae"],
            },
            "crps": {
                "h012": crps_h, "last4": crps_b, "improvement": crps_b-crps_h,
                "gameClusterBootstrap": boot,
            },
            "roleThresholdBrier": {"h012": brier_h,"last4": brier_b,"improvement": brier_b-brier_h},
            "intervalCalibration": {"h012": interval_h,"last4": interval_b},
            "pitDeciles": {"h012": pit_deciles(scored,"dist_pit"),"last4":pit_deciles(scored,"baseline_dist_pit")},
            "poolUsage": {"h012": dict(pool_usage_h),"last4":dict(pool_usage_b)},
            "downstreamExposureOnlyXTC": {
                "h012Point": xtc_point,
                "h012DistributionMean": xtc_dist,
                "last4DistributionMean": xtc_base_dist,
            },
        },
    }
    ci = boot.get("improvementCI95", [0,0])
    if crps_b-crps_h > 0 and brier_b-brier_h > 0 and ci[0] > 0:
        verdict = "H012D_DISTRIBUTION_STRONG_DIRECTIONAL_PASS"
    elif crps_b-crps_h > 0 and brier_b-brier_h > 0:
        verdict = "H012D_DISTRIBUTION_DIRECTIONAL_PASS"
    elif crps_b-crps_h <= 0 and brier_b-brier_h <= 0:
        verdict = "H012D_DISTRIBUTION_FAIL"
    else:
        verdict = "H012D_DISTRIBUTION_MIXED"
    report["verdict"] = verdict
    report["interpretation"] = "2024 is diagnostic-directed confirmation, not a pristine holdout. A positive result justifies prospective distribution testing and current-role feature work; it does not modify frozen OMEGA or consume the sealed 2025 holdout."
    report["nextGate"] = "Add current depth-chart/role evidence as a separate location-state challenger, then prospectively freeze snap-share distributions before 2026 markets. Keep availability probability separate."

    outbase = root/"data/models/nfl/omega_tackle_023_snap_distribution"
    out = outbase/sid
    if out.exists():
        raise SystemExit(f"Refusing overwrite immutable OMEGA 0.2.3 output: {out}")
    staging = outbase/("."+sid+".staging")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        write_csv(staging/"omega_snap_share_distribution_calibration_oof.csv", oof_rows)
        write_csv(staging/"omega_2024_snap_share_distribution_validation.csv", scored)
        write_csv(staging/"omega_h012_distribution_pool_summary.csv", hcal.pool_summary())
        write_csv(staging/"omega_last4_distribution_pool_summary.csv", bcal.pool_summary())
        model_meta = {
            "schemaVersion": SCHEMA,
            "version": sd.VERSION,
            "lineage": sd.LINEAGE,
            "selectedH012L2": selected_l2,
            "h012L2Search": l2_search,
            "calibrationYears": list(sd.CALIBRATION_YEARS),
            "minPool": sd.MIN_POOL,
            "roleThresholds": list(sd.ROLE_THRESHOLDS),
            "featureNames": list(er.FEATURE_NAMES),
            "pointModel": final_model.to_dict(),
            "residualCalibrationFile": "omega_snap_share_distribution_calibration_oof.csv",
            "conditionalTarget": report["targetDefinition"],
        }
        (staging/"omega_snap_share_distribution_model.json").write_text(json.dumps(model_meta,indent=2)+"\n",encoding="utf-8")
        rp = staging/"OMEGA_0.2.3_SNAP_SHARE_DISTRIBUTION_AUDIT.json"
        rp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        lines = [
            "# OMEGA 0.2.3 — Snap-Share Distribution Challenger","",
            "**RESEARCH CHALLENGER ONLY. FROZEN OMEGA UNCHANGED. 2025 SEALED. MARKET DATA 0.**","",
            f"Source snapshot: `{sid}`", f"Generated: {report['generatedAt']}","",
            "## Target","", report["targetDefinition"],"",
            "## Method","",
            "- Keep H012 point exposure architecture unchanged.",
            "- Generate strictly pre-2024 residuals from chronological target-year predictions.",
            "- Condition empirical residual pools on position group, history depth and predicted role tier.",
            f"- Minimum conditional pool: **{sd.MIN_POOL}** observations; hierarchical fallback to global.",
            "- No Normal/Beta shape assumption; clipping preserves the physical [0,1] snap-share support.","",
            "## 2024 diagnostic confirmation","",
            f"- H012 point snap-share MAE: **{point_h['mae']:.5f}** vs last-4 **{point_b['mae']:.5f}**",
            f"- Distribution CRPS: H012 **{crps_h:.5f}** vs last-4 **{crps_b:.5f}** · improvement **{crps_b-crps_h:+.5f}**",
            f"- Role-threshold Brier: H012 **{brier_h:.5f}** vs last-4 **{brier_b:.5f}** · improvement **{brier_b-brier_h:+.5f}**",
            f"- CRPS game-cluster bootstrap 95% CI: **[{ci[0]:+.5f}, {ci[1]:+.5f}]** · P(improvement>0) **{boot.get('probabilityPositive',0):.3f}**",
            f"- H012 50/80/90 interval coverage: **{interval_h['coverage50']:.1%} / {interval_h['coverage80']:.1%} / {interval_h['coverage90']:.1%}**",
            f"- Exposure-only xTC MAE from distribution mean: **{xtc_dist['mae']:.4f}** (H012 point **{xtc_point['mae']:.4f}**)","",
            "## Verdict","",f"**{verdict}**","",
            report["interpretation"],"",
            "## Next gate","",report["nextGate"],"",
        ]
        (staging/"OMEGA_0.2.3_SNAP_SHARE_DISTRIBUTION_AUDIT.md").write_text("\n".join(lines),encoding="utf-8")
        files=[]
        for p in sorted(staging.iterdir()):
            if p.is_file(): files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
        (staging/"OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"createdAt":now(),"files":files},indent=2)+"\n",encoding="utf-8")
        os.replace(staging,out)
        ptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_SNAP_DISTRIBUTION_CHALLENGER"
        tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(sid+"\n",encoding="utf-8"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise

    print("OMEGA 0.2.3 — SNAP-SHARE DISTRIBUTION CHALLENGER")
    print(f"PASS source snapshot {sid} · 2025 rows read 0 · market fields 0")
    print(f"PASS OOF residual calibration rows {len(oof_rows)} · years {sd.CALIBRATION_YEARS}")
    print(f"2024 H012 point snap MAE {point_h['mae']:.5f} vs last4 {point_b['mae']:.5f}")
    print(f"2024 CRPS H012 {crps_h:.5f} vs last4 {crps_b:.5f} · improvement {crps_b-crps_h:+.5f}")
    print(f"2024 threshold Brier H012 {brier_h:.5f} vs last4 {brier_b:.5f} · improvement {brier_b-brier_h:+.5f}")
    print(f"CRPS game-cluster bootstrap 95% CI {boot.get('improvementCI95')}")
    print(f"VERDICT: {verdict}")
    print("PASS frozen OMEGA writes 0 · tackle rate unchanged · team snap model unchanged")
    print(f"REPORT: {out/'OMEGA_0.2.3_SNAP_SHARE_DISTRIBUTION_AUDIT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

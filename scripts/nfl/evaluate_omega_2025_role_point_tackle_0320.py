#!/usr/bin/env python3
"""OMEGA 0.32 — fixed-mechanism 2025 role-point -> T+A propagation diagnostic.

POST-HOLDOUT DIAGNOSTIC ONLY. 2025 outcomes have already been consumed. This script
must not be interpreted as a new sealed holdout or used to retune the role model.

Question isolated here:
    If the already-frozen OMEGA 0.31 current-role snap-share point is substituted
    for H012, while xTO, play-family shares, shrunk tackle rates, participant
    universe, and every other OMEGA component remain unchanged, does mean T+A error
    improve relative to the immutable 0.12 blind forecast?

The blind 0.12 count construction is exactly linear in snap share:
    xTC = snap_share * sum_f(predicted_xTO * pred_share_f * shrunk_rate_f)
So the challenger is deterministic and involves zero fitting/tuning.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Callable, Sequence
import argparse
import csv
import hashlib
import json
import math
import os
import random
import shutil

SCHEMA = "OMEGA_2025_ROLE_POINT_TACKLE_PROPAGATION_DIAGNOSTIC_0.32.0"
VERSION = "0.32.0"
SID = "20260910T205221Z_58d8156a"
ROLE_ARTIFACT = "20260910T205221Z_58d8156a__20260914T222159Z_8f6be75b"
BLIND_SHA = "59c1a1726bb705661babe3f51fc408e389a25bece6a18df0fdf79065b08d036e"
EXPECTED_ROWS = 10524
EXPECTED_GAMES = 272
FAMILIES = ("RUSH", "COMPLETE_PASS", "SCRAMBLE", "SACK", "OTHER_PASS")
BOOTSTRAP_REPS = 10000
BOOTSTRAP_SEED = 320032


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def rcsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def wcsv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or ["status"], extrasaction="ignore", lineterminator="\n")
        w.writeheader(); w.writerows(rows)


def num(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"non-numeric value: {v!r}")
    if not math.isfinite(x):
        raise ValueError(f"non-finite value: {v!r}")
    return x


def percentile(xs: Sequence[float], q: float) -> float:
    z = sorted(float(x) for x in xs)
    if not z:
        raise ValueError("percentile on empty sequence")
    p = max(0.0, min(1.0, q)) * (len(z) - 1)
    lo, hi = int(math.floor(p)), int(math.ceil(p))
    if lo == hi:
        return z[lo]
    w = p - lo
    return z[lo] * (1.0 - w) + z[hi] * w


def metrics(rows: Sequence[dict[str, Any]], pred: str) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    ys = [num(r["actual_xtc"]) for r in rows]
    ps = [max(0.0, num(r[pred])) for r in rows]
    return {
        "n": len(rows),
        "actualMean": fmean(ys),
        "predictedMean": fmean(ps),
        "mae": fmean(abs(y-p) for y,p in zip(ys,ps)),
        "rmse": math.sqrt(fmean((y-p)**2 for y,p in zip(ys,ps))),
        "biasPredMinusActual": fmean(p-y for y,p in zip(ys,ps)),
    }


def compare(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    h = metrics(rows, "h012_xtc")
    r = metrics(rows, "role_point_xtc")
    return {
        "n": len(rows),
        "h012": h,
        "rolePoint": r,
        "maeImprovement": float(h["mae"]) - float(r["mae"]),
        "rmseImprovement": float(h["rmse"]) - float(r["rmse"]),
        "biasChangeRoleMinusH012": float(r["biasPredMinusActual"]) - float(h["biasPredMinusActual"]),
    }


def cluster_bootstrap(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by: dict[str, list[tuple[float,float,float]]] = defaultdict(list)
    for r in rows:
        by[str(r["game_id"])].append((num(r["actual_xtc"]), num(r["h012_xtc"]), num(r["role_point_xtc"])))
    keys = sorted(by)
    rng = random.Random(BOOTSTRAP_SEED)
    mae_draws: list[float] = []; rmse_draws: list[float] = []
    for _ in range(BOOTSTRAP_REPS):
        ae_h = ae_r = se_h = se_r = 0.0; n = 0
        for _j in range(len(keys)):
            g = keys[rng.randrange(len(keys))]
            for y,h,r in by[g]:
                ae_h += abs(y-h); ae_r += abs(y-r)
                se_h += (y-h)**2; se_r += (y-r)**2; n += 1
        mae_draws.append((ae_h-ae_r)/n)
        rmse_draws.append(math.sqrt(se_h/n)-math.sqrt(se_r/n))
    point = compare(rows)
    return {
        "cluster": "game_id", "clusters": len(keys), "reps": BOOTSTRAP_REPS, "seed": BOOTSTRAP_SEED,
        "maeImprovementPoint": point["maeImprovement"],
        "maeImprovementCI95": [percentile(mae_draws,.025), percentile(mae_draws,.975)],
        "maeProbabilityPositive": sum(x>0 for x in mae_draws)/len(mae_draws),
        "rmseImprovementPoint": point["rmseImprovement"],
        "rmseImprovementCI95": [percentile(rmse_draws,.025), percentile(rmse_draws,.975)],
        "rmseProbabilityPositive": sum(x>0 for x in rmse_draws)/len(rmse_draws),
    }


def subgroup_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    defs: dict[str, Callable[[dict[str, Any]], bool]] = {
        "depthCovered": lambda r: int(r["depth_present"]) == 1,
        "week2PreferredExposureUniverse": lambda r: int(r["depth_present"]) == 1 and not bool(r["backup_conflict"]),
        "rank1": lambda r: int(r["depth_rank"]) == 1,
        "rank2": lambda r: int(r["depth_rank"]) == 2,
        "rank3plus": lambda r: int(r["depth_rank"]) >= 3,
        "starterConflict": lambda r: bool(r["starter_conflict"]),
        "backupConflict": lambda r: bool(r["backup_conflict"]),
        "promotedToRank1": lambda r: int(r["promoted_to_rank1"]) == 1,
        "demotedFromRank1": lambda r: int(r["demoted_from_rank1"]) == 1,
        "week1": lambda r: int(r["week"]) == 1,
        "week1Rank1": lambda r: int(r["week"]) == 1 and int(r["depth_rank"]) == 1,
        "coldStartRank1": lambda r: int(r["prior_games"]) == 0 and int(r["depth_rank"]) == 1,
        "largeRoleDisagreement": lambda r: abs(num(r["role_correction"])) >= .15,
        "positionDB": lambda r: str(r["position_group"]).upper() == "DB",
        "positionLB": lambda r: str(r["position_group"]).upper() == "LB",
        "positionDL": lambda r: str(r["position_group"]).upper() == "DL",
    }
    return {name: compare([r for r in rows if fn(r)]) for name,fn in defs.items()}


def load_valid_role_result(root: Path) -> tuple[Path, list[dict[str,str]], dict[str,Any]]:
    ptr = root / "data/results/nfl/omega/CURRENT_OMEGA_2025_CURRENT_ROLE_CONFIRMATORY"
    if not ptr.exists():
        raise SystemExit("FAIL current valid OMEGA 0.31 role result pointer missing")
    d = root / ptr.read_text(encoding="utf-8").strip()
    rp = d / "OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_REPORT.json"
    sp = d / "OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_SCORED.csv"
    hp = d / "OMEGA_0.31_OUTPUT_HASHES.json"
    for p in (rp,sp,hp):
        if not p.exists(): raise SystemExit(f"FAIL 0.31 artifact missing: {p}")
    hashes = json.loads(hp.read_text(encoding="utf-8"))
    if hashes.get(rp.name) != sha256_file(rp) or hashes.get(sp.name) != sha256_file(sp):
        raise SystemExit("FAIL 0.31 output hash mismatch")
    report = json.loads(rp.read_text(encoding="utf-8"))
    if report.get("verdict") != "STRONG_CONFIRM":
        raise SystemExit(f"FAIL current 0.31 role result not STRONG_CONFIRM: {report.get('verdict')}")
    cov = float(report.get("coverage",{}).get("depthCoverage") or 0.0)
    if cov < .80:
        raise SystemExit(f"FAIL current 0.31 depth coverage too low: {cov:.1%}")
    rows = rcsv(sp)
    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"FAIL 0.31 row count drift {len(rows)} != {EXPECTED_ROWS}")
    return d, rows, report


def load_scored_tackle_holdout(root: Path) -> tuple[Path, list[dict[str,str]], dict[str,Any]]:
    ptr = root / "data/models/nfl/CURRENT_OMEGA_TACKLE_HOLDOUT_2025"
    if not ptr.exists() or ptr.read_text(encoding="utf-8").strip() != SID:
        raise SystemExit("FAIL OMEGA 0.13 holdout pointer missing/drifted")
    d = root / "data/models/nfl/omega_tackle_013_holdout_2025" / SID
    sp = d / "OMEGA_2025_HOLDOUT_SCORED.csv"
    rp = d / "OMEGA_0.13_HOLDOUT_SCORE.json"
    consumed = root / "data/models/nfl/OMEGA_TACKLE_2025_CONSUMED.json"
    for p in (sp,rp,consumed):
        if not p.exists(): raise SystemExit(f"FAIL OMEGA 0.13 artifact missing: {p}")
    cj = json.loads(consumed.read_text(encoding="utf-8"))
    if cj.get("blindPredictionSha256") != BLIND_SHA:
        raise SystemExit("FAIL OMEGA 0.13 consumed marker blind SHA drift")
    if cj.get("scoredLedgerSha256") != sha256_file(sp) or cj.get("scoreReportSha256") != sha256_file(rp):
        raise SystemExit("FAIL OMEGA 0.13 consumed marker output hash mismatch")
    rows = rcsv(sp)
    if len(rows) != EXPECTED_ROWS or len({r["game_id"] for r in rows}) != EXPECTED_GAMES:
        raise SystemExit("FAIL OMEGA 0.13 scored holdout coverage drift")
    return d, rows, json.loads(rp.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args(); root = Path(args.root).expanduser().resolve()

    role_dir, role_rows, role_report = load_valid_role_result(root)
    tackle_dir, tackle_rows, tackle_report = load_scored_tackle_holdout(root)

    rmap = {(r["game_id"],r["player_id"]):r for r in role_rows}
    tmap = {(r["game_id"],r["player_id"]):r for r in tackle_rows}
    if set(rmap) != set(tmap):
        only_r = list(sorted(set(rmap)-set(tmap)))[:3]; only_t = list(sorted(set(tmap)-set(rmap)))[:3]
        raise SystemExit(f"FAIL role/tackle row-universe mismatch role-only={only_r} tackle-only={only_t}")

    scored: list[dict[str,Any]] = []
    max_baseline_reconstruction_drift = 0.0
    snap_parity_drifts = 0
    for key in sorted(tmap):
        t = tmap[key]; r = rmap[key]
        hss = num(t["predicted_snap_share"]); role_ss = num(r["role_snap_share"])
        if abs(hss - num(r["h012_snap_share"])) > 1e-10:
            snap_parity_drifts += 1
        xto = num(t["predicted_xto"])
        per_unit = 0.0
        for f in FAMILIES:
            per_unit += xto * num(t[f"pred_share_{f}"]) * num(t[f"shrunk_rate_{f}"])
        reconstructed = hss * per_unit
        base_xtc = num(t["predicted_xtc"])
        drift = abs(reconstructed - base_xtc)
        max_baseline_reconstruction_drift = max(max_baseline_reconstruction_drift, drift)
        if drift > 1e-8:
            raise SystemExit(f"FAIL exact blind T+A reconstruction drift {key}: {drift:.3g}")
        role_xtc = max(0.0, role_ss * per_unit)
        rank = int(float(r.get("depth_rank") or 0)); starter_conflict = rank == 1 and hss < .65
        backup_conflict = rank >= 2 and hss >= .65
        scored.append({
            "game_id":t["game_id"], "season":2025, "week":int(t["week"]), "team":t["team"], "opponent":t["opponent"],
            "player_id":t["player_id"], "player_name":t.get("display_name",r.get("player_name","")), "position":t.get("position",""), "position_group":t.get("position_group",""),
            "prior_games":int(t["prior_games"]), "depth_present":int(float(r.get("depth_present") or 0)), "depth_rank":rank,
            "depth_position":r.get("depth_position",""), "prev_depth_rank":int(float(r.get("prev_depth_rank") or 0)),
            "promoted_to_rank1":int(float(r.get("promoted_to_rank1") or 0)), "demoted_from_rank1":int(float(r.get("demoted_from_rank1") or 0)),
            "starter_conflict":starter_conflict, "backup_conflict":backup_conflict,
            "h012_snap_share":hss, "role_snap_share":role_ss, "role_correction":role_ss-hss,
            "actual_snap_share":num(r["actual_snap_share"]),
            "tackle_credit_per_unit_snap_share":per_unit,
            "actual_xtc":num(t["actual_xtc"]), "h012_xtc":base_xtc, "role_point_xtc":role_xtc,
            "h012_xtc_abs_error":abs(num(t["actual_xtc"])-base_xtc), "role_point_xtc_abs_error":abs(num(t["actual_xtc"])-role_xtc),
            "xtc_change_role_minus_h012":role_xtc-base_xtc,
        })
    if snap_parity_drifts:
        raise SystemExit(f"FAIL H012 snap parity drift rows: {snap_parity_drifts}")

    overall = compare(scored); boot = cluster_bootstrap(scored); subs = subgroup_report(scored)
    depth_cov = sum(int(r["depth_present"]) for r in scored)/len(scored)
    changed = [r for r in scored if abs(num(r["role_correction"])) > 1e-12]
    operational = [r for r in scored if int(r["depth_present"]) == 1 and not bool(r["backup_conflict"])]
    op_boot = cluster_bootstrap(operational)

    # Descriptive only: no promotion verdict is defined after seeing 2025.
    direction = "IMPROVED" if overall["maeImprovement"] > 0 and overall["rmseImprovement"] > 0 else ("WORSENED" if overall["maeImprovement"] < 0 and overall["rmseImprovement"] < 0 else "MIXED")
    report = {
        "schemaVersion":SCHEMA, "version":VERSION, "generatedAt":now(),
        "scientificStatus":"POST_HOLDOUT_FIXED_MECHANISM_DIAGNOSTIC_NOT_A_NEW_SEALED_HOLDOUT",
        "question":"Does substituting the already-frozen 0.31 role-point snap share into the otherwise frozen 0.12 T+A mean calculation improve realized T+A error?",
        "mechanism":"role_point_xtc = role_snap_share * sum_f(predicted_xto * frozen_family_share_f * frozen_shrunk_rate_f)",
        "directionalResult":direction,
        "integrity":{
            "modelRefits":0,"hyperparameterSearches":0,"marketFieldsRead":0,"oddsPapiRequests":0,"networkRequests":0,"frozenOmegaWrites":0,
            "probabilityDistributionChanged":False,"participantUniverseChanged":False,"tackleRatesChanged":False,"xTOChanged":False,"familySharesChanged":False,
            "blindTackleBaselineReconstructionMaxAbsDrift":max_baseline_reconstruction_drift,"h012SnapParityDriftRows":snap_parity_drifts,
        },
        "sources":{
            "blindPredictionSha256":BLIND_SHA,"sourceSnapshotId":SID,"roleArtifactId":ROLE_ARTIFACT,
            "roleResultDir":str(role_dir.relative_to(root)),"roleScoredSha256":sha256_file(role_dir/"OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_SCORED.csv"),
            "tackleHoldoutDir":str(tackle_dir.relative_to(root)),"tackleScoredSha256":sha256_file(tackle_dir/"OMEGA_2025_HOLDOUT_SCORED.csv"),
            "roleHoldoutVerdict":role_report.get("verdict"),"originalTackleHoldoutVerdict":tackle_report.get("precommittedVerdict"),
        },
        "coverage":{"rows":len(scored),"games":len({r["game_id"] for r in scored}),"depthCoverage":depth_cov,"roleChangedRows":len(changed),"week2PreferredExposureUniverseRows":len(operational)},
        "overall":overall,"pairedGameClusterBootstrap":boot,
        "week2PreferredExposureUniverse":compare(operational),"week2PreferredExposureUniverseBootstrap":op_boot,
        "subgroups":subs,
        "interpretationRule":"Descriptive fixed-mechanism evidence only. Do not refit/tune on 2025. Week 2 frozen OMEGA remains control; current-role point remains challenger; full snap mixture remains research-only.",
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runid = f"{stamp}_{BLIND_SHA[:8]}"
    base = root/"data/results/nfl/omega_2025_role_point_tackle_0320"/ROLE_ARTIFACT
    final = base/runid; staging = base/("."+runid+".staging")
    if final.exists() or staging.exists(): raise SystemExit("FAIL duplicate OMEGA 0.32 run id")
    staging.mkdir(parents=True,exist_ok=False)
    try:
        sp=staging/"OMEGA_0.32_2025_ROLE_POINT_TACKLE_SCORED.csv"; wcsv(sp,scored)
        jp=staging/"OMEGA_0.32_2025_ROLE_POINT_TACKLE_REPORT.json"; jp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        o=overall; op=report["week2PreferredExposureUniverse"]
        lines=[
            "# OMEGA 0.32 — 2025 Role-Point → T+A Fixed-Mechanism Diagnostic","",
            "**POST-HOLDOUT DIAGNOSTIC ONLY · NO REFITS · NO TUNING · NO MARKET DATA**","",
            f"Generated: `{report['generatedAt']}`  ",f"Directional result: **{direction}**","",
            "## Overall 2025 conditional-player universe","",
            f"- Rows **{o['n']}** · games **{EXPECTED_GAMES}** · depth coverage **{depth_cov:.1%}**",
            f"- H012 T+A MAE **{o['h012']['mae']:.5f}** → role-point **{o['rolePoint']['mae']:.5f}** · improvement **{o['maeImprovement']:+.5f}**",
            f"- H012 T+A RMSE **{o['h012']['rmse']:.5f}** → role-point **{o['rolePoint']['rmse']:.5f}** · improvement **{o['rmseImprovement']:+.5f}**",
            f"- Bias H012 **{o['h012']['biasPredMinusActual']:+.5f}** → role-point **{o['rolePoint']['biasPredMinusActual']:+.5f}**",
            f"- MAE game-cluster bootstrap 95% CI **[{boot['maeImprovementCI95'][0]:+.5f}, {boot['maeImprovementCI95'][1]:+.5f}]** · P(positive) **{boot['maeProbabilityPositive']:.3f}**",
            f"- RMSE game-cluster bootstrap 95% CI **[{boot['rmseImprovementCI95'][0]:+.5f}, {boot['rmseImprovementCI95'][1]:+.5f}]** · P(positive) **{boot['rmseProbabilityPositive']:.3f}**","",
            "## Week 2 preferred exposure universe","",
            "Depth-covered rows excluding backup conflicts; this mirrors the already-frozen Week 2 operating policy.","",
            f"- Rows **{op['n']}**",
            f"- T+A MAE **{op['h012']['mae']:.5f}** → **{op['rolePoint']['mae']:.5f}** · improvement **{op['maeImprovement']:+.5f}**",
            f"- T+A RMSE **{op['h012']['rmse']:.5f}** → **{op['rolePoint']['rmse']:.5f}** · improvement **{op['rmseImprovement']:+.5f}**","",
            "## Important restriction","",
            "This result does not promote the full snap-share distribution and does not overwrite frozen OMEGA. It tests only the deterministic point substitution. 2025 is already consumed, so the result is diagnostic rather than a new model-selection holdout.","",
        ]
        (staging/"OMEGA_0.32_2025_ROLE_POINT_TACKLE_REPORT.md").write_text("\n".join(lines),encoding="utf-8")
        hashes={p.name:sha256_file(p) for p in staging.iterdir() if p.is_file()}
        (staging/"OMEGA_0.32_OUTPUT_HASHES.json").write_text(json.dumps(hashes,indent=2)+"\n",encoding="utf-8")
        os.replace(staging,final)
        ptr=root/"data/results/nfl/omega/CURRENT_OMEGA_2025_ROLE_POINT_TACKLE_DIAGNOSTIC"; ptr.parent.mkdir(parents=True,exist_ok=True)
        tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(str(final.relative_to(root))+"\n",encoding="utf-8"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

    print("OMEGA 0.32 — 2025 ROLE-POINT -> T+A FIXED-MECHANISM DIAGNOSTIC")
    print(f"PASS rows {len(scored)} · games {EXPECTED_GAMES} · depth coverage {depth_cov:.1%} · role-changed rows {len(changed)}")
    print(f"ALL: H012 MAE {overall['h012']['mae']:.5f} -> ROLE {overall['rolePoint']['mae']:.5f} · improvement {overall['maeImprovement']:+.5f}")
    print(f"ALL: H012 RMSE {overall['h012']['rmse']:.5f} -> ROLE {overall['rolePoint']['rmse']:.5f} · improvement {overall['rmseImprovement']:+.5f}")
    print(f"ALL: MAE bootstrap 95% CI [{boot['maeImprovementCI95'][0]:+.5f}, {boot['maeImprovementCI95'][1]:+.5f}] · P+ {boot['maeProbabilityPositive']:.3f}")
    print(f"W2 ELIGIBLE n {op['n']}: MAE {op['h012']['mae']:.5f}->{op['rolePoint']['mae']:.5f} {op['maeImprovement']:+.5f} · RMSE {op['h012']['rmse']:.5f}->{op['rolePoint']['rmse']:.5f} {op['rmseImprovement']:+.5f}")
    for name in ("starterConflict","backupConflict","promotedToRank1","demotedFromRank1","week1Rank1","coldStartRank1","largeRoleDisagreement"):
        s=subs[name]
        if s.get("n",0): print(f"{name}: n {s['n']} · MAE {s['h012']['mae']:.4f}->{s['rolePoint']['mae']:.4f} · improvement {s['maeImprovement']:+.4f}")
    print(f"DIRECTIONAL RESULT: {direction} (diagnostic only; not a new sealed holdout)")
    print("PASS refits 0 · market fields 0 · OddsPapi 0 · probability layer changed NO · frozen OMEGA writes 0")
    print(f"REPORT: {final/'OMEGA_0.32_2025_ROLE_POINT_TACKLE_REPORT.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""OMEGA 0.2.1 validation diagnostics and failure-slice audit.

This phase does not fit or modify a model. It reads only the already-produced
OMEGA 0.2 2024 validation outputs, computes diagnostic slices/paired cluster
bootstrap uncertainty, and preserves the OMEGA 2025 holdout seal.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Sequence

SCHEMA = "OMEGA_TACKLE_VALIDATION_DIAGNOSTICS_0.2.1"
VERSION = "0.2.1"
LINEAGE = "omega-tackle-v0.2.1-validation-diagnostics-2026-09-11"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 290021


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


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for k in row:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: "" if row.get(k) is None else row.get(k) for k in fields})


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        x = float(v)
        return default if math.isnan(x) else x
    except (TypeError, ValueError):
        return default


def metrics(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> dict[str, float | int]:
    if not rows:
        return {"n": 0, "actualMean": 0.0, "predictedMean": 0.0, "mae": 0.0, "rmse": 0.0, "bias": 0.0}
    ys = [num(r.get(actual)) for r in rows]
    ps = [max(0.0, num(r.get(pred))) for r in rows]
    n = len(rows)
    return {
        "n": n,
        "actualMean": fmean(ys),
        "predictedMean": fmean(ps),
        "mae": fmean(abs(a-p) for a,p in zip(ys,ps)),
        "rmse": math.sqrt(fmean((a-p)**2 for a,p in zip(ys,ps))),
        "bias": fmean(p-a for a,p in zip(ys,ps)),
    }


def improvement_pct(base: float, model: float) -> float | None:
    return None if base == 0 else 100.0 * (base - model) / base


def compare(rows: Sequence[dict[str, Any]], actual: str, model: str, bench: str) -> dict[str, Any]:
    mm = metrics(rows, actual, model)
    bm = metrics(rows, actual, bench)
    return {
        "model": mm,
        "benchmark": bm,
        "maeImprovement": bm["mae"] - mm["mae"],
        "maeImprovementPct": improvement_pct(float(bm["mae"]), float(mm["mae"])),
        "rmseImprovement": bm["rmse"] - mm["rmse"],
    }


def percentile(xs: Sequence[float], p: float) -> float:
    if not xs:
        return 0.0
    z = sorted(xs)
    if len(z) == 1:
        return z[0]
    q = max(0.0, min(1.0, p)) * (len(z)-1)
    lo = int(math.floor(q)); hi = int(math.ceil(q))
    if lo == hi:
        return z[lo]
    w = q-lo
    return z[lo]*(1-w)+z[hi]*w


def cluster_bootstrap(rows: Sequence[dict[str, Any]], *, actual: str, model: str, bench: str,
                      cluster: str = "game_id", reps: int = BOOTSTRAP_REPS,
                      seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Paired cluster bootstrap of benchmark-minus-model MAE and RMSE.

    Positive differences mean the model is better. Games are resampled as clusters,
    preserving within-game dependence among player rows and the two team sides.
    """
    by: dict[str, list[tuple[float,float,float]]] = defaultdict(list)
    for r in rows:
        key = str(r.get(cluster) or "")
        by[key].append((num(r.get(actual)), max(0.0,num(r.get(model))), max(0.0,num(r.get(bench)))))
    keys = sorted(k for k in by if k)
    if not keys:
        raise ValueError("no bootstrap clusters")
    rng = random.Random(seed)
    mae_diffs: list[float] = []
    rmse_diffs: list[float] = []
    for _ in range(reps):
        ae_m = ae_b = se_m = se_b = 0.0
        n = 0
        for _j in range(len(keys)):
            k = keys[rng.randrange(len(keys))]
            for a,m,b in by[k]:
                ae_m += abs(a-m); ae_b += abs(a-b)
                se_m += (a-m)**2; se_b += (a-b)**2
                n += 1
        mae_diffs.append((ae_b-ae_m)/n)
        rmse_diffs.append(math.sqrt(se_b/n)-math.sqrt(se_m/n))
    point = compare(rows, actual, model, bench)
    return {
        "cluster": cluster,
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


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = fmean(xs), fmean(ys)
    vx = sum((x-mx)**2 for x in xs)
    vy = sum((y-my)**2 for y in ys)
    if vx <= 1e-12 or vy <= 1e-12:
        return None
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/math.sqrt(vx*vy)


def slice_compare(rows: Sequence[dict[str, Any]], field: str, actual: str, model: str, bench: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(field) or "UNK")].append(r)
    return {k: compare(v, actual, model, bench) for k,v in sorted(groups.items())}


def role_band(v: float) -> str:
    if v < .35: return "LOW_<35%"
    if v < .65: return "ROTATIONAL_35-65%"
    if v < .85: return "STARTER_65-85%"
    return "EVERY_DOWN_85%+"


def history_band(n: int) -> str:
    if n == 0: return "0_COLD"
    if n == 1: return "1_PRIOR_GAME"
    if n <= 4: return "2-4_PRIOR_GAMES"
    if n <= 8: return "5-8_PRIOR_GAMES"
    return "9+_PRIOR_GAMES"


def predicted_deciles(rows: Sequence[dict[str, Any]], pred: str, actual: str, bins: int = 10) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda r: num(r.get(pred)))
    out = []
    n = len(ordered)
    for i in range(bins):
        lo = round(i*n/bins); hi = round((i+1)*n/bins)
        rr = ordered[lo:hi]
        if not rr: continue
        ps = [num(r.get(pred)) for r in rr]
        ys = [num(r.get(actual)) for r in rr]
        out.append({
            "bin": i+1,
            "n": len(rr),
            "predMin": min(ps),
            "predMax": max(ps),
            "predMean": fmean(ps),
            "actualMean": fmean(ys),
            "bias": fmean(ps)-fmean(ys),
        })
    return out


def calibration_ols(rows: Sequence[dict[str, Any]], pred: str, actual: str) -> dict[str, float | None]:
    xs=[num(r.get(pred)) for r in rows]; ys=[num(r.get(actual)) for r in rows]
    if len(xs)<3: return {"intercept":None,"slope":None,"r2":None}
    mx,my=fmean(xs),fmean(ys)
    vx=sum((x-mx)**2 for x in xs)
    if vx<=1e-12: return {"intercept":None,"slope":None,"r2":None}
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/vx
    intercept=my-slope*mx
    vy=sum((y-my)**2 for y in ys)
    cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    r2=(cov*cov/(vx*vy)) if vy>1e-12 else None
    return {"intercept":intercept,"slope":slope,"r2":r2}


def top_misses(rows: Sequence[dict[str, Any]], n: int = 30) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda r: abs(num(r.get("actual_xtc"))-num(r.get("predicted_xtc"))), reverse=True)
    out=[]
    for r in ranked[:n]:
        out.append({
            "game_id":r.get("game_id"), "week":r.get("week"), "team":r.get("team"), "opponent":r.get("opponent"),
            "player_id":r.get("player_id"), "display_name":r.get("display_name"), "position":r.get("position"),
            "position_group":r.get("position_group"), "prior_games":r.get("prior_games"),
            "prior_last4_snap_share":r.get("prior_last4_snap_share"), "actual_snap_share":r.get("actual_snap_share"),
            "predicted_player_defensive_snaps":r.get("predicted_player_defensive_snaps"), "actual_defensive_snaps":r.get("actual_defensive_snaps"),
            "predicted_xtc":r.get("predicted_xtc"), "benchmark_last4_xtc":r.get("benchmark_last4_xtc"), "actual_xtc":r.get("actual_xtc"),
            "model_abs_error":abs(num(r.get("actual_xtc"))-num(r.get("predicted_xtc"))),
            "benchmark_abs_error":abs(num(r.get("actual_xtc"))-num(r.get("benchmark_last4_xtc"))),
        })
    return out


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args=ap.parse_args()
    root=Path(args.root).resolve()
    ptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE"
    if not ptr.exists(): raise SystemExit("FAIL OMEGA 0.2 pointer missing")
    sid=ptr.read_text(encoding="utf-8").strip()
    src=root/"data/models/nfl/omega_tackle_02"/sid
    apath=src/"OMEGA_0.2_AUDIT.json"
    tpath=src/"omega_2024_team_validation.csv"
    ppath=src/"omega_2024_player_validation.csv"
    for p in (apath,tpath,ppath):
        if not p.exists(): raise SystemExit(f"FAIL required OMEGA 0.2 output missing: {p}")
    base_audit=json.loads(apath.read_text(encoding="utf-8"))
    integ=base_audit.get("integrity",{})
    if integ.get("omega2025RowsRead") != 0: raise SystemExit("FAIL OMEGA 2025 seal already violated")
    if integ.get("marketFieldsRead") != 0 or integ.get("oddsPapiRequests") != 0: raise SystemExit("FAIL contaminated OMEGA 0.2 source")
    team=read_csv(tpath); player=read_csv(ppath)
    if any(int(num(r.get("season"))) != 2024 for r in team+player): raise SystemExit("FAIL diagnostics received non-2024 validation rows")

    # fixed diagnostic slices; these are descriptive and are not tuning selectors.
    for r in player:
        r["diagnostic_role_band"] = role_band(num(r.get("prior_last4_snap_share")))
        r["diagnostic_history_band"] = history_band(int(num(r.get("prior_games"))))
        actual=num(r.get("actual_xtc")); pred=num(r.get("predicted_xtc")); bench=num(r.get("benchmark_last4_xtc"))
        r["model_residual"] = actual-pred
        r["benchmark_residual"] = actual-bench
        r["snap_residual"] = num(r.get("actual_defensive_snaps"))-num(r.get("predicted_player_defensive_snaps"))
        r["actual_snaps_rate_counterfactual_xtc"] = num(r.get("actual_defensive_snaps"))*num(r.get("shrunk_credit_rate_per_snap"))
        r["exposure_error_component"] = r["actual_snaps_rate_counterfactual_xtc"]-pred
        r["rate_allocation_residual"] = actual-r["actual_snaps_rate_counterfactual_xtc"]

    team_lookup={(r.get("game_id"),r.get("defense_team")):r for r in team}
    joined=[]
    for r in player:
        tr=team_lookup.get((r.get("game_id"),r.get("team")))
        if tr:
            r["team_xto_residual"] = num(tr.get("actual_opportunity_plays"))-num(tr.get("predicted_xto"))
            r["team_snap_residual"] = num(tr.get("actual_defensive_snaps"))-num(tr.get("predicted_defensive_snaps"))
            denom=max(1.0,num(tr.get("predicted_defensive_snaps")))
            r["team_opportunity_density_residual"] = (num(tr.get("actual_opportunity_plays"))-num(tr.get("predicted_xto")))/denom
            joined.append(r)

    prior_counts=Counter(int(num(r.get("prior_games"))) for r in player)
    one_prior=sum(1 for r in player if int(num(r.get("prior_games")))==1)
    pos=slice_compare(player,"position_group","actual_xtc","predicted_xtc","benchmark_last4_xtc")
    role=slice_compare(player,"diagnostic_role_band","actual_xtc","predicted_xtc","benchmark_last4_xtc")
    hist=slice_compare(player,"diagnostic_history_band","actual_xtc","predicted_xtc","benchmark_last4_xtc")
    overall=compare(player,"actual_xtc","predicted_xtc","benchmark_last4_xtc")
    xsnap=metrics(player,"actual_defensive_snaps","predicted_player_defensive_snaps")
    xto=compare(team,"actual_opportunity_plays","predicted_xto","benchmark_opportunity_plays")
    xteamsnap=compare(team,"actual_defensive_snaps","predicted_defensive_snaps","benchmark_defensive_snaps")

    residual_corr={
        "playerResidual_vs_teamXTOResidual": pearson([num(r.get("model_residual")) for r in joined],[num(r.get("team_xto_residual")) for r in joined]),
        "playerResidual_vs_teamOpportunityDensityResidual": pearson([num(r.get("model_residual")) for r in joined],[num(r.get("team_opportunity_density_residual")) for r in joined]),
        "playerResidual_vs_teamSnapResidual": pearson([num(r.get("model_residual")) for r in joined],[num(r.get("team_snap_residual")) for r in joined]),
        "playerResidual_vs_playerSnapResidual": pearson([num(r.get("model_residual")) for r in player],[num(r.get("snap_residual")) for r in player]),
        "playerResidual_vs_exposureErrorComponent": pearson([num(r.get("model_residual")) for r in player],[num(r.get("exposure_error_component")) for r in player]),
        "playerResidual_vs_rateAllocationResidual": pearson([num(r.get("model_residual")) for r in player],[num(r.get("rate_allocation_residual")) for r in player]),
    }

    diag={
        "schemaVersion":SCHEMA,"version":VERSION,"lineage":LINEAGE,"generatedAt":now(),"sourceSnapshotId":sid,
        "integrity":{"omega2025RowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,"modelFittingPerformed":False,"hyperparameterSelectionPerformed":False},
        "preRegisteredDiagnostics":{
            "H011":{"name":"Opportunity-Density Coupling","mechanism":"If tackle-generating opportunity density matters beyond raw defensive snaps, baseline player residuals should move positively with team xTO/opportunity-density residuals.","expectedDirection":"positive residual correlation","status":"DIAGNOSTIC_ONLY_NOT_PROMOTED"},
            "H012":{"name":"Exposure Error Dominance in Sparse Histories","mechanism":"Role/snap uncertainty should contribute more to xTC error for players with 0-1 prior games than for established players.","expectedDirection":"larger player-snap and xTC errors in 0-1 prior-game bands","status":"DIAGNOSTIC_ONLY_NOT_PROMOTED"},
        },
        "samples":{"teamRows":len(team),"playerRows":len(player),"uniqueGames":len({r.get('game_id') for r in team}),"onePriorGamePlayerRows":one_prior,"priorGameCountDistribution":dict(sorted(prior_counts.items()))},
        "overall":{"xDefensiveSnaps":xteamsnap,"xTO":xto,"xTC":overall,"playerDefensiveSnapForecast":xsnap},
        "pairedGameClusterBootstrap":{
            "xDefensiveSnaps":cluster_bootstrap(team,actual="actual_defensive_snaps",model="predicted_defensive_snaps",bench="benchmark_defensive_snaps",seed=BOOTSTRAP_SEED+1),
            "xTO":cluster_bootstrap(team,actual="actual_opportunity_plays",model="predicted_xto",bench="benchmark_opportunity_plays",seed=BOOTSTRAP_SEED+2),
            "xTC":cluster_bootstrap(player,actual="actual_xtc",model="predicted_xtc",bench="benchmark_last4_xtc",seed=BOOTSTRAP_SEED+3),
        },
        "xTCFailureSlices":{"byPositionGroup":pos,"byProjectedRoleBand":role,"byPriorGameBand":hist},
        "xTCCalibration":{"ols":calibration_ols(player,"predicted_xtc","actual_xtc"),"predictedDeciles":predicted_deciles(player,"predicted_xtc","actual_xtc")},
        "residualDiagnostics":residual_corr,
        "notes":[
            "OMEGA 0.2 xTC currently uses predicted defensive snaps, lagged player snap share, and shrunk credit rate per defensive snap; predicted xTO is not yet an upstream xTC input.",
            "A positive H011 residual relationship would support testing an opportunity-denominator allocation challenger in a later preregistered phase; it does not itself justify promotion.",
            "All slices use 2024 only for diagnosis. No parameter is selected from these slices and OMEGA 2025 remains sealed.",
        ],
    }

    outbase=root/"data/models/nfl/omega_tackle_021_diagnostics"
    out=outbase/sid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable OMEGA 0.2.1 output: {out}")
    staging=outbase/("."+sid+".staging"); staging.mkdir(parents=True,exist_ok=False)
    try:
        write_csv(staging/"omega_2024_player_diagnostic_rows.csv",player)
        write_csv(staging/"omega_2024_largest_xtc_misses.csv",top_misses(player,30))
        write_csv(staging/"omega_2024_xtc_calibration_deciles.csv",diag["xTCCalibration"]["predictedDeciles"])
        (staging/"OMEGA_0.2.1_DIAGNOSTICS.json").write_text(json.dumps(diag,indent=2)+"\n",encoding="utf-8")
        b=diag["pairedGameClusterBootstrap"]; rc=diag["residualDiagnostics"]
        def fmt_ci(x): return f"[{x[0]:+.4f}, {x[1]:+.4f}]"
        lines=[
            "# OMEGA Tackle Model 0.2.1 — Validation Diagnostics", "",
            f"Generated: {diag['generatedAt']}", "",
            "**DIAGNOSTIC ONLY. NO MODEL REFIT, NO SPORTSBOOK DATA, OMEGA 2025 REMAINS SEALED.**", "",
            "## Integrity", "",
            f"- Source OMEGA snapshot: `{sid}`",
            "- 2024 validation rows only",
            "- OMEGA 2025 rows read: **0**",
            "- Market fields read: **0**",
            "- OddsPapi requests: **0**",
            "- Model fitting/hyperparameter selection: **NO**", "",
            "## Overall 2024 baseline", "",
            f"- xDefensiveSnaps MAE improvement vs lag blend: **{xteamsnap['maeImprovement']:+.4f}** ({xteamsnap['maeImprovementPct']:+.2f}%)",
            f"- xTO MAE improvement vs lag blend: **{xto['maeImprovement']:+.4f}** ({xto['maeImprovementPct']:+.2f}%)",
            f"- xTC MAE improvement vs last-4: **{overall['maeImprovement']:+.4f}** ({overall['maeImprovementPct']:+.2f}%)", "",
            "## Paired game-cluster bootstrap", "",
            f"- xDefensiveSnaps MAE Δ (benchmark - model): **{b['xDefensiveSnaps']['maeImprovementPoint']:+.4f}**, 95% CI **{fmt_ci(b['xDefensiveSnaps']['maeImprovementCI95'])}**, P(Δ>0) **{b['xDefensiveSnaps']['maeProbabilityPositive']:.3f}**",
            f"- xTO MAE Δ: **{b['xTO']['maeImprovementPoint']:+.4f}**, 95% CI **{fmt_ci(b['xTO']['maeImprovementCI95'])}**, P(Δ>0) **{b['xTO']['maeProbabilityPositive']:.3f}**",
            f"- xTC MAE Δ: **{b['xTC']['maeImprovementPoint']:+.4f}**, 95% CI **{fmt_ci(b['xTC']['maeImprovementCI95'])}**, P(Δ>0) **{b['xTC']['maeProbabilityPositive']:.3f}**", "",
            "## Sparse-history accounting", "",
            f"- Player validation rows: **{len(player)}**",
            f"- 0 prior games: **{sum(1 for r in player if int(num(r.get('prior_games')))==0)}**",
            f"- 1 prior game: **{one_prior}**",
            f"- 2+ prior games: **{sum(1 for r in player if int(num(r.get('prior_games')))>=2)}**", "",
            "## H011 — Opportunity-Density Coupling", "",
            "OMEGA 0.2 predicts xTO separately, but xTC does not yet consume predicted xTO. The diagnostic asks whether player residuals still move with missed team opportunity density.",
            f"- corr(player xTC residual, team xTO residual): **{rc['playerResidual_vs_teamXTOResidual'] if rc['playerResidual_vs_teamXTOResidual'] is not None else 'NA'}**",
            f"- corr(player xTC residual, team opportunity-density residual): **{rc['playerResidual_vs_teamOpportunityDensityResidual'] if rc['playerResidual_vs_teamOpportunityDensityResidual'] is not None else 'NA'}**", "",
            "## H012 — Exposure Error", "",
            f"- Player defensive-snap forecast MAE: **{xsnap['mae']:.4f}**",
            f"- corr(xTC residual, player snap residual): **{rc['playerResidual_vs_playerSnapResidual'] if rc['playerResidual_vs_playerSnapResidual'] is not None else 'NA'}**",
            f"- corr(xTC residual, exposure-error component): **{rc['playerResidual_vs_exposureErrorComponent'] if rc['playerResidual_vs_exposureErrorComponent'] is not None else 'NA'}**",
            f"- corr(xTC residual, rate/allocation residual): **{rc['playerResidual_vs_rateAllocationResidual'] if rc['playerResidual_vs_rateAllocationResidual'] is not None else 'NA'}**", "",
            "## Position slices", "",
        ]
        for k,v in pos.items():
            lines.append(f"- {k}: n={v['model']['n']} · model MAE {v['model']['mae']:.4f} · benchmark {v['benchmark']['mae']:.4f} · improvement {v['maeImprovementPct']:+.2f}%")
        lines += ["", "## Projected-role slices", ""]
        for k,v in role.items():
            lines.append(f"- {k}: n={v['model']['n']} · model MAE {v['model']['mae']:.4f} · benchmark {v['benchmark']['mae']:.4f} · improvement {v['maeImprovementPct']:+.2f}%")
        lines += ["", "## Prior-history slices", ""]
        for k,v in hist.items():
            lines.append(f"- {k}: n={v['model']['n']} · model MAE {v['model']['mae']:.4f} · benchmark {v['benchmark']['mae']:.4f} · improvement {v['maeImprovementPct']:+.2f}%")
        cal=diag["xTCCalibration"]["ols"]
        lines += ["", "## Count calibration", "",
                  f"- OLS actual~predicted intercept: **{cal['intercept'] if cal['intercept'] is not None else 'NA'}**",
                  f"- OLS slope: **{cal['slope'] if cal['slope'] is not None else 'NA'}**",
                  f"- R²: **{cal['r2'] if cal['r2'] is not None else 'NA'}**", "",
                  "The full predicted-decile table and top 30 misses are written as CSVs for qualitative review.", "",
                  "## Gate", "",
                  "Do not open 2025 or add market data. Use these diagnostics to decide which single preregistered mechanism should be tested next. H011 is the preferred next challenger only if the opportunity-density residual relationship is directionally positive and the failure slices do not reveal a more basic exposure problem.", ""]
        (staging/"OMEGA_0.2.1_DIAGNOSTICS.md").write_text("\n".join(lines),encoding="utf-8")
        files=[]
        for p in sorted(staging.iterdir()):
            if p.is_file(): files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
        (staging/"OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"createdAt":now(),"files":files},indent=2)+"\n",encoding="utf-8")
        os.replace(staging,out)
        (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_DIAGNOSTICS").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise
    print("OMEGA 0.2.1 VALIDATION DIAGNOSTICS")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS xTC paired game-cluster bootstrap 95% CI: {b['xTC']['maeImprovementCI95']}")
    print("PASS OMEGA 2025 untouched · market fields 0 · OddsPapi 0 · no refit")
    print(f"REPORT: {out/'OMEGA_0.2.1_DIAGNOSTICS.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

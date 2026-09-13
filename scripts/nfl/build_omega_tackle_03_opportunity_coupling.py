#!/usr/bin/env python3
"""Build OMEGA 0.3 H011 opportunity-coupling challenger.

H012 exposure model is frozen from 0.2.2. H011 is the only new mechanism:
current predicted xTO is allowed to drive player xTC through a historical,
position-shrunk credit-per-opportunity-exposure rate.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, random, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_TACKLE_OPPORTUNITY_COUPLING_CHALLENGER_0.3"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 290030


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def num(v: Any, default: float=0.0) -> float:
    try:
        if v in (None, ""): return default
        x=float(v); return default if math.isnan(x) else x
    except (TypeError,ValueError): return default


def metrics(rows: Sequence[dict[str,Any]], actual: str, pred: str) -> dict[str,Any]:
    if not rows: return {"n":0,"mae":0.0,"rmse":0.0,"bias":0.0,"actualMean":0.0,"predictedMean":0.0}
    y=[num(r.get(actual)) for r in rows]; p=[num(r.get(pred)) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(a-b) for a,b in zip(y,p)),"rmse":math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),"bias":fmean(b-a for a,b in zip(y,p)),"actualMean":fmean(y),"predictedMean":fmean(p)}


def compare(rows: Sequence[dict[str,Any]], actual: str, challenger: str, baseline: str) -> dict[str,Any]:
    c=metrics(rows,actual,challenger); b=metrics(rows,actual,baseline)
    return {"challenger":c,"baseline":b,"maeImprovement":b["mae"]-c["mae"],"maeImprovementPct":100*(b["mae"]-c["mae"])/b["mae"] if b["mae"] else None,"rmseImprovement":b["rmse"]-c["rmse"]}


def percentile(xs: Sequence[float], p: float) -> float:
    z=sorted(xs)
    if not z: return 0.0
    q=max(0.0,min(1.0,p))*(len(z)-1); lo=int(math.floor(q)); hi=int(math.ceil(q))
    if lo==hi: return z[lo]
    w=q-lo; return z[lo]*(1-w)+z[hi]*w


def cluster_bootstrap(rows: Sequence[dict[str,Any]], actual: str, challenger: str, baseline: str) -> dict[str,Any]:
    by: dict[str,list[tuple[float,float,float]]] = defaultdict(list)
    for r in rows:
        by[str(r.get("game_id") or "")].append((num(r.get(actual)),num(r.get(challenger)),num(r.get(baseline))))
    keys=sorted(k for k in by if k); rng=random.Random(BOOTSTRAP_SEED); ds=[]
    for _ in range(BOOTSTRAP_REPS):
        ec=eb=0.0; n=0
        for _j in range(len(keys)):
            k=keys[rng.randrange(len(keys))]
            for a,c,b in by[k]: ec+=abs(a-c); eb+=abs(a-b); n+=1
        ds.append((eb-ec)/n)
    point=compare(rows,actual,challenger,baseline)
    return {"cluster":"game_id","clusters":len(keys),"reps":BOOTSTRAP_REPS,"seed":BOOTSTRAP_SEED,"maeImprovementPoint":point["maeImprovement"],"maeImprovementCI95":[percentile(ds,.025),percentile(ds,.975)],"probabilityPositive":sum(x>0 for x in ds)/len(ds)}


def corr(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs)!=len(ys) or len(xs)<2: return 0.0
    mx=fmean(xs); my=fmean(ys)
    vx=sum((x-mx)**2 for x in xs); vy=sum((y-my)**2 for y in ys)
    if vx<=0 or vy<=0: return 0.0
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/math.sqrt(vx*vy)


def calibration(rows: Sequence[dict[str,Any]], pred: str) -> dict[str,float]:
    xs=[num(r.get(pred)) for r in rows]; ys=[num(r.get("actual_xtc")) for r in rows]
    if len(xs)<2: return {"intercept":0.0,"slope":0.0,"r2":0.0}
    mx=fmean(xs); my=fmean(ys); sxx=sum((x-mx)**2 for x in xs)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sxx if sxx>0 else 0.0
    intercept=my-slope*mx
    sst=sum((y-my)**2 for y in ys); sse=sum((y-(intercept+slope*x))**2 for x,y in zip(xs,ys))
    return {"intercept":intercept,"slope":slope,"r2":1-sse/sst if sst>0 else 0.0}


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); args=ap.parse_args()
    root=Path(args.root).resolve(); sys.path.insert(0,str(root/"packages/models/nfl/omega"))
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import opportunity_coupling_challenger as oc

    ptrs={
        "foundation":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION",
        "exposure":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE",
        "baseline":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE",
        "diagnostics":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_DIAGNOSTICS",
        "role":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER",
    }
    for p in ptrs.values():
        if not p.exists(): raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    sid=ptrs["foundation"].read_text(encoding="utf-8").strip()
    if any(p.read_text(encoding="utf-8").strip()!=sid for p in ptrs.values()): raise SystemExit("FAIL OMEGA prerequisite pointers disagree")

    foundation=root/"data/normalized/nfl/omega_tackle"/sid
    exposure=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    base=root/"data/models/nfl/omega_tackle_02"/sid
    diag=root/"data/models/nfl/omega_tackle_021_diagnostics"/sid
    role=root/"data/models/nfl/omega_tackle_022_exposure"/sid
    req=[foundation/"OMEGA_TACKLE_FOUNDATION_AUDIT.json",exposure/"OMEGA_TACKLE_EXPOSURE_AUDIT.json",exposure/"omega_tackle_exposure_player_games.csv",foundation/"omega_tackle_play_opportunities.csv",base/"OMEGA_0.2_AUDIT.json",base/"omega_2024_team_validation.csv",diag/"OMEGA_0.2.1_DIAGNOSTICS.json",role/"OMEGA_0.2.2_AUDIT.json",role/"omega_2024_exposure_challenger_validation.csv"]
    for p in req:
        if not p.exists(): raise SystemExit(f"FAIL required source missing: {p}")
    fa=json.loads(req[0].read_text(encoding="utf-8")); ea=json.loads(req[1].read_text(encoding="utf-8")); ba=json.loads(req[4].read_text(encoding="utf-8")); da=json.loads(req[6].read_text(encoding="utf-8")); ra=json.loads(req[7].read_text(encoding="utf-8"))
    seals=[fa.get("omegaHoldoutPbpRowsRead",0),ea.get("omegaHoldoutRowsRead",0),ba.get("integrity",{}).get("omega2025RowsRead",0),da.get("integrity",{}).get("omega2025RowsRead",0),ra.get("integrity",{}).get("omega2025RowsRead",0)]
    if any(int(x)!=0 for x in seals): raise SystemExit("FAIL OMEGA 2025 seal not clean")
    markets=[fa.get("marketFieldsRead",0),ea.get("marketFieldsRead",0),ba.get("integrity",{}).get("marketFieldsRead",0),da.get("integrity",{}).get("marketFieldsRead",0),ra.get("integrity",{}).get("marketFieldsRead",0)]
    if any(int(x)!=0 for x in markets): raise SystemExit("FAIL market contamination")
    if str(ra.get("verdict"))!="H012_EXPOSURE_CHALLENGER_PASS": raise SystemExit(f"FAIL H012 is not frozen PASS: {ra.get('verdict')}")

    exposure_rows=read_csv(exposure/"omega_tackle_exposure_player_games.csv")
    plays=read_csv(foundation/"omega_tackle_play_opportunities.csv")
    if any(int(num(r.get("season")))==2025 for r in exposure_rows+plays): raise SystemExit("FAIL 2025 row read")
    team_outcomes=xb.aggregate_team_game_outcomes(plays,exposure_rows)
    team_rows=xb.build_team_pregame_rows(team_outcomes)
    team_snap_totals=xb.estimate_team_defensive_snaps(exposure_rows)
    role_rows=er.build_exposure_pregame_rows(exposure_rows,team_snap_totals)
    opp_rows=oc.build_opportunity_player_rows(exposure_rows,team_outcomes,team_snap_totals)
    omap={(r["game_id"],r["team"],r["player_id"]):r for r in opp_rows}
    rmap={(r["game_id"],r["team"],r["player_id"]):r for r in role_rows}
    common=sorted(set(omap)&set(rmap))
    joint=[]
    for k in common:
        z=dict(omap[k]); z.update({f"role_{n}":rmap[k][n] for n in er.FEATURE_NAMES}); joint.append(z)

    # Freeze upstream hyperparameters already selected before H011.
    xto_l2=float(ba["selection"]["xTOL2"])
    role_l2=float(ra["selection"]["selectedL2"])

    alpha_search=[]
    for alpha in oc.ALPHA_GRID:
        fold_mae=[]; fold_rmse=[]
        for year in (2021,2022,2023):
            ttrain=[r for r in team_rows if 2017<=int(r["season"])<year]; tval=[r for r in team_rows if int(r["season"])==year]
            rrtrain=[r for r in role_rows if 2017<=int(r["season"])<year]; rrval=[r for r in role_rows if int(r["season"])==year]
            oval=[r for r in opp_rows if int(r["season"])==year]
            if not ttrain or not tval or not rrtrain or not rrval or not oval: continue
            xm=xb.fit_ridge(ttrain,target_key="actual_opportunity_plays",l2=xto_l2)
            em=er.fit_ridge(rrtrain,role_l2)
            xpred={(r["game_id"],r["defense_team"]):xm.predict([float(r[n]) for n in xb.TEAM_FEATURE_NAMES]) for r in tval}
            epred={(r["game_id"],r["team"],r["player_id"]):em.predict(r) for r in rrval}
            scored=oc.score_rows(oval,alpha=alpha,xto_predictions=xpred,exposure_predictions=epred)
            if scored:
                fold_mae.append(oc.mae(scored,"actual_xtc","opportunity_coupled_xtc")); fold_rmse.append(oc.rmse(scored,"actual_xtc","opportunity_coupled_xtc"))
        if fold_mae:
            alpha_search.append({"alphaPseudoOpportunityExposure":alpha,"folds":len(fold_mae),"meanMAE":fmean(fold_mae),"meanRMSE":fmean(fold_rmse)})
    if not alpha_search: raise SystemExit("FAIL no chronological H011 alpha folds")
    alpha_search.sort(key=lambda x:(x["meanMAE"],x["meanRMSE"],x["alphaPseudoOpportunityExposure"]))
    alpha=float(alpha_search[0]["alphaPseudoOpportunityExposure"])

    # 2024 uses the already-written frozen xTO and H012 exposure outputs exactly.
    team_val=read_csv(base/"omega_2024_team_validation.csv")
    role_val=read_csv(role/"omega_2024_exposure_challenger_validation.csv")
    xpred={(r.get("game_id"),r.get("defense_team")):num(r.get("predicted_xto")) for r in team_val}
    epred={(r.get("game_id"),r.get("team"),r.get("player_id")):num(r.get("challenger_snap_share")) for r in role_val}
    oval=[r for r in opp_rows if int(r["season"])==2024]
    scored=oc.score_rows(oval,alpha=alpha,xto_predictions=xpred,exposure_predictions=epred)
    rolemap={(r.get("game_id"),r.get("team"),r.get("player_id")):r for r in role_val}
    teammap={(r.get("game_id"),r.get("defense_team")):r for r in team_val}
    joined=[]
    for r in scored:
        k=(r["game_id"],r["team"],r["player_id"]); br=rolemap.get(k)
        if br is None: continue
        z=dict(r)
        z["h012_xtc"]=num(br.get("challenger_xtc"))
        z["raw_last4_xtc"]=num(br.get("benchmark_last4_xtc"))
        z["h012_player_defensive_snaps"]=num(br.get("challenger_player_defensive_snaps"))
        tv=teammap.get((r["game_id"],r["team"]))
        if tv:
            z["actual_team_opportunities"]=num(tv.get("actual_opportunity_plays"))
            z["predicted_team_opportunities"]=num(tv.get("predicted_xto"))
            z["team_xto_residual"]=z["actual_team_opportunities"]-z["predicted_team_opportunities"]
        joined.append(z)
    if not joined: raise SystemExit("FAIL no 2024 H011 joined rows")

    overall=compare(joined,"actual_xtc","opportunity_coupled_xtc","h012_xtc")
    vs_recent=compare(joined,"actual_xtc","opportunity_coupled_xtc","raw_last4_xtc")
    core=[r for r in joined if str(r.get("position_group")) in {"DB","DL","LB"}]
    corecmp=compare(core,"actual_xtc","opportunity_coupled_xtc","h012_xtc")
    by_pos={}
    for pg in sorted({str(r.get("position_group") or "UNK") for r in joined}):
        rr=[r for r in joined if str(r.get("position_group") or "UNK")==pg]; by_pos[pg]=compare(rr,"actual_xtc","opportunity_coupled_xtc","h012_xtc")
    boot=cluster_bootstrap(joined,"actual_xtc","opportunity_coupled_xtc","h012_xtc")
    pre_res=[num(r.get("actual_xtc"))-num(r.get("h012_xtc")) for r in joined]; post_res=[num(r.get("actual_xtc"))-num(r.get("opportunity_coupled_xtc")) for r in joined]; tres=[num(r.get("team_xto_residual")) for r in joined]
    corr_pre=corr(pre_res,tres); corr_post=corr(post_res,tres)
    cal_h012=calibration(joined,"h012_xtc"); cal_h011=calibration(joined,"opportunity_coupled_xtc")

    lo=boot["maeImprovementCI95"][0]
    if overall["maeImprovement"]>0 and corecmp["maeImprovement"]>0 and lo>0:
        verdict="H011_OPPORTUNITY_COUPLING_PASS"
    elif overall["maeImprovement"]>0 and corecmp["maeImprovement"]>0:
        verdict="H011_DIRECTIONAL_PASS"
    elif (overall["maeImprovement"]>0)!=(corecmp["maeImprovement"]>0):
        verdict="H011_MIXED"
    else:
        verdict="H011_FAIL"

    outbase=root/"data/models/nfl/omega_tackle_03_opportunity"; out=outbase/sid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable OMEGA 0.3 output: {out}")
    staging=outbase/("."+sid+".staging"); staging.mkdir(parents=True,exist_ok=False)
    try:
        write_csv(staging/"omega_2024_opportunity_coupling_validation.csv",joined)
        write_csv(staging/"omega_0.3_alpha_search.csv",alpha_search)
        audit={
            "schemaVersion":SCHEMA,"generatedAt":now(),"sourceSnapshotId":sid,
            "integrity":{"omega2025RowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,"postseasonIncluded":False,"h012Frozen":True,"xTOModelChanged":False,"exposureModelChanged":False,"sportsbookSettlementAssumed":False},
            "selection":{"xtoRidgeL2Frozen":xto_l2,"exposureRidgeL2Frozen":role_l2,"opportunityShrinkageAlpha":alpha,"selectionFolds":[2021,2022,2023],"finalConfirmationSeason":2024,"confirmationStatus":"DIAGNOSTIC_DIRECTED_NOT_PRISTINE_HOLDOUT"},
            "formula":{"opportunityExposure":"team tackle-opportunity plays * player defensive snap share","challengerXTC":"predicted_xTO * H012_predicted_snap_share * shrunk_lagged_credit_per_opportunity_exposure","rateWindowGames":oc.RATE_WINDOW,"alphaGrid":list(oc.ALPHA_GRID)},
            "validation2024":{"rows":len(joined),"overallVsH012":overall,"coreDBDLLBVsH012":corecmp,"vsRawLast4":vs_recent,"byPosition":by_pos,"bootstrap":boot,"residualXTOCorrelationBefore":corr_pre,"residualXTOCorrelationAfter":corr_post,"calibrationH012":cal_h012,"calibrationH011":cal_h011},
            "verdict":verdict,
            "nextGate":"If H011 passes, freeze opportunity coupling and investigate allocation/topology as a new preregistered mechanism. If mixed/fail, retain H012 and inspect position-specific coupling before adding complexity. OMEGA 2025 remains sealed."
        }
        (staging/"OMEGA_0.3_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        md=f"""# OMEGA Tackle Model 0.3 — Opportunity Coupling Challenger Audit

Generated: {audit['generatedAt']}

**SINGLE-MECHANISM CHALLENGER. H011 ONLY. H012 EXPOSURE IS FROZEN. NO MARKET DATA. OMEGA 2025 REMAINS SEALED.**

## Integrity

- Source snapshot: `{sid}`
- 2025 tackle rows read: **0**
- Market fields read: **0**
- OddsPapi requests: **0**
- H012 exposure model changed: **NO**
- 0.2 xTO model changed: **NO**
- Sportsbook settlement convention assumed: **NO**

## H011 mechanism

OMEGA 0.3 replaces per-defensive-snap credit rate with a directly xTO-coupled generative form:

`xTC = predicted xTO × H012 predicted player snap share × shrunk credit rate per opportunity-exposure unit`

A historical opportunity-exposure unit is `realized team tackle-opportunity plays × realized player defensive snap share`. It is an approximation of opportunity exposure, not exact on-field play participation.

## Chronological selection

- Frozen xTO ridge L2: **{xto_l2}**
- Frozen H012 exposure ridge L2: **{role_l2}**
- H011 opportunity shrinkage alpha selected on 2021–2023 folds only: **{alpha}**
- 2024: **diagnostic-directed confirmation** (not a pristine holdout)
- 2025: **SEALED OMEGA HOLDOUT**

## 2024 xTC result

- Rows: **{len(joined)}**
- H011 MAE: **{overall['challenger']['mae']:.4f}** vs frozen H012 **{overall['baseline']['mae']:.4f}** · improvement **{overall['maeImprovement']:+.4f}** ({overall['maeImprovementPct']:+.2f}%)
- H011 RMSE improvement vs H012: **{overall['rmseImprovement']:+.4f}**
- Core DB/DL/LB MAE improvement: **{corecmp['maeImprovement']:+.4f}** ({corecmp['maeImprovementPct']:+.2f}%)
- Paired game-cluster bootstrap MAE Δ (H012 - H011): **{boot['maeImprovementPoint']:+.4f}**, 95% CI **[{boot['maeImprovementCI95'][0]:+.4f}, {boot['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{boot['probabilityPositive']:.3f}**
- H011 MAE vs raw last-4 tackle average: **{vs_recent['challenger']['mae']:.4f}** vs **{vs_recent['baseline']['mae']:.4f}**

## Did coupling remove xTO residual dependence?

- corr(xTC residual, team xTO residual) before H011 / frozen H012: **{corr_pre:.4f}**
- corr(xTC residual, team xTO residual) after H011: **{corr_post:.4f}**

## Position slices
"""
        for pg,v in by_pos.items():
            md += f"\n- {pg}: n={v['challenger']['n']} · H011 MAE {v['challenger']['mae']:.4f} · H012 {v['baseline']['mae']:.4f} · improvement {v['maeImprovementPct']:+.2f}%"
        md += f"""

## Count calibration

- H012 actual~predicted: intercept **{cal_h012['intercept']:.4f}**, slope **{cal_h012['slope']:.4f}**, R² **{cal_h012['r2']:.4f}**
- H011 actual~predicted: intercept **{cal_h011['intercept']:.4f}**, slope **{cal_h011['slope']:.4f}**, R² **{cal_h011['r2']:.4f}**

## Verdict

**{verdict}**

This is predictive research only. It is not evidence of sportsbook edge.

## Next gate

{audit['nextGate']}
"""
        (staging/"OMEGA_0.3_AUDIT.md").write_text(md,encoding="utf-8")
        hashes={p.name:sha256_file(p) for p in staging.iterdir() if p.is_file()}
        (staging/"SHA256SUMS.json").write_text(json.dumps(hashes,indent=2)+"\n",encoding="utf-8")
        os.replace(staging,out)
        (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_OPPORTUNITY_CHALLENGER").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise
    print("OMEGA 0.3 OPPORTUNITY COUPLING CHALLENGER")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS selected opportunity alpha: {alpha}")
    print(f"PASS 2024 MAE improvement vs H012: {overall['maeImprovement']:+.6f}")
    print(f"PASS paired game-cluster bootstrap 95% CI: {boot['maeImprovementCI95']}")
    print(f"VERDICT: {verdict}")
    print("PASS OMEGA 2025 untouched · market fields 0 · OddsPapi 0")
    print(f"REPORT: {out/'OMEGA_0.3_AUDIT.md'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

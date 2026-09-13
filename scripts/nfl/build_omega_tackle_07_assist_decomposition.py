#!/usr/bin/env python3
"""Build OMEGA 0.7 H004 assist-vs-primary credit decomposition challenger."""
from __future__ import annotations

import argparse, csv, json, math, random, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_TACKLE_ASSIST_PRIMARY_DECOMPOSITION_CHALLENGER_0.7"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 290070


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


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        x = float(v)
        return default if math.isnan(x) else x
    except (TypeError, ValueError):
        return default


def metrics(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> dict[str, Any]:
    if not rows:
        return {"n":0,"mae":0.0,"rmse":0.0,"bias":0.0,"actualMean":0.0,"predictedMean":0.0}
    y=[num(r.get(actual)) for r in rows]; p=[num(r.get(pred)) for r in rows]
    return {
        "n":len(rows),
        "mae":fmean(abs(a-b) for a,b in zip(y,p)),
        "rmse":math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),
        "bias":fmean(b-a for a,b in zip(y,p)),
        "actualMean":fmean(y),
        "predictedMean":fmean(p),
    }


def compare(rows: Sequence[dict[str, Any]], actual: str, challenger: str, baseline: str) -> dict[str, Any]:
    c=metrics(rows,actual,challenger); b=metrics(rows,actual,baseline)
    return {
        "challenger":c,"baseline":b,
        "maeImprovement":b["mae"]-c["mae"],
        "maeImprovementPct":100*(b["mae"]-c["mae"])/b["mae"] if b["mae"] else None,
        "rmseImprovement":b["rmse"]-c["rmse"],
    }


def percentile(xs: Sequence[float], p: float) -> float:
    z=sorted(xs)
    if not z: return 0.0
    q=max(0.0,min(1.0,p))*(len(z)-1); lo=int(math.floor(q)); hi=int(math.ceil(q))
    if lo==hi: return z[lo]
    w=q-lo; return z[lo]*(1-w)+z[hi]*w


def cluster_bootstrap(rows: Sequence[dict[str, Any]], actual: str, challenger: str, baseline: str) -> dict[str, Any]:
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
    return {
        "cluster":"game_id","clusters":len(keys),"reps":BOOTSTRAP_REPS,"seed":BOOTSTRAP_SEED,
        "maeImprovementPoint":point["maeImprovement"],
        "maeImprovementCI95":[percentile(ds,.025),percentile(ds,.975)],
        "probabilityPositive":sum(x>0 for x in ds)/len(ds),
    }


def calibration(rows: Sequence[dict[str, Any]], pred: str) -> dict[str,float]:
    xs=[num(r.get(pred)) for r in rows]; ys=[num(r.get("actual_xtc")) for r in rows]
    if len(xs)<2: return {"intercept":0.0,"slope":0.0,"r2":0.0}
    mx=fmean(xs); my=fmean(ys); sxx=sum((x-mx)**2 for x in xs)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sxx if sxx>0 else 0.0
    intercept=my-slope*mx
    sst=sum((y-my)**2 for y in ys); sse=sum((y-(intercept+slope*x))**2 for x,y in zip(xs,ys))
    return {"intercept":intercept,"slope":slope,"r2":1-sse/sst if sst>0 else 0.0}


def corr(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs)<2 or len(xs)!=len(ys): return 0.0
    mx=fmean(xs); my=fmean(ys)
    sx=sum((x-mx)**2 for x in xs); sy=sum((y-my)**2 for y in ys)
    if sx<=0 or sy<=0: return 0.0
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/math.sqrt(sx*sy)


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); args=ap.parse_args()
    root=Path(args.root).resolve(); sys.path.insert(0,str(root/"packages/models/nfl/omega"))
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import assist_primary_decomposition as ad

    ptrs={
        "foundation":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION",
        "exposure":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE",
        "baseline":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE",
        "diagnostics":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_DIAGNOSTICS",
        "role":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER",
        "opp":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_OPPORTUNITY_CHALLENGER",
        "footprint":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FOOTPRINT_CHALLENGER",
        "funnel":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FUNNEL_CHALLENGER",
        "roleconv":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_ROLE_CONVEXITY_CHALLENGER",
    }
    for p in ptrs.values():
        if not p.exists(): raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    sid=ptrs["foundation"].read_text(encoding="utf-8").strip()
    if any(p.read_text(encoding="utf-8").strip()!=sid for p in ptrs.values()):
        raise SystemExit("FAIL OMEGA prerequisite pointers disagree")

    foundation=root/"data/normalized/nfl/omega_tackle"/sid
    exposure=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    base=root/"data/models/nfl/omega_tackle_02"/sid
    role=root/"data/models/nfl/omega_tackle_022_exposure"/sid
    opp=root/"data/models/nfl/omega_tackle_03_opportunity"/sid
    footprint=root/"data/models/nfl/omega_tackle_04_footprint"/sid
    funnel=root/"data/models/nfl/omega_tackle_05_funnel"/sid
    roleconv=root/"data/models/nfl/omega_tackle_06_role_convexity"/sid
    req=[
        foundation/"OMEGA_TACKLE_FOUNDATION_AUDIT.json",
        foundation/"omega_tackle_play_opportunities.csv",
        foundation/"omega_tackle_credit_events.csv",
        exposure/"OMEGA_TACKLE_EXPOSURE_AUDIT.json",
        exposure/"omega_tackle_exposure_player_games.csv",
        base/"OMEGA_0.2_AUDIT.json",
        base/"omega_2024_team_validation.csv",
        role/"OMEGA_0.2.2_AUDIT.json",
        role/"omega_2024_exposure_challenger_validation.csv",
        opp/"OMEGA_0.3_AUDIT.json",
        footprint/"OMEGA_0.4_AUDIT.json",
        footprint/"omega_2024_footprint_validation.csv",
        funnel/"OMEGA_0.5_AUDIT.json",
        roleconv/"OMEGA_0.6_AUDIT.json",
    ]
    for p in req:
        if not p.exists(): raise SystemExit(f"FAIL required source missing: {p}")

    fa=json.loads(req[0].read_text(encoding="utf-8")); ea=json.loads(req[3].read_text(encoding="utf-8"))
    ba=json.loads(req[5].read_text(encoding="utf-8")); ra=json.loads(req[7].read_text(encoding="utf-8"))
    oa=json.loads(req[9].read_text(encoding="utf-8")); fpa=json.loads(req[10].read_text(encoding="utf-8"))
    fua=json.loads(req[12].read_text(encoding="utf-8")); rca=json.loads(req[13].read_text(encoding="utf-8"))
    seals=[fa.get("omegaHoldoutPbpRowsRead",0),ea.get("omegaHoldoutRowsRead",0),ba.get("integrity",{}).get("omega2025RowsRead",0),ra.get("integrity",{}).get("omega2025RowsRead",0),oa.get("integrity",{}).get("omega2025RowsRead",0),fpa.get("integrity",{}).get("omega2025RowsRead",0),fua.get("integrity",{}).get("omega2025RowsRead",0),rca.get("integrity",{}).get("omega2025RowsRead",0)]
    if any(int(x)!=0 for x in seals): raise SystemExit("FAIL OMEGA 2025 seal not clean")
    markets=[fa.get("marketFieldsRead",0),ea.get("marketFieldsRead",0),ba.get("integrity",{}).get("marketFieldsRead",0),ra.get("integrity",{}).get("marketFieldsRead",0),oa.get("integrity",{}).get("marketFieldsRead",0),fpa.get("integrity",{}).get("marketFieldsRead",0),fua.get("integrity",{}).get("marketFieldsRead",0),rca.get("integrity",{}).get("marketFieldsRead",0)]
    if any(int(x)!=0 for x in markets): raise SystemExit("FAIL market contamination")
    if str(ra.get("verdict"))!="H012_EXPOSURE_CHALLENGER_PASS": raise SystemExit(f"FAIL H012 not frozen PASS: {ra.get('verdict')}")
    if str(oa.get("verdict"))!="H011_FAIL": raise SystemExit(f"FAIL H011 expected rejected: {oa.get('verdict')}")
    if str(fpa.get("verdict"))!="H008_TACKLE_OPPORTUNITY_FOOTPRINT_PASS": raise SystemExit(f"FAIL H008 not frozen PASS: {fpa.get('verdict')}")
    if str(fua.get("verdict")) not in {"H002_MIXED","H002_FAIL"}: raise SystemExit(f"FAIL H004 expects H002 not promoted: {fua.get('verdict')}")
    if str(rca.get("verdict"))!="H003_FAIL": raise SystemExit(f"FAIL H004 expects H003 rejected: {rca.get('verdict')}")

    exposure_rows=read_csv(exposure/"omega_tackle_exposure_player_games.csv")
    plays=read_csv(foundation/"omega_tackle_play_opportunities.csv")
    events=read_csv(foundation/"omega_tackle_credit_events.csv")
    if any(int(num(r.get("season")))==2025 for r in exposure_rows+plays+events): raise SystemExit("FAIL 2025 row read")

    team_outcomes=xb.aggregate_team_game_outcomes(plays,exposure_rows)
    team_rows=xb.build_team_pregame_rows(team_outcomes)
    team_snap_totals=xb.estimate_team_defensive_snaps(exposure_rows)
    role_rows=er.build_exposure_pregame_rows(exposure_rows,team_snap_totals)
    family_outcomes=tf.aggregate_team_family_opportunities(plays)
    family_share_rows=tf.build_team_family_share_pregame_rows(family_outcomes)
    family_share_by_season: dict[int,dict[tuple[str,str],dict[str,float]]] = defaultdict(dict)
    for r in family_share_rows:
        family_share_by_season[int(r["season"])][(r["game_id"],r["defense_team"])]= {f:float(r[f"pred_share_{f}"]) for f in tf.FAMILIES}

    class_credits=ad.aggregate_player_family_credit_classes(events,tf.FAMILIES)
    class_rows=ad.build_player_credit_class_rows(exposure_rows,family_outcomes,class_credits,team_snap_totals,tf.FAMILIES)
    mismatches=[r for r in class_rows if abs(float(r["actual_credit_class_sum"])-float(r["actual_xtc"]))>1e-9]
    if mismatches: raise SystemExit(f"FAIL H004 credit-class reconciliation mismatches: {len(mismatches)}")

    xto_l2=float(ba["selection"]["xTOL2"]); role_l2=float(ra["selection"]["selectedL2"]); h008_alpha=float(fpa["selection"]["familyOpportunityShrinkageAlpha"])

    pair_search=[]
    for pa in ad.PRIMARY_ALPHA_GRID:
        for aa in ad.ASSIST_ALPHA_GRID:
            fold_mae=[]; fold_rmse=[]
            for year in (2021,2022,2023):
                ttrain=[r for r in team_rows if 2017<=int(r["season"])<year]; tval=[r for r in team_rows if int(r["season"])==year]
                rrtrain=[r for r in role_rows if 2017<=int(r["season"])<year]; rrval=[r for r in role_rows if int(r["season"])==year]
                pval=[r for r in class_rows if int(r["season"])==year]
                if not ttrain or not tval or not rrtrain or not rrval or not pval: continue
                xm=xb.fit_ridge(ttrain,target_key="actual_opportunity_plays",l2=xto_l2)
                em=er.fit_ridge(rrtrain,role_l2)
                xpred={(r["game_id"],r["defense_team"]):xm.predict([float(r[n]) for n in xb.TEAM_FEATURE_NAMES]) for r in tval}
                epred={(r["game_id"],r["team"],r["player_id"]):em.predict(r) for r in rrval}
                scored=ad.score_rows(pval,primary_alpha=pa,assist_alpha=aa,xto_predictions=xpred,exposure_predictions=epred,family_share_predictions=family_share_by_season.get(year,{}),families=tf.FAMILIES)
                if scored:
                    fold_mae.append(ad.mae(scored,"actual_xtc","h004_xtc")); fold_rmse.append(ad.rmse(scored,"actual_xtc","h004_xtc"))
            if fold_mae:
                pair_search.append({"primaryAlpha":pa,"assistAlpha":aa,"folds":len(fold_mae),"meanMAE":fmean(fold_mae),"meanRMSE":fmean(fold_rmse)})
    if not pair_search: raise SystemExit("FAIL no chronological H004 alpha-pair folds")
    pair_search.sort(key=lambda x:(x["meanMAE"],x["meanRMSE"],x["primaryAlpha"]+x["assistAlpha"],x["primaryAlpha"],x["assistAlpha"]))
    primary_alpha=float(pair_search[0]["primaryAlpha"]); assist_alpha=float(pair_search[0]["assistAlpha"])

    # 2024 uses frozen xTO, H012 exposure, and H008 baseline outputs exactly.
    team_val=read_csv(base/"omega_2024_team_validation.csv")
    role_val=read_csv(role/"omega_2024_exposure_challenger_validation.csv")
    h008_2024=read_csv(footprint/"omega_2024_footprint_validation.csv")
    xpred={(r.get("game_id"),r.get("defense_team")):num(r.get("predicted_xto")) for r in team_val}
    epred={(r.get("game_id"),r.get("team"),r.get("player_id")):num(r.get("challenger_snap_share")) for r in role_val}
    fs2024={(r["game_id"],r["defense_team"]):{f:float(r[f"pred_share_{f}"]) for f in tf.FAMILIES} for r in family_share_rows if int(r["season"])==2024}
    pval=[r for r in class_rows if int(r["season"])==2024]
    scored=ad.score_rows(pval,primary_alpha=primary_alpha,assist_alpha=assist_alpha,xto_predictions=xpred,exposure_predictions=epred,family_share_predictions=fs2024,families=tf.FAMILIES)
    bmap={(r.get("game_id"),r.get("team"),r.get("player_id")):r for r in h008_2024}
    joined=[]
    for r in scored:
        br=bmap.get((r.get("game_id"),r.get("team"),r.get("player_id")))
        if br is None: continue
        z=dict(r); z["h008_xtc"]=num(br.get("topology_xtc")); z["raw_last4_xtc"]=num(br.get("raw_last4_xtc")); joined.append(z)
    if not joined: raise SystemExit("FAIL no 2024 H004 joined rows")

    overall=compare(joined,"actual_xtc","h004_xtc","h008_xtc")
    core=[r for r in joined if str(r.get("position_group")) in {"DB","DL","LB"}]
    corecmp=compare(core,"actual_xtc","h004_xtc","h008_xtc")
    by_pos={}
    for pg in sorted({str(r.get("position_group") or "UNK") for r in joined}):
        rr=[r for r in joined if str(r.get("position_group") or "UNK")==pg]; by_pos[pg]=compare(rr,"actual_xtc","h004_xtc","h008_xtc")
    boot=cluster_bootstrap(joined,"actual_xtc","h004_xtc","h008_xtc")
    cal_h008=calibration(joined,"h008_xtc"); cal_h004=calibration(joined,"h004_xtc")
    positive_core_positions=sum(1 for pg in ("DB","DL","LB") if by_pos.get(pg,{}).get("maeImprovement",0.0)>0)

    primary_metrics=metrics(joined,"actual_primary_total","pred_primary_total")
    assist_metrics=metrics(joined,"actual_assist_total","pred_assist_total")
    actual_total=sum(num(r.get("actual_xtc")) for r in joined); actual_assists=sum(num(r.get("actual_assist_total")) for r in joined)
    pred_total=sum(num(r.get("h004_xtc")) for r in joined); pred_assists=sum(num(r.get("pred_assist_total")) for r in joined)
    actual_assist_share=actual_assists/actual_total if actual_total>0 else 0.0
    predicted_assist_share=pred_assists/pred_total if pred_total>0 else 0.0
    assist_corr=corr([num(r.get("actual_assist_total")) for r in joined],[num(r.get("pred_assist_total")) for r in joined])
    primary_corr=corr([num(r.get("actual_primary_total")) for r in joined],[num(r.get("pred_primary_total")) for r in joined])

    lo=boot["maeImprovementCI95"][0]
    if overall["maeImprovement"]>0 and corecmp["maeImprovement"]>0 and positive_core_positions>=2 and lo>0:
        verdict="H004_ASSIST_PRIMARY_DECOMPOSITION_PASS"
    elif overall["maeImprovement"]>0 and corecmp["maeImprovement"]>0 and positive_core_positions>=2:
        verdict="H004_DIRECTIONAL_PASS"
    elif overall["maeImprovement"]>0:
        verdict="H004_MIXED"
    else:
        verdict="H004_FAIL"

    outbase=root/"data/models/nfl/omega_tackle_07_assist_decomp"; out=outbase/sid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable OMEGA 0.7 output: {out}")
    staging=outbase/("."+sid+".staging"); staging.mkdir(parents=True,exist_ok=False)
    try:
        write_csv(staging/"omega_2024_assist_primary_validation.csv",joined)
        write_csv(staging/"omega_0.7_alpha_pair_search.csv",pair_search)
        audit={
            "schemaVersion":SCHEMA,"generatedAt":now(),"sourceSnapshotId":sid,
            "integrity":{"omega2025RowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,"postseasonIncluded":False,"h012Frozen":True,"h008Frozen":True,"h011Rejected":True,"h002Promoted":False,"h003Rejected":True,"sportsbookSettlementAssumed":False},
            "preregisteredHypothesis":{"id":"H004","name":"Assist-vs-primary credit decomposition","origin":"OMEGA 0.1 hypothesis registry / assist competition family","mechanism":"Combined tackle credit has separate primary and co-credit assist pathways whose persistence/shrinkage can differ even within the same play family.","expectedDirection":"Separate shrinkage should improve combined T+A only if assist and primary processes carry different stable signal."},
            "selection":{"xtoRidgeL2Frozen":xto_l2,"exposureRidgeL2Frozen":role_l2,"h008FamilyAlphaFrozen":h008_alpha,"primaryAlpha":primary_alpha,"assistAlpha":assist_alpha,"primaryAlphaGrid":list(ad.PRIMARY_ALPHA_GRID),"assistAlphaGrid":list(ad.ASSIST_ALPHA_GRID),"selectionFolds":[2021,2022,2023],"finalConfirmationSeason":2024,"confirmationStatus":"DIAGNOSTIC_DIRECTED_NOT_PRISTINE_HOLDOUT"},
            "formula":{"primaryCredit":"SOLO + PRIMARY_WITH_ASSIST","assistCredit":"ASSIST","challenger":"sum_family(predicted_family_opportunity * H012_predicted_snap_share * (shrunk_primary_rate + shrunk_assist_rate))","rateWindowGames":ad.RATE_WINDOW,"note":"If primaryAlpha == assistAlpha == H008 alpha, the decomposition collapses algebraically toward the H008 combined-rate form."},
            "reconciliation":{"creditClassMismatches":0,"pass":True},
            "validation2024":{"rows":len(joined),"overallVsH008":overall,"coreDBDLLBVsH008":corecmp,"positiveCorePositions":positive_core_positions,"byPosition":by_pos,"bootstrap":boot,"calibrationH008":cal_h008,"calibrationH004":cal_h004,"primaryCountMetrics":primary_metrics,"assistCountMetrics":assist_metrics,"actualAssistShare":actual_assist_share,"predictedAssistShare":predicted_assist_share,"assistCountCorrelation":assist_corr,"primaryCountCorrelation":primary_corr},
            "verdict":verdict,
            "nextGate":"If H004 passes, freeze credit-class decomposition and test H005 venue/year official-credit environment without using market data. If mixed/fail, retain H008 as T+A champion; preserve H004 diagnostics for future solo/assists-only markets but do not promote them into T+A. OMEGA 2025 remains sealed."
        }
        (staging/"OMEGA_0.7_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        pos_lines=[]
        for pg,v in by_pos.items():
            pct=v.get("maeImprovementPct"); pct_txt=f"{pct:+.2f}%" if pct is not None else "n/a"
            pos_lines.append(f"- {pg}: n={v['challenger']['n']} · H004 MAE {v['challenger']['mae']:.4f} · H008 {v['baseline']['mae']:.4f} · improvement {pct_txt}")
        md=f"""# OMEGA Tackle Model 0.7 — Assist / Primary Credit Decomposition Audit

Generated: {audit['generatedAt']}

**SINGLE PRE-REGISTERED MECHANISM: H004. H012 EXPOSURE AND H008 TOPOLOGY ARE FROZEN. H011 REJECTED. H002 NOT PROMOTED. H003 REJECTED. NO MARKET DATA. OMEGA 2025 REMAINS SEALED.**

## Why H004 follows H003

H003 selected beta=0 in the untouched 2021–2023 selection folds, so the proposed universal positive replacement-role convexity modifier had no development support and is rejected without rescue. OMEGA keeps H008 as the T+A champion. H004 now tests a different pre-registered mechanism: an official combined tackle credit can arrive through a primary-credit pathway or an assist pathway, and those processes may require different shrinkage even within the same play family.

## Integrity

- Source snapshot: `{sid}`
- 2025 tackle rows read: **0**
- Market fields read: **0**
- OddsPapi requests: **0**
- H012 exposure model changed: **NO**
- H008 topology model changed: **NO**
- H011 promoted: **NO**
- H002 promoted: **NO**
- H003 promoted: **NO**
- Sportsbook settlement convention assumed: **NO**

## H004 mechanism

`PRIMARY = SOLO + PRIMARY_WITH_ASSIST`

`ASSIST = ASSIST`

For each H008 play family, H004 estimates the player's strictly-lagged primary-credit rate and assist-credit rate on the same opportunity-exposure denominator, shrinks those two rates separately toward strictly-prior position-family priors, and then recombines them:

`xTC_H004 = Σ_family(pred_family_opp × H012 snap share × (shrunk_primary_rate + shrunk_assist_rate))`

This is a nested challenger. If the two selected shrinkage strengths converge to H008's same combined-rate shrinkage, H004 should collapse back toward H008 rather than manufacture a gain.

## Chronological selection

- Frozen xTO ridge L2: **{xto_l2}**
- Frozen H012 exposure ridge L2: **{role_l2}**
- Frozen H008 family alpha: **{h008_alpha}**
- H004 primary alpha selected on 2021–2023 folds only: **{primary_alpha}**
- H004 assist alpha selected on 2021–2023 folds only: **{assist_alpha}**
- 2024: **diagnostic-directed confirmation** (not a pristine holdout)
- 2025: **SEALED OMEGA HOLDOUT**

## 2024 combined T+A result

- Rows: **{len(joined)}**
- H004 MAE: **{overall['challenger']['mae']:.4f}** vs frozen H008 **{overall['baseline']['mae']:.4f}** · improvement **{overall['maeImprovement']:+.4f}** ({overall['maeImprovementPct']:+.2f}%)
- H004 RMSE improvement vs H008: **{overall['rmseImprovement']:+.4f}**
- Core DB/DL/LB MAE improvement: **{corecmp['maeImprovement']:+.4f}** ({corecmp['maeImprovementPct']:+.2f}%)
- Core positions improved: **{positive_core_positions}/3**
- Paired game-cluster bootstrap MAE Δ (H008 - H004): **{boot['maeImprovementPoint']:+.4f}**, 95% CI **[{boot['maeImprovementCI95'][0]:+.4f}, {boot['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{boot['probabilityPositive']:.3f}**

## Credit-class diagnostics

- Primary-credit count MAE: **{primary_metrics['mae']:.4f}** · RMSE **{primary_metrics['rmse']:.4f}** · correlation **{primary_corr:.4f}**
- Assist-credit count MAE: **{assist_metrics['mae']:.4f}** · RMSE **{assist_metrics['rmse']:.4f}** · correlation **{assist_corr:.4f}**
- Actual pooled assist share of combined standard-defensive credits: **{actual_assist_share:.4%}**
- Predicted pooled assist share: **{predicted_assist_share:.4%}**

These credit-class diagnostics are research outputs only. They do not redefine a sportsbook settlement formula and do not independently promote H004 into the T+A champion.

## Position slices

{chr(10).join(pos_lines)}

## Count calibration

- H008 actual~predicted: intercept **{cal_h008['intercept']:.4f}**, slope **{cal_h008['slope']:.4f}**, R² **{cal_h008['r2']:.4f}**
- H004 actual~predicted: intercept **{cal_h004['intercept']:.4f}**, slope **{cal_h004['slope']:.4f}**, R² **{cal_h004['r2']:.4f}**

## Verdict

**{verdict}**

This is predictive research only. It is not evidence of sportsbook edge.

## Next gate

If H004 passes, freeze credit-class decomposition and test H005 venue/year official-credit environment without market data. If mixed/fail, retain H008 as T+A champion; preserve H004 diagnostics for future solo/assists-only markets but do not promote them into T+A. OMEGA 2025 remains sealed.
"""
        (staging/"OMEGA_0.7_AUDIT.md").write_text(md,encoding="utf-8")
        meta={"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"verdict":verdict,"files":{p.name:None for p in staging.iterdir() if p.is_file()}}
        (staging/"OMEGA_0.7_MANIFEST.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf-8")
        staging.rename(out)
        (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_ASSIST_DECOMP_CHALLENGER").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

    print("OMEGA 0.7 ASSIST / PRIMARY CREDIT DECOMPOSITION")
    print()
    print(f"PASS source snapshot: {sid}")
    print(f"PASS H004 selected primary/assist alphas: {primary_alpha} / {assist_alpha}")
    print(f"PASS 2024 H004 vs H008 MAE delta: {overall['maeImprovement']:+.6f} · verdict {verdict}")
    print("PASS OMEGA 2025 untouched · market fields 0 · OddsPapi 0 · no settlement assumption")
    print()
    print("REPORT:", out/"OMEGA_0.7_AUDIT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

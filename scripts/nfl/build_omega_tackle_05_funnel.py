#!/usr/bin/env python3
"""Build OMEGA 0.5 H002 tackle-funnel-rigidity allocation challenger."""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, random, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_TACKLE_FUNNEL_RIGIDITY_ALLOCATION_CHALLENGER_0.5"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 290050


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


def calibration(rows: Sequence[dict[str,Any]], pred: str) -> dict[str,float]:
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
    import tackle_funnel_rigidity as fr

    ptrs={
        "foundation":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION",
        "exposure":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE",
        "baseline":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE",
        "diagnostics":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_DIAGNOSTICS",
        "role":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER",
        "opp":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_OPPORTUNITY_CHALLENGER",
        "footprint":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FOOTPRINT_CHALLENGER",
    }
    for p in ptrs.values():
        if not p.exists(): raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    sid=ptrs["foundation"].read_text(encoding="utf-8").strip()
    if any(p.read_text(encoding="utf-8").strip()!=sid for p in ptrs.values()): raise SystemExit("FAIL OMEGA prerequisite pointers disagree")

    foundation=root/"data/normalized/nfl/omega_tackle"/sid
    exposure=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    base=root/"data/models/nfl/omega_tackle_02"/sid
    role=root/"data/models/nfl/omega_tackle_022_exposure"/sid
    opp=root/"data/models/nfl/omega_tackle_03_opportunity"/sid
    footprint=root/"data/models/nfl/omega_tackle_04_footprint"/sid
    req=[
        foundation/"OMEGA_TACKLE_FOUNDATION_AUDIT.json",
        foundation/"omega_tackle_play_opportunities.csv",
        foundation/"omega_tackle_credit_events.csv",
        exposure/"OMEGA_TACKLE_EXPOSURE_AUDIT.json",
        exposure/"omega_tackle_exposure_player_games.csv",
        base/"OMEGA_0.2_AUDIT.json",
        role/"OMEGA_0.2.2_AUDIT.json",
        opp/"OMEGA_0.3_AUDIT.json",
        footprint/"OMEGA_0.4_AUDIT.json",
        footprint/"omega_2024_footprint_validation.csv",
    ]
    for p in req:
        if not p.exists(): raise SystemExit(f"FAIL required source missing: {p}")
    fa=json.loads(req[0].read_text(encoding="utf-8")); ea=json.loads(req[3].read_text(encoding="utf-8")); ba=json.loads(req[5].read_text(encoding="utf-8")); ra=json.loads(req[6].read_text(encoding="utf-8")); oa=json.loads(req[7].read_text(encoding="utf-8")); fpa=json.loads(req[8].read_text(encoding="utf-8"))
    seals=[fa.get("omegaHoldoutPbpRowsRead",0),ea.get("omegaHoldoutRowsRead",0),ba.get("integrity",{}).get("omega2025RowsRead",0),ra.get("integrity",{}).get("omega2025RowsRead",0),oa.get("integrity",{}).get("omega2025RowsRead",0),fpa.get("integrity",{}).get("omega2025RowsRead",0)]
    if any(int(x)!=0 for x in seals): raise SystemExit("FAIL OMEGA 2025 seal not clean")
    markets=[fa.get("marketFieldsRead",0),ea.get("marketFieldsRead",0),ba.get("integrity",{}).get("marketFieldsRead",0),ra.get("integrity",{}).get("marketFieldsRead",0),oa.get("integrity",{}).get("marketFieldsRead",0),fpa.get("integrity",{}).get("marketFieldsRead",0)]
    if any(int(x)!=0 for x in markets): raise SystemExit("FAIL market contamination")
    if str(ra.get("verdict"))!="H012_EXPOSURE_CHALLENGER_PASS": raise SystemExit(f"FAIL H012 is not frozen PASS: {ra.get('verdict')}")
    if str(oa.get("verdict"))!="H011_FAIL": raise SystemExit(f"FAIL H011 expected rejected: {oa.get('verdict')}")
    if str(fpa.get("verdict"))!="H008_TACKLE_OPPORTUNITY_FOOTPRINT_PASS": raise SystemExit(f"FAIL H008 is not frozen PASS: {fpa.get('verdict')}")

    exposure_rows=read_csv(exposure/"omega_tackle_exposure_player_games.csv")
    plays=read_csv(foundation/"omega_tackle_play_opportunities.csv")
    events=read_csv(foundation/"omega_tackle_credit_events.csv")
    if any(int(num(r.get("season")))==2025 for r in exposure_rows+plays+events): raise SystemExit("FAIL 2025 row read")

    team_snap_totals=xb.estimate_team_defensive_snaps(exposure_rows)
    funnel_rows=fr.build_funnel_pregame_rows(exposure_rows,events,plays,team_snap_totals)
    funnel_map={(r["game_id"],r["team"],r["player_id"]):r for r in funnel_rows}

    # Rebuild frozen upstream pregame rows for chronological 2021-2023 lambda selection.
    team_outcomes=xb.aggregate_team_game_outcomes(plays,exposure_rows)
    team_rows=xb.build_team_pregame_rows(team_outcomes)
    role_rows=er.build_exposure_pregame_rows(exposure_rows,team_snap_totals)
    family_outcomes=tf.aggregate_team_family_opportunities(plays)
    family_share_rows=tf.build_team_family_share_pregame_rows(family_outcomes)
    family_share_by_season: dict[int, dict[tuple[str,str], dict[str,float]]] = defaultdict(dict)
    for r in family_share_rows:
        family_share_by_season[int(r["season"])][(r["game_id"],r["defense_team"])]= {f:float(r[f"pred_share_{f}"]) for f in tf.FAMILIES}
    player_family_credits=tf.aggregate_player_family_credits(events)
    topo_rows=tf.build_player_topology_rows(exposure_rows,family_outcomes,player_family_credits,team_snap_totals)

    xto_l2=float(ba["selection"]["xTOL2"])
    role_l2=float(ra["selection"]["selectedL2"])
    h008_alpha=float(fpa["selection"]["familyOpportunityShrinkageAlpha"])

    selection=[]
    for lam in fr.LAMBDA_GRID:
        fold_mae=[]; fold_rmse=[]
        for year in (2021,2022,2023):
            ttrain=[r for r in team_rows if 2017<=int(r["season"])<year]; tval=[r for r in team_rows if int(r["season"])==year]
            rrtrain=[r for r in role_rows if 2017<=int(r["season"])<year]; rrval=[r for r in role_rows if int(r["season"])==year]
            pval=[r for r in topo_rows if int(r["season"])==year]
            if not ttrain or not tval or not rrtrain or not rrval or not pval: continue
            xm=xb.fit_ridge(ttrain,target_key="actual_opportunity_plays",l2=xto_l2)
            em=er.fit_ridge(rrtrain,role_l2)
            xpred={(r["game_id"],r["defense_team"]):xm.predict([float(r[n]) for n in xb.TEAM_FEATURE_NAMES]) for r in tval}
            epred={(r["game_id"],r["team"],r["player_id"]):em.predict(r) for r in rrval}
            fs=family_share_by_season.get(year,{})
            scored=tf.score_rows(pval,alpha=h008_alpha,xto_predictions=xpred,exposure_predictions=epred,family_share_predictions=fs)
            fmap={k:v for k,v in funnel_map.items() if int(v["season"])==year}
            challenged=fr.score_rows(scored,fmap,lam=lam)
            if challenged:
                fold_mae.append(fr.mae(challenged,"actual_xtc","funnel_xtc")); fold_rmse.append(fr.rmse(challenged,"actual_xtc","funnel_xtc"))
        if fold_mae:
            selection.append({"lambda":lam,"folds":len(fold_mae),"meanMAE":fmean(fold_mae),"meanRMSE":fmean(fold_rmse)})
    if not selection: raise SystemExit("FAIL no chronological H002 lambda folds")
    selection.sort(key=lambda x:(x["meanMAE"],x["meanRMSE"],x["lambda"]))
    lam=float(selection[0]["lambda"])

    # 2024 uses the immutable frozen H008 validation output exactly.
    h008_2024=read_csv(footprint/"omega_2024_footprint_validation.csv")
    fmap2024={k:v for k,v in funnel_map.items() if int(v["season"])==2024}
    joined=fr.score_rows(h008_2024,fmap2024,lam=lam)
    if not joined: raise SystemExit("FAIL no 2024 H002 joined rows")
    for r in joined:
        r["h008_xtc"]=num(r.get("topology_xtc"))

    overall=compare(joined,"actual_xtc","funnel_xtc","h008_xtc")
    core=[r for r in joined if str(r.get("position_group")) in {"DB","DL","LB"}]
    corecmp=compare(core,"actual_xtc","funnel_xtc","h008_xtc")
    by_pos={}
    for pg in sorted({str(r.get("position_group") or "UNK") for r in joined}):
        rr=[r for r in joined if str(r.get("position_group") or "UNK")==pg]; by_pos[pg]=compare(rr,"actual_xtc","funnel_xtc","h008_xtc")
    positive_core_positions=sum(1 for pg in ("DB","DL","LB") if by_pos.get(pg,{}).get("maeImprovement",0.0)>0)
    boot=cluster_bootstrap(joined,"actual_xtc","funnel_xtc","h008_xtc")
    cal_h008=calibration(joined,"h008_xtc"); cal_h002=calibration(joined,"funnel_xtc")

    # Mechanism diagnostics: higher prior rigidity should make allocation useful, not less useful.
    rigid=[]; improvements=[]; base_errors=[]
    for r in joined:
        rigid.append(num(r.get("team_funnel_rigidity")))
        be=abs(num(r.get("actual_xtc"))-num(r.get("h008_xtc")))
        ce=abs(num(r.get("actual_xtc"))-num(r.get("funnel_xtc")))
        base_errors.append(be); improvements.append(be-ce)
    rigidity_improvement_corr=corr(rigid,improvements)
    rigidity_base_error_corr=corr(rigid,base_errors)

    # Fixed, interpretable rigidity slices; not used for parameter selection.
    slices={"LOW_<0.50":lambda x:x<0.50,"MID_0.50-0.75":lambda x:0.50<=x<0.75,"HIGH_0.75+":lambda x:x>=0.75}
    by_rigidity={}
    for name,pred in slices.items():
        rr=[r for r in joined if pred(num(r.get("team_funnel_rigidity")))]
        by_rigidity[name]=compare(rr,"actual_xtc","funnel_xtc","h008_xtc") if rr else {"challenger":{"n":0,"mae":0.0},"baseline":{"n":0,"mae":0.0},"maeImprovement":0.0,"maeImprovementPct":None,"rmseImprovement":0.0}

    lo=boot["maeImprovementCI95"][0]
    if lam>0 and overall["maeImprovement"]>0 and corecmp["maeImprovement"]>0 and positive_core_positions>=2 and lo>0:
        verdict="H002_TACKLE_FUNNEL_RIGIDITY_PASS"
    elif lam>0 and overall["maeImprovement"]>0 and corecmp["maeImprovement"]>0 and positive_core_positions>=2:
        verdict="H002_DIRECTIONAL_PASS"
    elif lam>0 and overall["maeImprovement"]>0:
        verdict="H002_MIXED"
    else:
        verdict="H002_FAIL"

    outbase=root/"data/models/nfl/omega_tackle_05_funnel"; out=outbase/sid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable OMEGA 0.5 output: {out}")
    staging=outbase/("."+sid+".staging"); staging.mkdir(parents=True,exist_ok=False)
    try:
        write_csv(staging/"omega_2024_funnel_validation.csv",joined)
        write_csv(staging/"omega_0.5_lambda_search.csv",selection)
        write_csv(staging/"omega_0.5_funnel_pregame_features.csv",funnel_rows)
        audit={
            "schemaVersion":SCHEMA,"generatedAt":now(),"sourceSnapshotId":sid,
            "integrity":{"omega2025RowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,"postseasonIncluded":False,"h012Frozen":True,"h011Rejected":True,"h008Frozen":True,"targetGameParticipantNormalization":False,"sportsbookSettlementAssumed":False},
            "preregisteredHypothesis":{"id":"H002","name":"Tackle funnel rigidity","origin":"OMEGA 0.1 hypothesis registry","mechanism":"Some defenses allocate tackle credit to a stable set of players across opponents.","expectedDirection":"High rigidity lowers player-level forecast error / makes lagged within-defense allocation more useful."},
            "selection":{"xtoRidgeL2Frozen":xto_l2,"exposureRidgeL2Frozen":role_l2,"h008FamilyAlphaFrozen":h008_alpha,"lambda":lam,"lambdaGrid":list(fr.LAMBDA_GRID),"selectionFolds":[2021,2022,2023],"finalConfirmationSeason":2024,"confirmationStatus":"DIAGNOSTIC_DIRECTED_NOT_PRISTINE_HOLDOUT"},
            "formula":{"rigidity":"mean total-variation similarity of consecutive prior team player-credit-share vectors, last 8 team games","priorPlayerShare":"player credits / exact team credits over last 8 player appearances","roleAdjustment":"prior player credit share * H012 predicted snap share / prior mean snap share","teamCreditMass":"sum over H008 predicted family opportunities * strictly-prior league family credits-per-opportunity","effectiveBlendWeight":"lambda * rigidity * min(1, prior_games/4)","challenger":"(1-weight)*H008 + weight*allocation_prediction","targetRosterNormalization":"PROHIBITED"},
            "validation2024":{"rows":len(joined),"overallVsH008":overall,"coreDBDLLBVsH008":corecmp,"positiveCorePositions":positive_core_positions,"byPosition":by_pos,"byRigidity":by_rigidity,"bootstrap":boot,"calibrationH008":cal_h008,"calibrationH002":cal_h002,"rigidityVsImprovementCorrelation":rigidity_improvement_corr,"rigidityVsH008AbsoluteErrorCorrelation":rigidity_base_error_corr},
            "verdict":verdict,
            "nextGate":"If H002 passes, freeze funnel allocation and move to assist-vs-solo allocation (H004/H005) or role-change convexity (H003), one preregistered mechanism at a time. If H002 fails, retain H008 and do not normalize over target-game participants post hoc. OMEGA 2025 remains sealed."
        }
        (staging/"OMEGA_0.5_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        pos_lines=[]
        for pg,v in by_pos.items():
            pos_lines.append(f"- {pg}: n={v['challenger']['n']} · H002 MAE {v['challenger']['mae']:.4f} · H008 {v['baseline']['mae']:.4f} · improvement {v['maeImprovementPct']:+.2f}%")
        rig_lines=[]
        for name,v in by_rigidity.items():
            pct=v.get('maeImprovementPct')
            pct_txt=(f"{pct:+.2f}%" if pct is not None else "n/a")
            rig_lines.append(f"- {name}: n={v['challenger']['n']} · H002 MAE {v['challenger']['mae']:.4f} · H008 {v['baseline']['mae']:.4f} · improvement {pct_txt}")
        md=f"""# OMEGA Tackle Model 0.5 — Funnel Rigidity / Allocation Challenger Audit

Generated: {audit['generatedAt']}

**SINGLE PRE-REGISTERED MECHANISM: H002. H008 TOPOLOGY AND H012 EXPOSURE ARE FROZEN. H011 REMAINS REJECTED. NO MARKET DATA. OMEGA 2025 REMAINS SEALED.**

## Why H002 follows H008

H008 showed that opportunity composition improves individual tackle prediction, especially for linebackers. H002 now tests the next causal layer: whether a defense's tackle credit is predictably *allocated among its players* using strictly-lagged within-defense credit shares and a prior-only rigidity measure.

## Integrity

- Source snapshot: `{sid}`
- 2025 tackle rows read: **0**
- Market fields read: **0**
- OddsPapi requests: **0**
- H012 exposure model changed: **NO**
- H008 topology model changed: **NO**
- H011 promoted: **NO**
- Target-game participant-set normalization: **NO — PROHIBITED**
- Sportsbook settlement convention assumed: **NO**

## H002 mechanism

`rigidity = mean similarity of consecutive prior team player-credit-share vectors`

`role_adjusted_share = prior player share of team credits × (H012 predicted snap share / prior mean snap share)`

`predicted_team_credit_mass = Σ_family(H008 predicted family opportunities × strictly-prior league family credit-units/opportunity)`

`allocation_xTC = predicted_team_credit_mass × role_adjusted_share`

`effective_weight = λ × rigidity × min(1, prior_player_games/4)`

`xTC_H002 = (1-effective_weight) × H008 + effective_weight × allocation_xTC`

Crucially, this challenger never renormalizes over the players who actually appeared in the target game. That would leak target-game participation.

## Chronological selection

- Frozen xTO ridge L2: **{xto_l2}**
- Frozen H012 exposure ridge L2: **{role_l2}**
- Frozen H008 family alpha: **{h008_alpha}**
- H002 blend λ selected on 2021–2023 folds only: **{lam}**
- 2024: **diagnostic-directed confirmation** (not a pristine holdout)
- 2025: **SEALED OMEGA HOLDOUT**

## 2024 result

- Rows: **{len(joined)}**
- H002 MAE: **{overall['challenger']['mae']:.4f}** vs frozen H008 **{overall['baseline']['mae']:.4f}** · improvement **{overall['maeImprovement']:+.4f}** ({overall['maeImprovementPct']:+.2f}%)
- H002 RMSE improvement vs H008: **{overall['rmseImprovement']:+.4f}**
- Core DB/DL/LB MAE improvement: **{corecmp['maeImprovement']:+.4f}** ({corecmp['maeImprovementPct']:+.2f}%)
- Core positions improved: **{positive_core_positions}/3**
- Paired game-cluster bootstrap MAE Δ (H008 - H002): **{boot['maeImprovementPoint']:+.4f}**, 95% CI **[{boot['maeImprovementCI95'][0]:+.4f}, {boot['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{boot['probabilityPositive']:.3f}**

## H002 mechanism diagnostics

- corr(prior funnel rigidity, H002 absolute-error improvement over H008): **{rigidity_improvement_corr:.4f}**
- corr(prior funnel rigidity, H008 absolute error): **{rigidity_base_error_corr:.4f}**

### Rigidity slices

{chr(10).join(rig_lines)}

## Position slices

{chr(10).join(pos_lines)}

## Count calibration

- H008 actual~predicted: intercept **{cal_h008['intercept']:.4f}**, slope **{cal_h008['slope']:.4f}**, R² **{cal_h008['r2']:.4f}**
- H002 actual~predicted: intercept **{cal_h002['intercept']:.4f}**, slope **{cal_h002['slope']:.4f}**, R² **{cal_h002['r2']:.4f}**

## Verdict

**{verdict}**

This is predictive research only. It is not evidence of sportsbook edge.

## Next gate

If H002 passes, freeze funnel allocation and move to assist-vs-solo allocation (H004/H005) or replacement-role convexity (H003), one preregistered mechanism at a time. If H002 fails, retain H008 and do not rescue the result by normalizing over the target game's realized participants. OMEGA 2025 remains sealed.
"""
        (staging/"OMEGA_0.5_AUDIT.md").write_text(md,encoding="utf-8")
        files=[]
        for p in sorted(staging.iterdir()):
            if p.is_file(): files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
        (staging/"OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"createdAt":now(),"files":files},indent=2)+"\n",encoding="utf-8")
        os.replace(staging,out)
        (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FUNNEL_CHALLENGER").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

    print("OMEGA 0.5 FUNNEL RIGIDITY / ALLOCATION CHALLENGER")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS target-game participant normalization prohibited")
    print(f"PASS H002 paired game-cluster bootstrap 95% CI: {boot['maeImprovementCI95']}")
    print(f"VERDICT: {verdict}")
    print("PASS OMEGA 2025 untouched · market fields 0 · OddsPapi 0 · H012/H008 frozen · H011 rejected")
    print(f"REPORT: {out/'OMEGA_0.5_AUDIT.md'}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

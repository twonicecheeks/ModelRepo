#!/usr/bin/env python3
"""Build OMEGA 0.10 H009 game-script elasticity challenger."""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, random, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA="OMEGA_TACKLE_GAME_SCRIPT_ELASTICITY_CHALLENGER_0.10"
BOOTSTRAP_REPS=5000
BOOTSTRAP_SEED=290100


def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def read_csv(path:Path):
    with path.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def write_csv(path:Path,rows:list[dict[str,Any]]):
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n");w.writeheader()
        for r in rows:w.writerow({k:"" if r.get(k) is None else r.get(k) for k in fields})
def sha256_file(path:Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def num(v:Any,default:float=0.0):
    try:
        if v in (None,""):return default
        x=float(v);return default if math.isnan(x) else x
    except (TypeError,ValueError):return default

def metrics(rows:Sequence[dict[str,Any]],actual:str,pred:str):
    if not rows:return {"n":0,"mae":0.0,"rmse":0.0,"bias":0.0,"actualMean":0.0,"predictedMean":0.0}
    y=[num(r.get(actual)) for r in rows];p=[num(r.get(pred)) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(a-b) for a,b in zip(y,p)),"rmse":math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),"bias":fmean(b-a for a,b in zip(y,p)),"actualMean":fmean(y),"predictedMean":fmean(p)}
def compare(rows,actual,challenger,baseline):
    c=metrics(rows,actual,challenger);b=metrics(rows,actual,baseline)
    return {"challenger":c,"baseline":b,"maeImprovement":b["mae"]-c["mae"],"maeImprovementPct":100*(b["mae"]-c["mae"])/b["mae"] if b["mae"] else None,"rmseImprovement":b["rmse"]-c["rmse"]}
def percentile(xs,p):
    z=sorted(xs)
    if not z:return 0.0
    q=max(0,min(1,p))*(len(z)-1);lo=int(math.floor(q));hi=int(math.ceil(q))
    if lo==hi:return z[lo]
    w=q-lo;return z[lo]*(1-w)+z[hi]*w
def cluster_bootstrap(rows,actual,challenger,baseline):
    by=defaultdict(list)
    for r in rows:by[str(r.get("game_id") or "")].append((num(r.get(actual)),num(r.get(challenger)),num(r.get(baseline))))
    keys=sorted(k for k in by if k);rng=random.Random(BOOTSTRAP_SEED);ds=[]
    for _ in range(BOOTSTRAP_REPS):
        ec=eb=0.0;n=0
        for _j in range(len(keys)):
            k=keys[rng.randrange(len(keys))]
            for a,c,b in by[k]:ec+=abs(a-c);eb+=abs(a-b);n+=1
        ds.append((eb-ec)/n)
    point=compare(rows,actual,challenger,baseline)
    return {"cluster":"game_id","clusters":len(keys),"reps":BOOTSTRAP_REPS,"seed":BOOTSTRAP_SEED,"maeImprovementPoint":point["maeImprovement"],"maeImprovementCI95":[percentile(ds,.025),percentile(ds,.975)],"probabilityPositive":sum(x>0 for x in ds)/len(ds)}
def calibration(rows,pred):
    xs=[num(r.get(pred)) for r in rows];ys=[num(r.get("actual_xtc")) for r in rows]
    if len(xs)<2:return {"intercept":0.0,"slope":0.0,"r2":0.0}
    mx=fmean(xs);my=fmean(ys);sxx=sum((x-mx)**2 for x in xs)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sxx if sxx>0 else 0.0;intercept=my-slope*mx
    sst=sum((y-my)**2 for y in ys);sse=sum((y-(intercept+slope*x))**2 for x,y in zip(xs,ys))
    return {"intercept":intercept,"slope":slope,"r2":1-sse/sst if sst>0 else 0.0}


def apply_h009(rows,script_map,beta,gs,tf):
    out=[]
    for r in rows:
        k=(str(r.get("game_id") or ""),str(r.get("team") or ""))
        sr=script_map.get(k)
        if sr is None:continue
        h={f:float(r.get(f"pred_share_{f}") or 0.0) for f in tf.FAMILIES}
        s={f:float(sr.get(f"script_share_{f}") or 0.0) for f in tf.FAMILIES}
        b=gs.blend_family_shares(h,s,beta)
        x_to=float(r.get("predicted_xto") or 0.0);ss=float(r.get("predicted_snap_share") or 0.0)
        pred=0.0;z=dict(r)
        for f in tf.FAMILIES:
            rate=float(r.get(f"shrunk_rate_{f}") or 0.0)
            opp=x_to*b[f]
            z[f"h009_share_{f}"]=b[f];z[f"h009_pred_opp_{f}"]=opp
            pred+=opp*ss*rate
        z["h009_beta"]=float(beta);z["h009_xtc"]=max(0.0,pred)
        for st in gs.STATES:z[f"h009_pred_state_share_{st}"]=float(sr.get(f"pred_state_share_{st}") or 0.0)
        out.append(z)
    return out


def family_share_l1_from_team(script_rows,h008_share_rows,beta,gs,tf):
    hmap={(r["game_id"],r["defense_team"]):r for r in h008_share_rows}
    vals_h=[];vals_s=[];vals_b=[]
    for r in script_rows:
        h=hmap.get((r["game_id"],r["defense_team"]))
        if h is None:continue
        hs={f:float(h.get(f"pred_share_{f}") or 0.0) for f in tf.FAMILIES}
        ss={f:float(r.get(f"script_share_{f}") or 0.0) for f in tf.FAMILIES}
        bs=gs.blend_family_shares(hs,ss,beta)
        actual={f:float(r.get(f"actual_family_share_{f}") or 0.0) for f in tf.FAMILIES}
        vals_h.append(sum(abs(actual[f]-hs[f]) for f in tf.FAMILIES))
        vals_s.append(sum(abs(actual[f]-ss[f]) for f in tf.FAMILIES))
        vals_b.append(sum(abs(actual[f]-bs[f]) for f in tf.FAMILIES))
    return {"n":len(vals_h),"h008MeanL1":fmean(vals_h) if vals_h else 0.0,"scriptOnlyMeanL1":fmean(vals_s) if vals_s else 0.0,"selectedBlendMeanL1":fmean(vals_b) if vals_b else 0.0,"blendImprovementVsH008":(fmean(vals_h)-fmean(vals_b)) if vals_h else 0.0}


def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL");args=ap.parse_args()
    root=Path(args.root).resolve();sys.path.insert(0,str(root/"packages/models/nfl/omega"))
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import game_script_elasticity as gs

    ptrs={
      "foundation":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION",
      "exposure":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE",
      "baseline":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE",
      "role":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER",
      "opp":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_OPPORTUNITY_CHALLENGER",
      "footprint":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FOOTPRINT_CHALLENGER",
      "funnel":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FUNNEL_CHALLENGER",
      "roleconv":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_ROLE_CONVEXITY_CHALLENGER",
      "assist":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_ASSIST_DECOMP_CHALLENGER",
      "venue":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_VENUE_ENVIRONMENT_CHALLENGER",
      "residual":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_RESIDUAL_PERSISTENCE_CHALLENGER",
    }
    for p in ptrs.values():
        if not p.exists():raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    sid=ptrs["foundation"].read_text().strip()
    if any(p.read_text().strip()!=sid for p in ptrs.values()):raise SystemExit("FAIL OMEGA prerequisite pointers disagree")

    foundation=root/"data/normalized/nfl/omega_tackle"/sid;exposure=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    base=root/"data/models/nfl/omega_tackle_02"/sid;role=root/"data/models/nfl/omega_tackle_022_exposure"/sid
    opp=root/"data/models/nfl/omega_tackle_03_opportunity"/sid;foot=root/"data/models/nfl/omega_tackle_04_footprint"/sid
    funnel=root/"data/models/nfl/omega_tackle_05_funnel"/sid;roleconv=root/"data/models/nfl/omega_tackle_06_role_convexity"/sid
    assist=root/"data/models/nfl/omega_tackle_07_assist_decomp"/sid;venue=root/"data/models/nfl/omega_tackle_08_venue_environment"/sid
    residual=root/"data/models/nfl/omega_tackle_09_residual_persistence"/sid
    req=[
      foundation/"OMEGA_TACKLE_FOUNDATION_AUDIT.json",foundation/"omega_tackle_play_opportunities.csv",foundation/"omega_tackle_credit_events.csv",
      exposure/"OMEGA_TACKLE_EXPOSURE_AUDIT.json",exposure/"omega_tackle_exposure_player_games.csv",
      base/"OMEGA_0.2_AUDIT.json",base/"omega_2024_team_validation.csv",
      role/"OMEGA_0.2.2_AUDIT.json",role/"omega_2024_exposure_challenger_validation.csv",
      opp/"OMEGA_0.3_AUDIT.json",foot/"OMEGA_0.4_AUDIT.json",foot/"omega_2024_footprint_validation.csv",foot/"omega_0.4_team_family_share_pregame.csv",
      funnel/"OMEGA_0.5_AUDIT.json",roleconv/"OMEGA_0.6_AUDIT.json",assist/"OMEGA_0.7_AUDIT.json",venue/"OMEGA_0.8_AUDIT.json",residual/"OMEGA_0.9_AUDIT.json",
    ]
    for p in req:
        if not p.exists():raise SystemExit(f"FAIL required source missing: {p}")
    fa=json.loads(req[0].read_text());ea=json.loads(req[3].read_text());ba=json.loads(req[5].read_text());ra=json.loads(req[7].read_text());oa=json.loads(req[9].read_text());fpa=json.loads(req[10].read_text());fua=json.loads(req[13].read_text());rca=json.loads(req[14].read_text());ada=json.loads(req[15].read_text());vea=json.loads(req[16].read_text());rpa=json.loads(req[17].read_text())
    seals=[fa.get("omegaHoldoutPbpRowsRead",0),ea.get("omegaHoldoutRowsRead",0),ba.get("integrity",{}).get("omega2025RowsRead",0),ra.get("integrity",{}).get("omega2025RowsRead",0),oa.get("integrity",{}).get("omega2025RowsRead",0),fpa.get("integrity",{}).get("omega2025RowsRead",0),fua.get("integrity",{}).get("omega2025RowsRead",0),rca.get("integrity",{}).get("omega2025RowsRead",0),ada.get("integrity",{}).get("omega2025RowsRead",0),vea.get("integrity",{}).get("omega2025RowsRead",0),rpa.get("integrity",{}).get("omega2025RowsRead",0)]
    if any(int(x)!=0 for x in seals):raise SystemExit("FAIL OMEGA 2025 seal not clean")
    if str(ra.get("verdict"))!="H012_EXPOSURE_CHALLENGER_PASS":raise SystemExit("FAIL H012 not frozen PASS")
    if str(oa.get("verdict"))!="H011_FAIL":raise SystemExit("FAIL H011 expected rejected")
    if str(fpa.get("verdict"))!="H008_TACKLE_OPPORTUNITY_FOOTPRINT_PASS":raise SystemExit("FAIL H008 not frozen champion")
    if str(fua.get("verdict")) not in {"H002_MIXED","H002_FAIL"}:raise SystemExit("FAIL H002 unexpectedly promoted")
    if str(rca.get("verdict"))!="H003_FAIL":raise SystemExit("FAIL H003 expected rejected")
    if str(vea.get("verdict"))!="H005_FAIL":raise SystemExit("FAIL H005 expected rejected")
    if str(rpa.get("verdict"))!="H007_FAIL_NULL_SELECTED":raise SystemExit("FAIL H007 expected null-selected rejection")

    exposure_rows=read_csv(exposure/"omega_tackle_exposure_player_games.csv");plays=read_csv(foundation/"omega_tackle_play_opportunities.csv");events=read_csv(foundation/"omega_tackle_credit_events.csv")
    if any(int(num(r.get("season")))==2025 for r in exposure_rows+plays+events):raise SystemExit("FAIL 2025 tackle row read")

    team_outcomes=xb.aggregate_team_game_outcomes(plays,exposure_rows);team_rows=xb.build_team_pregame_rows(team_outcomes);team_snap_totals=xb.estimate_team_defensive_snaps(exposure_rows)
    role_rows=er.build_exposure_pregame_rows(exposure_rows,team_snap_totals)
    family_outcomes=tf.aggregate_team_family_opportunities(plays);h008_share_rows=tf.build_team_family_share_pregame_rows(family_outcomes)
    h008_share_by_season=defaultdict(dict)
    for r in h008_share_rows:h008_share_by_season[int(r["season"])][(r["game_id"],r["defense_team"])]= {f:float(r[f"pred_share_{f}"]) for f in tf.FAMILIES}
    state_outcomes=gs.aggregate_state_family_opportunities(plays);script_rows=gs.build_script_family_pregame_rows(state_outcomes)
    script_by_season=defaultdict(dict)
    for r in script_rows:script_by_season[int(r["season"])][(r["game_id"],r["defense_team"])]=r
    player_family_credits=tf.aggregate_player_family_credits(events);topo_rows=tf.build_player_topology_rows(exposure_rows,family_outcomes,player_family_credits,team_snap_totals)
    mismatches=[r for r in topo_rows if abs(float(r["actual_family_credit_sum"])-float(r["actual_xtc"]))>1e-9]
    if mismatches:raise SystemExit(f"FAIL H009 inherited H008 family-credit mismatches: {len(mismatches)}")

    xto_l2=float(ba["selection"]["xTOL2"]);role_l2=float(ra["selection"]["selectedL2"]);h008_alpha=float(fpa["selection"]["familyOpportunityShrinkageAlpha"])

    # Reconstruct frozen H008 predictions for each selection year and evaluate only beta.
    search=[]
    for beta in gs.BETA_GRID:
        fold_mae=[];fold_rmse=[]
        for year in (2021,2022,2023):
            ttrain=[r for r in team_rows if 2017<=int(r["season"])<year];tval=[r for r in team_rows if int(r["season"])==year]
            rrtrain=[r for r in role_rows if 2017<=int(r["season"])<year];rrval=[r for r in role_rows if int(r["season"])==year]
            pval=[r for r in topo_rows if int(r["season"])==year]
            if not ttrain or not tval or not rrtrain or not rrval or not pval:continue
            xm=xb.fit_ridge(ttrain,target_key="actual_opportunity_plays",l2=xto_l2);em=er.fit_ridge(rrtrain,role_l2)
            xpred={(r["game_id"],r["defense_team"]):xm.predict([float(r[n]) for n in xb.TEAM_FEATURE_NAMES]) for r in tval}
            epred={(r["game_id"],r["team"],r["player_id"]):em.predict(r) for r in rrval}
            scored=tf.score_rows(pval,alpha=h008_alpha,xto_predictions=xpred,exposure_predictions=epred,family_share_predictions=h008_share_by_season.get(year,{}))
            h009=apply_h009(scored,script_by_season.get(year,{}),beta,gs,tf)
            if h009:
                fold_mae.append(fmean(abs(float(r["actual_xtc"])-float(r["h009_xtc"])) for r in h009))
                fold_rmse.append(math.sqrt(fmean((float(r["actual_xtc"])-float(r["h009_xtc"]))**2 for r in h009)))
        if fold_mae:search.append({"beta":beta,"folds":len(fold_mae),"meanMAE":fmean(fold_mae),"meanRMSE":fmean(fold_rmse)})
    if not search:raise SystemExit("FAIL no H009 selection folds")
    search.sort(key=lambda x:(x["meanMAE"],x["meanRMSE"],x["beta"]));beta=float(search[0]["beta"])

    # 2024 exact frozen H008 rows; only family-share forecast changes.
    h008_2024=read_csv(foot/"omega_2024_footprint_validation.csv")
    scored2024=apply_h009(h008_2024,script_by_season.get(2024,{}),beta,gs,tf)
    if not scored2024:raise SystemExit("FAIL no H009 2024 rows")
    overall=compare(scored2024,"actual_xtc","h009_xtc","topology_xtc")
    core=[r for r in scored2024 if str(r.get("position_group")) in {"DB","DL","LB"}];corecmp=compare(core,"actual_xtc","h009_xtc","topology_xtc")
    by_pos={}
    for pg in sorted({str(r.get("position_group") or "UNK") for r in scored2024}):
        rr=[r for r in scored2024 if str(r.get("position_group") or "UNK")==pg];by_pos[pg]=compare(rr,"actual_xtc","h009_xtc","topology_xtc")
    pos_improved=sum(1 for pg in ("DB","DL","LB") if by_pos.get(pg,{}).get("maeImprovement",0)>0)
    boot=cluster_bootstrap(scored2024,"actual_xtc","h009_xtc","topology_xtc")
    cal_h008=calibration(scored2024,"topology_xtc");cal_h009=calibration(scored2024,"h009_xtc")
    script2024=[r for r in script_rows if int(r["season"])==2024];h008shares2024=[r for r in h008_share_rows if int(r["season"])==2024]
    family_diag=family_share_l1_from_team(script2024,h008shares2024,beta,gs,tf)
    # State prediction error is descriptive only.
    state_l1=fmean(sum(abs(float(r.get(f"actual_state_share_{s}") or 0.0)-float(r.get(f"pred_state_share_{s}") or 0.0)) for s in gs.STATES) for r in script2024) if script2024 else 0.0

    lo=boot["maeImprovementCI95"][0]
    if beta>0 and overall["maeImprovement"]>0 and corecmp["maeImprovement"]>0 and pos_improved>=2 and lo>0:
        verdict="H009_GAME_SCRIPT_ELASTICITY_PASS"
    elif beta>0 and overall["maeImprovement"]>0 and corecmp["maeImprovement"]>0 and pos_improved>=2:
        verdict="H009_DIRECTIONAL_PASS"
    elif beta==0:
        verdict="H009_FAIL_NULL_SELECTED"
    elif overall["maeImprovement"]>0:
        verdict="H009_MIXED"
    else:
        verdict="H009_FAIL"

    outbase=root/"data/models/nfl/omega_tackle_010_game_script";out=outbase/sid
    if out.exists():raise SystemExit(f"Refusing overwrite immutable OMEGA 0.10 output: {out}")
    staging=outbase/("."+sid+".staging");staging.mkdir(parents=True,exist_ok=False)
    try:
        write_csv(staging/"omega_2024_game_script_validation.csv",scored2024);write_csv(staging/"omega_0.10_beta_search.csv",search);write_csv(staging/"omega_0.10_script_family_pregame.csv",script_rows)
        audit={
          "schemaVersion":SCHEMA,"generatedAt":now(),"sourceSnapshotId":sid,
          "integrity":{"omega2025RowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,"postseasonIncluded":False,"h012Frozen":True,"h008FrozenChampion":True,"h007NullRejected":True,"sportsbookSettlementAssumed":False,"marketGameScriptUsed":False},
          "preregisteredHypothesis":{"id":"H009","name":"Game-script elasticity","origin":"OMEGA 0.1 hypothesis registry","mechanism":"Score state changes offensive opportunity-family mix; a strictly-lagged projected state mixture may improve player tackle-credit prediction beyond unconditional H008 family shares."},
          "selection":{"xtoRidgeL2Frozen":xto_l2,"exposureRidgeL2Frozen":role_l2,"h008FamilyAlphaFrozen":h008_alpha,"beta":beta,"betaGrid":list(gs.BETA_GRID),"selectionFolds":[2021,2022,2023],"finalConfirmationSeason":2024,"confirmationStatus":"DIAGNOSTIC_DIRECTED_NOT_PRISTINE_HOLDOUT"},
          "formula":{"states":list(gs.STATES),"families":list(gs.FAMILIES),"stateThreshold":"offense perspective: trailing <= -7, neutral -6..+6, leading >= +7","teamWindowGames":gs.TEAM_WINDOW,"scriptShare":"sum_state(predicted_state_share * predicted_family_share_given_state)","blend":"(1-beta)*H008_family_share + beta*script_family_share","challenger":"sum_f(frozen_xTO * blended_family_share_f * frozen_H012_snap_share * frozen_H008_player_family_rate_f)","nullAllowed":"beta=0 exactly collapses to H008"},
          "validation2024":{"rows":len(scored2024),"overallVsH008":overall,"coreDBDLLBVsH008":corecmp,"positiveCorePositions":pos_improved,"byPosition":by_pos,"bootstrap":boot,"familyShareForecastDiagnostic":family_diag,"predictedStateShareMeanL1":state_l1,"calibrationH008":cal_h008,"calibrationH009":cal_h009},
          "verdict":verdict,
          "nextGate":"If H009 passes, freeze the score-state-conditioned family mixture and proceed to settlement-specific distribution modeling / prospective price capture. If null/mixed/fail, retain H008 and close the currently pre-registered football-only mechanism loop before opening OMEGA 2025."
        }
        (staging/"OMEGA_0.10_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        pos_lines=[f"- {pg}: n={v['challenger']['n']} · H009 MAE {v['challenger']['mae']:.4f} · H008 {v['baseline']['mae']:.4f} · improvement {v['maeImprovementPct']:+.2f}%" for pg,v in by_pos.items()]
        md=f"""# OMEGA Tackle Model 0.10 — Game-Script Elasticity Challenger Audit

Generated: {audit['generatedAt']}

**SINGLE PRE-REGISTERED MECHANISM: H009. H012 EXPOSURE AND H008 TOPOLOGY ARE FROZEN. H007 SELECTED THE NULL. NO MARKET DATA. OMEGA 2025 REMAINS SEALED.**

## Why H009 follows H007

H007 selected `gamma=0` on 2021–2023, so recent unexplained player residuals do not earn a persistent correction. H009 returns to football structure: H008 models opportunity family, but it forecasts that mix unconditionally. H009 asks whether conditioning the family mixture on a strictly-lagged expected score-state distribution adds predictive information.

## Integrity

- Source snapshot: `{sid}`
- 2025 tackle rows read: **0**
- Market fields read: **0**
- OddsPapi requests: **0**
- Sportsbook spread/total used for game script: **NO**
- H012 exposure changed: **NO**
- H008 topology/player rates changed: **NO**
- H007 promoted: **NO**
- Sportsbook settlement convention assumed: **NO**

## H009 mechanism

Score state uses the offense-perspective pre-play score differential:

- **TRAILING_7P:** <= -7
- **NEUTRAL:** -6 through +6
- **LEADING_7P:** >= +7

For each target game, H009 builds strictly-lagged predicted opportunity-state shares from the opponent offense's last-{gs.TEAM_WINDOW} generated mix and the defense's last-{gs.TEAM_WINDOW} allowed mix. Within each state it similarly forecasts the H008 family mix. The score-state-conditioned family share is:

`script_family_share = Σ_state(pred_state_share × pred_family_share_given_state)`

The only selected challenger weight is:

`blended_family_share = (1-beta) × H008_share + beta × script_family_share`

`beta=0` collapses exactly to H008.

## Chronological selection

- Frozen xTO ridge L2: **{xto_l2}**
- Frozen H012 exposure ridge L2: **{role_l2}**
- Frozen H008 family alpha: **{h008_alpha}**
- H009 beta selected on 2021–2023 only: **{beta}**
- 2024: **diagnostic-directed confirmation** (not a pristine holdout)
- 2025: **SEALED OMEGA HOLDOUT**

## 2024 result

- Rows: **{len(scored2024)}**
- H009 MAE: **{overall['challenger']['mae']:.4f}** vs frozen H008 **{overall['baseline']['mae']:.4f}** · improvement **{overall['maeImprovement']:+.4f}** ({overall['maeImprovementPct']:+.2f}%)
- H009 RMSE improvement vs H008: **{overall['rmseImprovement']:+.4f}**
- Core DB/DL/LB MAE improvement: **{corecmp['maeImprovement']:+.4f}** ({corecmp['maeImprovementPct']:+.2f}%)
- Core positions improved: **{pos_improved}/3**
- Paired game-cluster bootstrap MAE Δ (H008 - H009): **{boot['maeImprovementPoint']:+.4f}**, 95% CI **[{boot['maeImprovementCI95'][0]:+.4f}, {boot['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{boot['probabilityPositive']:.3f}**

## Mechanism diagnostics

- Team family-share forecast mean L1, frozen H008: **{family_diag['h008MeanL1']:.4f}**
- Team family-share forecast mean L1, script-only: **{family_diag['scriptOnlyMeanL1']:.4f}**
- Team family-share forecast mean L1, selected blend: **{family_diag['selectedBlendMeanL1']:.4f}**
- Selected-blend family-share L1 improvement vs H008: **{family_diag['blendImprovementVsH008']:+.4f}**
- Predicted score-state share mean L1: **{state_l1:.4f}**

## Position slices

{chr(10).join(pos_lines)}

## Count calibration

- H008 actual~predicted: intercept **{cal_h008['intercept']:.4f}**, slope **{cal_h008['slope']:.4f}**, R² **{cal_h008['r2']:.4f}**
- H009 actual~predicted: intercept **{cal_h009['intercept']:.4f}**, slope **{cal_h009['slope']:.4f}**, R² **{cal_h009['r2']:.4f}**

## Verdict

**{verdict}**

This is predictive research only. It is not evidence of sportsbook edge.

## Next gate

If H009 passes, freeze the score-state-conditioned family mixture and proceed toward settlement-specific count distributions and prospective tackle-price capture. If H009 selects the null or fails, retain H008 and close the currently pre-registered football-only mechanism loop before considering the sealed 2025 OMEGA holdout.
"""
        (staging/"OMEGA_0.10_AUDIT.md").write_text(md,encoding="utf-8")
        files=[]
        for p in sorted(staging.iterdir()):
            if p.is_file():files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
        (staging/"OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"createdAt":now(),"files":files},indent=2)+"\n",encoding="utf-8")
        os.replace(staging,out);(root/"data/models/nfl/CURRENT_OMEGA_TACKLE_GAME_SCRIPT_CHALLENGER").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True);raise

    print("OMEGA 0.10 GAME-SCRIPT ELASTICITY CHALLENGER")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS H009 beta selected on 2021-2023 only: {beta}")
    print(f"PASS paired game-cluster bootstrap 95% CI: {boot['maeImprovementCI95']}")
    print(f"VERDICT: {verdict}")
    print("PASS OMEGA 2025 untouched · market fields 0 · OddsPapi 0 · H008 frozen")
    print(f"REPORT: {out/'OMEGA_0.10_AUDIT.md'}")
    return 0

if __name__=="__main__":raise SystemExit(main())

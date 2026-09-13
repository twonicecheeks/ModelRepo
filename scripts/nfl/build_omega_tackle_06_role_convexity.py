#!/usr/bin/env python3
"""Build OMEGA 0.6 H003 replacement-role-convexity challenger."""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, random, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_TACKLE_REPLACEMENT_ROLE_CONVEXITY_CHALLENGER_0.6"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 290060


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
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
        return {"n": 0, "mae": 0.0, "rmse": 0.0, "bias": 0.0, "actualMean": 0.0, "predictedMean": 0.0}
    y = [num(r.get(actual)) for r in rows]
    p = [num(r.get(pred)) for r in rows]
    return {
        "n": len(rows),
        "mae": fmean(abs(a-b) for a,b in zip(y,p)),
        "rmse": math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),
        "bias": fmean(b-a for a,b in zip(y,p)),
        "actualMean": fmean(y),
        "predictedMean": fmean(p),
    }


def compare(rows: Sequence[dict[str, Any]], actual: str, challenger: str, baseline: str) -> dict[str, Any]:
    c = metrics(rows, actual, challenger); b = metrics(rows, actual, baseline)
    return {
        "challenger": c,
        "baseline": b,
        "maeImprovement": b["mae"] - c["mae"],
        "maeImprovementPct": 100*(b["mae"]-c["mae"])/b["mae"] if b["mae"] else None,
        "rmseImprovement": b["rmse"] - c["rmse"],
    }


def percentile(xs: Sequence[float], p: float) -> float:
    z = sorted(xs)
    if not z:
        return 0.0
    q = max(0.0, min(1.0, p))*(len(z)-1)
    lo = int(math.floor(q)); hi = int(math.ceil(q))
    if lo == hi:
        return z[lo]
    w = q-lo
    return z[lo]*(1-w)+z[hi]*w


def cluster_bootstrap(rows: Sequence[dict[str, Any]], actual: str, challenger: str, baseline: str, seed: int) -> dict[str, Any]:
    by: dict[str, list[tuple[float,float,float]]] = defaultdict(list)
    for r in rows:
        by[str(r.get("game_id") or "")].append((num(r.get(actual)), num(r.get(challenger)), num(r.get(baseline))))
    keys = sorted(k for k in by if k)
    if not keys:
        return {"cluster":"game_id","clusters":0,"reps":0,"seed":seed,"maeImprovementPoint":0.0,"maeImprovementCI95":[0.0,0.0],"probabilityPositive":0.0}
    rng = random.Random(seed); ds=[]
    for _ in range(BOOTSTRAP_REPS):
        ec=eb=0.0; n=0
        for _j in range(len(keys)):
            k=keys[rng.randrange(len(keys))]
            for a,c,b in by[k]:
                ec += abs(a-c); eb += abs(a-b); n += 1
        ds.append((eb-ec)/n)
    point = compare(rows, actual, challenger, baseline)
    return {
        "cluster":"game_id","clusters":len(keys),"reps":BOOTSTRAP_REPS,"seed":seed,
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
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL"); args=ap.parse_args()
    root=Path(args.root).resolve(); sys.path.insert(0,str(root/"packages/models/nfl/omega"))
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import replacement_role_convexity as rc

    ptrs={
        "foundation":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION",
        "exposure":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE",
        "baseline":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE",
        "diagnostics":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_DIAGNOSTICS",
        "role":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER",
        "opp":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_OPPORTUNITY_CHALLENGER",
        "footprint":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FOOTPRINT_CHALLENGER",
        "funnel":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FUNNEL_CHALLENGER",
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
    funnel=root/"data/models/nfl/omega_tackle_05_funnel"/sid
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
        funnel/"OMEGA_0.5_AUDIT.json",
    ]
    for p in req:
        if not p.exists(): raise SystemExit(f"FAIL required source missing: {p}")
    fa=json.loads(req[0].read_text(encoding="utf-8")); ea=json.loads(req[3].read_text(encoding="utf-8")); ba=json.loads(req[5].read_text(encoding="utf-8")); ra=json.loads(req[6].read_text(encoding="utf-8")); oa=json.loads(req[7].read_text(encoding="utf-8")); fpa=json.loads(req[8].read_text(encoding="utf-8")); fua=json.loads(req[10].read_text(encoding="utf-8"))
    seals=[fa.get("omegaHoldoutPbpRowsRead",0),ea.get("omegaHoldoutRowsRead",0),ba.get("integrity",{}).get("omega2025RowsRead",0),ra.get("integrity",{}).get("omega2025RowsRead",0),oa.get("integrity",{}).get("omega2025RowsRead",0),fpa.get("integrity",{}).get("omega2025RowsRead",0),fua.get("integrity",{}).get("omega2025RowsRead",0)]
    if any(int(x)!=0 for x in seals): raise SystemExit("FAIL OMEGA 2025 seal not clean")
    markets=[fa.get("marketFieldsRead",0),ea.get("marketFieldsRead",0),ba.get("integrity",{}).get("marketFieldsRead",0),ra.get("integrity",{}).get("marketFieldsRead",0),oa.get("integrity",{}).get("marketFieldsRead",0),fpa.get("integrity",{}).get("marketFieldsRead",0),fua.get("integrity",{}).get("marketFieldsRead",0)]
    if any(int(x)!=0 for x in markets): raise SystemExit("FAIL market contamination")
    if str(ra.get("verdict"))!="H012_EXPOSURE_CHALLENGER_PASS": raise SystemExit(f"FAIL H012 not frozen PASS: {ra.get('verdict')}")
    if str(oa.get("verdict"))!="H011_FAIL": raise SystemExit(f"FAIL H011 expected rejected: {oa.get('verdict')}")
    if str(fpa.get("verdict"))!="H008_TACKLE_OPPORTUNITY_FOOTPRINT_PASS": raise SystemExit(f"FAIL H008 not frozen PASS: {fpa.get('verdict')}")
    if str(fua.get("verdict")) not in {"H002_MIXED","H002_FAIL"}: raise SystemExit(f"FAIL H003 expects H002 not promoted: {fua.get('verdict')}")

    exposure_rows=read_csv(exposure/"omega_tackle_exposure_player_games.csv")
    plays=read_csv(foundation/"omega_tackle_play_opportunities.csv")
    events=read_csv(foundation/"omega_tackle_credit_events.csv")
    if any(int(num(r.get("season")))==2025 for r in exposure_rows+plays+events): raise SystemExit("FAIL 2025 row read")

    team_snap_totals=xb.estimate_team_defensive_snaps(exposure_rows)
    transition_rows=rc.build_role_transition_rows(exposure_rows,team_snap_totals)
    transition_map={(r["game_id"],r["team"],r["player_id"]):r for r in transition_rows}

    # Rebuild frozen H008 pregame rows for chronological 2021-2023 beta selection.
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

    beta_search=[]
    for beta in rc.BETA_GRID:
        fold_mae=[]; fold_rmse=[]; activated_mae=[]; activated_base=[]; activated_n=0
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
            fmap={k:v for k,v in transition_map.items() if int(v["season"])==year}
            challenged=rc.score_rows(scored,fmap,beta=beta)
            if challenged:
                fold_mae.append(rc.mae(challenged,"actual_xtc","role_convexity_xtc")); fold_rmse.append(rc.rmse(challenged,"actual_xtc","role_convexity_xtc"))
                ar=[r for r in challenged if int(num(r.get("h003_activated")))==1]
                if ar:
                    activated_mae.append(rc.mae(ar,"actual_xtc","role_convexity_xtc")); activated_base.append(rc.mae(ar,"actual_xtc","topology_xtc")); activated_n += len(ar)
        if fold_mae:
            beta_search.append({
                "beta":beta,"folds":len(fold_mae),"meanMAE":fmean(fold_mae),"meanRMSE":fmean(fold_rmse),
                "activatedRows":activated_n,
                "activatedMeanMAE":fmean(activated_mae) if activated_mae else 0.0,
                "activatedBaselineMeanMAE":fmean(activated_base) if activated_base else 0.0,
                "activatedMAEImprovement": (fmean(activated_base)-fmean(activated_mae)) if activated_mae else 0.0,
            })
    if not beta_search: raise SystemExit("FAIL no chronological H003 beta folds")
    # H003 is an explicitly conditional niche. Select beta on the fixed activated
    # role-expansion state, not on the much larger non-activated population where
    # every beta produces the same frozen H008 prediction. Overall MAE is retained
    # as the first tie-breaker and must still be non-degrading at confirmation.
    eligible_search=[x for x in beta_search if int(x.get("activatedRows",0))>0]
    if not eligible_search: raise SystemExit("FAIL no activated H003 rows in chronological selection folds")
    eligible_search.sort(key=lambda x:(x["activatedMeanMAE"],x["meanMAE"],x["meanRMSE"],x["beta"]))
    beta=float(eligible_search[0]["beta"])

    # 2024 uses immutable H008 output exactly.
    h008_2024=read_csv(footprint/"omega_2024_footprint_validation.csv")
    fmap2024={k:v for k,v in transition_map.items() if int(v["season"])==2024}
    joined=rc.score_rows(h008_2024,fmap2024,beta=beta)
    if not joined: raise SystemExit("FAIL no 2024 H003 joined rows")
    for r in joined: r["h008_xtc"]=num(r.get("topology_xtc"))

    overall=compare(joined,"actual_xtc","role_convexity_xtc","h008_xtc")
    core=[r for r in joined if str(r.get("position_group")) in {"DB","DL","LB"}]
    corecmp=compare(core,"actual_xtc","role_convexity_xtc","h008_xtc")
    by_pos={}
    for pg in sorted({str(r.get("position_group") or "UNK") for r in joined}):
        rr=[r for r in joined if str(r.get("position_group") or "UNK")==pg]
        by_pos[pg]=compare(rr,"actual_xtc","role_convexity_xtc","h008_xtc")
    boot=cluster_bootstrap(joined,"actual_xtc","role_convexity_xtc","h008_xtc",BOOTSTRAP_SEED)
    cal_h008=calibration(joined,"h008_xtc"); cal_h003=calibration(joined,"role_convexity_xtc")

    activated=[r for r in joined if int(num(r.get("h003_activated")))==1]
    actcmp=compare(activated,"actual_xtc","role_convexity_xtc","h008_xtc") if activated else compare([],"actual_xtc","role_convexity_xtc","h008_xtc")
    actboot=cluster_bootstrap(activated,"actual_xtc","role_convexity_xtc","h008_xtc",BOOTSTRAP_SEED+1) if activated else {"cluster":"game_id","clusters":0,"reps":0,"seed":BOOTSTRAP_SEED+1,"maeImprovementPoint":0.0,"maeImprovementCI95":[0.0,0.0],"probabilityPositive":0.0}
    large=[r for r in joined if num(r.get("h003_role_jump"))>=0.20 and int(num(r.get("h003_activated")))==1]
    largecmp=compare(large,"actual_xtc","role_convexity_xtc","h008_xtc") if large else compare([],"actual_xtc","role_convexity_xtc","h008_xtc")

    # Diagnostic only: within activated rows, bigger role jumps should tend to make convexity more useful.
    jumps=[]; improvements=[]
    for r in activated:
        be=abs(num(r.get("actual_xtc"))-num(r.get("h008_xtc")))
        ce=abs(num(r.get("actual_xtc"))-num(r.get("role_convexity_xtc")))
        jumps.append(num(r.get("h003_role_jump"))); improvements.append(be-ce)
    jump_improvement_corr=corr(jumps,improvements)

    slices={
        "NO_ACTIVATION":lambda r:int(num(r.get("h003_activated")))==0,
        "JUMP_10_20PP":lambda r:int(num(r.get("h003_activated")))==1 and 0.10<=num(r.get("h003_role_jump"))<0.20,
        "JUMP_20PP_PLUS":lambda r:int(num(r.get("h003_activated")))==1 and num(r.get("h003_role_jump"))>=0.20,
    }
    by_jump={}
    for name,pred in slices.items():
        rr=[r for r in joined if pred(r)]
        by_jump[name]=compare(rr,"actual_xtc","role_convexity_xtc","h008_xtc") if rr else compare([],"actual_xtc","role_convexity_xtc","h008_xtc")

    lo=boot["maeImprovementCI95"][0]; alo=actboot["maeImprovementCI95"][0] if activated else 0.0
    if beta>0 and overall["maeImprovement"]>0 and actcmp["maeImprovement"]>0 and lo>0 and alo>0:
        verdict="H003_REPLACEMENT_ROLE_CONVEXITY_PASS"
    elif beta>0 and overall["maeImprovement"]>=0 and actcmp["maeImprovement"]>0 and alo>0:
        verdict="H003_REPLACEMENT_ROLE_CONVEXITY_NICHE_PASS"
    elif beta>0 and actcmp["maeImprovement"]>0:
        verdict="H003_MIXED"
    else:
        verdict="H003_FAIL"

    outbase=root/"data/models/nfl/omega_tackle_06_role_convexity"; out=outbase/sid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable OMEGA 0.6 output: {out}")
    staging=outbase/("."+sid+".staging"); staging.mkdir(parents=True,exist_ok=False)
    try:
        write_csv(staging/"omega_2024_role_convexity_validation.csv",joined)
        write_csv(staging/"omega_0.6_beta_search.csv",beta_search)
        write_csv(staging/"omega_0.6_role_transition_pregame.csv",transition_rows)
        audit={
            "schemaVersion":SCHEMA,"generatedAt":now(),"sourceSnapshotId":sid,
            "integrity":{"omega2025RowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,"postseasonIncluded":False,"h012Frozen":True,"h008Frozen":True,"h011Rejected":True,"h002Promoted":False,"sportsbookSettlementAssumed":False},
            "preregisteredHypothesis":{"id":"H003","name":"Replacement-role convexity","origin":"OMEGA 0.1 hypothesis registry","mechanism":"A material role expansion may change tackle efficiency, so production can scale nonlinearly with predicted snaps.","expectedDirection":"Positive convexity on large strictly-lagged role expansions."},
            "selection":{"xtoRidgeL2Frozen":xto_l2,"exposureRidgeL2Frozen":role_l2,"h008FamilyAlphaFrozen":h008_alpha,"beta":beta,"betaGrid":list(rc.BETA_GRID),"selectionTarget":"ACTIVATED_ROLE_EXPANSION_MAE","activationJump":rc.ACTIVATION_JUMP,"confidenceGames":rc.CONFIDENCE_GAMES,"maxFactor":rc.MAX_FACTOR,"selectionFolds":[2021,2022,2023],"finalConfirmationSeason":2024,"confirmationStatus":"DIAGNOSTIC_DIRECTED_NOT_PRISTINE_HOLDOUT"},
            "formula":{"prechangeBaseline":"mean of up to four appearances before the most recent appearance; strictly-prior position fallback","roleJump":"H012 predicted snap share - prechange baseline","activation":"prior_games>=1 and role_jump>=0.10","historyConfidence":"min(1, prior_games/2)","challenger":"H008 * min(1.50, 1 + beta * role_jump * history_confidence) when activated; else H008"},
            "validation2024":{"rows":len(joined),"activatedRows":len(activated),"largeJumpRows":len(large),"overallVsH008":overall,"coreDBDLLBVsH008":corecmp,"activatedVsH008":actcmp,"largeJumpVsH008":largecmp,"byPosition":by_pos,"byRoleJump":by_jump,"bootstrapOverall":boot,"bootstrapActivated":actboot,"calibrationH008":cal_h008,"calibrationH003":cal_h003,"roleJumpVsImprovementCorrelationActivated":jump_improvement_corr},
            "verdict":verdict,
            "nextGate":"If H003 passes or niche-passes, preserve it only in the pre-registered activated role-expansion state and move to H004 assist-vs-primary credit decomposition. If mixed/fail, retain H008 as champion and move to H004 without post-hoc rescue. OMEGA 2025 remains sealed."
        }
        (staging/"OMEGA_0.6_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        pos_lines=[]
        for pg,v in by_pos.items():
            pct=v.get("maeImprovementPct"); pct_txt=f"{pct:+.2f}%" if pct is not None else "n/a"
            pos_lines.append(f"- {pg}: n={v['challenger']['n']} · H003 MAE {v['challenger']['mae']:.4f} · H008 {v['baseline']['mae']:.4f} · improvement {pct_txt}")
        jump_lines=[]
        for name,v in by_jump.items():
            pct=v.get("maeImprovementPct"); pct_txt=f"{pct:+.2f}%" if pct is not None else "n/a"
            jump_lines.append(f"- {name}: n={v['challenger']['n']} · H003 MAE {v['challenger']['mae']:.4f} · H008 {v['baseline']['mae']:.4f} · improvement {pct_txt}")
        md=f"""# OMEGA Tackle Model 0.6 — Replacement-Role Convexity Challenger Audit

Generated: {audit['generatedAt']}

**SINGLE PRE-REGISTERED MECHANISM: H003. H012 EXPOSURE AND H008 TOPOLOGY ARE FROZEN. H011 REJECTED. H002 NOT PROMOTED. NO MARKET DATA. OMEGA 2025 REMAINS SEALED.**

## Why H003 follows H002

H002's broad within-defense funnel allocation was mixed and its rigidity measure did not explain forecast improvement. OMEGA therefore keeps H008 as the champion. H003 tests a different pre-registered niche that follows directly from the earlier H012 result: if a defender's role materially expands, tackle production may scale *convexly* rather than linearly because the role itself can change with playing time.

## Integrity

- Source snapshot: `{sid}`
- 2025 tackle rows read: **0**
- Market fields read: **0**
- OddsPapi requests: **0**
- H012 exposure model changed: **NO**
- H008 topology model changed: **NO**
- H011 promoted: **NO**
- H002 promoted: **NO**
- Sportsbook settlement convention assumed: **NO**

## H003 mechanism

`prechange_baseline = mean(up to 4 appearances before the most recent appearance)` with a strictly-prior position fallback.

`role_jump = H012 predicted snap share - prechange_baseline`

Activation is fixed in advance at **+{rc.ACTIVATION_JUMP:.0%}** predicted snap share and at least one prior game.

`history_confidence = min(1, prior_games/{rc.CONFIDENCE_GAMES})`

`xTC_H003 = H008 × min({rc.MAX_FACTOR:.2f}, 1 + beta × role_jump × history_confidence)` when activated; otherwise H003 equals H008 exactly.

## Chronological selection

- Frozen xTO ridge L2: **{xto_l2}**
- Frozen H012 exposure ridge L2: **{role_l2}**
- Frozen H008 family alpha: **{h008_alpha}**
- H003 beta selected on 2021–2023 folds only: **{beta}**
- Selection target: **MAE within the fixed activated role-expansion state** (overall MAE is a confirmation safety gate)
- 2024: **diagnostic-directed confirmation** (not a pristine holdout)
- 2025: **SEALED OMEGA HOLDOUT**

## 2024 result

- Rows: **{len(joined)}**
- Activated role-expansion rows: **{len(activated)}**
- Large role-jump (20pp+) rows: **{len(large)}**
- H003 MAE: **{overall['challenger']['mae']:.4f}** vs frozen H008 **{overall['baseline']['mae']:.4f}** · improvement **{overall['maeImprovement']:+.4f}** ({overall['maeImprovementPct']:+.2f}%)
- H003 RMSE improvement vs H008: **{overall['rmseImprovement']:+.4f}**
- Paired game-cluster bootstrap overall MAE Δ (H008 - H003): **{boot['maeImprovementPoint']:+.4f}**, 95% CI **[{boot['maeImprovementCI95'][0]:+.4f}, {boot['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{boot['probabilityPositive']:.3f}**
- Activated-subset MAE improvement: **{actcmp['maeImprovement']:+.4f}** ({actcmp['maeImprovementPct']:+.2f}% if defined)
- Activated-subset bootstrap 95% CI: **[{actboot['maeImprovementCI95'][0]:+.4f}, {actboot['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{actboot['probabilityPositive']:.3f}**

## Role-jump slices

{chr(10).join(jump_lines)}

## Position slices

{chr(10).join(pos_lines)}

## Mechanism diagnostic

- corr(role jump, H003 absolute-error improvement over H008) among activated rows: **{jump_improvement_corr:.4f}**

## Count calibration

- H008 actual~predicted: intercept **{cal_h008['intercept']:.4f}**, slope **{cal_h008['slope']:.4f}**, R² **{cal_h008['r2']:.4f}**
- H003 actual~predicted: intercept **{cal_h003['intercept']:.4f}**, slope **{cal_h003['slope']:.4f}**, R² **{cal_h003['r2']:.4f}**

## Verdict

**{verdict}**

This is predictive research only. It is not evidence of sportsbook edge.

## Next gate

If H003 passes or niche-passes, preserve it only in the pre-registered activated role-expansion state and move to H004 assist-vs-primary credit decomposition. If mixed/fail, retain H008 as champion and move to H004 without post-hoc rescue. OMEGA 2025 remains sealed.
"""
        # Clean the awkward conditional text in one report line.
        md=md.replace(f"({actcmp['maeImprovementPct']:+.2f}% if defined)", f"({actcmp['maeImprovementPct']:+.2f}%)" if actcmp['maeImprovementPct'] is not None else "(n/a)")
        (staging/"OMEGA_0.6_AUDIT.md").write_text(md,encoding="utf-8")
        files=[]
        for p in sorted(staging.iterdir()):
            if p.is_file(): files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
        (staging/"OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"createdAt":now(),"files":files},indent=2)+"\n",encoding="utf-8")
        os.replace(staging,out)
        (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_ROLE_CONVEXITY_CHALLENGER").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

    print("OMEGA 0.6 REPLACEMENT-ROLE CONVEXITY CHALLENGER")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS fixed H003 activation: +{rc.ACTIVATION_JUMP:.0%} role jump; selected beta {beta}")
    print(f"PASS overall game-cluster bootstrap 95% CI: {boot['maeImprovementCI95']}")
    print(f"PASS activated game-cluster bootstrap 95% CI: {actboot['maeImprovementCI95']}")
    print(f"VERDICT: {verdict}")
    print("PASS OMEGA 2025 untouched · market fields 0 · OddsPapi 0 · H012/H008 frozen · H011 rejected · H002 not promoted")
    print(f"REPORT: {out/'OMEGA_0.6_AUDIT.md'}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

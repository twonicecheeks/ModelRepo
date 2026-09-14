#!/usr/bin/env python3
"""Build OMEGA 0.2.7 current-role snap-share distribution challenger.

Frozen OMEGA stays read-only. Historical nflverse weekly depth charts (2019-2024)
are joined by season/week/team/GSIS id.  H012 remains the anchor; a chronological
role-state model predicts only the residual correction.  A role-aware empirical
residual distribution is then evaluated on 2024.  2025 remains sealed.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, random, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_TACKLE_CURRENT_ROLE_SNAP_DISTRIBUTION_CHALLENGER_0.2.7"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 270027
DEV_YEARS = (2019,2020,2021,2022,2023)
DIST_CAL_YEARS = (2020,2021,2022,2023)
TEST_YEAR = 2024
SEALED_YEAR = 2025


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def rcsv(path: Path) -> list[dict[str,str]]:
    with path.open(newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))


def wcsv(path: Path, rows: Sequence[dict[str,Any]]) -> None:
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields or ["status"],extrasaction="ignore",lineterminator="\n")
        w.writeheader(); w.writerows(rows)


def num(v: Any, d: float=0.0) -> float:
    try:
        if v in (None,""): return d
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d


def normteam(v: Any) -> str:
    x=str(v or "").strip().upper()
    return {"JAX":"JAC","LAR":"LA","STL":"LA","SD":"LAC","OAK":"LV"}.get(x,x)


def metrics(rows: Sequence[dict[str,Any]], actual: str, pred: str) -> dict[str,Any]:
    if not rows: return {"n":0}
    y=[num(r.get(actual)) for r in rows]; p=[num(r.get(pred)) for r in rows]
    return {"n":len(rows),"actualMean":fmean(y),"predictedMean":fmean(p),
            "mae":fmean(abs(a-b) for a,b in zip(y,p)),
            "rmse":math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),
            "biasPredMinusActual":fmean(b-a for a,b in zip(y,p))}


def percentile(xs: Sequence[float], p: float) -> float:
    z=sorted(float(x) for x in xs)
    if not z: return 0.0
    q=max(0,min(1,float(p)))*(len(z)-1); lo=int(math.floor(q)); hi=int(math.ceil(q))
    if lo==hi: return z[lo]
    w=q-lo; return z[lo]*(1-w)+z[hi]*w


def game_cluster_bootstrap(rows: Sequence[dict[str,Any]], challenger_loss: str, baseline_loss: str) -> dict[str,Any]:
    by=defaultdict(list)
    for r in rows:
        gid=str(r.get("game_id") or "")
        if gid: by[gid].append((num(r.get(challenger_loss)),num(r.get(baseline_loss))))
    keys=sorted(by)
    if not keys: return {"clusters":0}
    point=fmean(num(r.get(baseline_loss))-num(r.get(challenger_loss)) for r in rows)
    rng=random.Random(BOOTSTRAP_SEED); draws=[]
    for _ in range(BOOTSTRAP_REPS):
        c=b=0.0; n=0
        for _j in range(len(keys)):
            vals=by[keys[rng.randrange(len(keys))]]
            for cc,bb in vals: c+=cc; b+=bb; n+=1
        draws.append((b-c)/n)
    return {"cluster":"game_id","clusters":len(keys),"reps":BOOTSTRAP_REPS,"seed":BOOTSTRAP_SEED,
            "improvementPoint":point,"improvementCI95":[percentile(draws,.025),percentile(draws,.975)],
            "probabilityPositive":sum(x>0 for x in draws)/len(draws)}


def interval_summary(rows: Sequence[dict[str,Any]], prefix: str) -> dict[str,float]:
    return {f"coverage{level}":fmean(num(r.get(f"{prefix}_covered_{level}")) for r in rows)
            for level in (50,80,90)} | {f"meanWidth{level}":fmean(num(r.get(f"{prefix}_width_{level}")) for r in rows)
            for level in (50,80,90)}


def threshold_brier(rows: Sequence[dict[str,Any]], prefix: str) -> float:
    return fmean(num(r.get(f"{prefix}_brier_ge_{t}")) for r in rows for t in ("035","065","085"))


def load_depth_history(audit_dir: Path, audit: dict[str,Any]) -> tuple[dict[tuple[int,int,str,str],dict[str,Any]],dict[str,Any]]:
    import pyarrow.parquet as pq
    years=set(int(x) for x in audit.get("yearsRead",[]))
    if SEALED_YEAR in years or audit.get("sealed2025RowsRead") != 0:
        raise SystemExit("FAIL 2025 depth-chart seal violated")
    need=set(range(2019,2025))
    if not need.issubset(years): raise SystemExit(f"FAIL depth audit missing historical years {sorted(need-years)}")
    best: dict[tuple[int,int,str,str],dict[str,Any]]={}
    rows_read=0
    for a in audit.get("assets",[]):
        year=int(a.get("year") or 0)
        if year not in need: continue
        p=audit_dir/str(a["filename"])
        if not p.exists() or sha256_file(p)!=a.get("sha256"): raise SystemExit(f"FAIL depth asset hash/path {p}")
        pf=pq.ParquetFile(p); names=set(pf.schema_arrow.names)
        cols=[x for x in ("season","week","game_type","club_code","team","gsis_id","depth_position","depth_team","formation") if x in names]
        for r in pf.read(columns=cols).to_pylist():
            if int(num(r.get("season"),year))!=year: continue
            if str(r.get("game_type") or "REG").strip().upper() not in {"REG",""}: continue
            if str(r.get("formation") or "").strip().upper() not in {"DEFENSE","DEF"}: continue
            pid=str(r.get("gsis_id") or "").strip(); team=normteam(r.get("club_code") or r.get("team"))
            week=int(num(r.get("week"))); rank=int(num(r.get("depth_team")))
            if not pid or not team or week<=0 or rank<=0: continue
            rows_read+=1; key=(year,week,team,pid)
            rec={"season":year,"week":week,"team":team,"player_id":pid,"depth_rank":rank,
                 "depth_position":str(r.get("depth_position") or "").strip()}
            old=best.get(key)
            if old is None or rank<int(old["depth_rank"]): best[key]=rec

    # Strictly prior depth state by player.  All records in a given week receive
    # the same previous-week state; same-week team changes cannot leak into prev.
    bypid=defaultdict(lambda:defaultdict(list))
    for rec in best.values(): bypid[rec["player_id"]][(rec["season"],rec["week"])].append(rec)
    for pid,times in bypid.items():
        prev=None
        for t in sorted(times):
            group=times[t]
            for rec in group:
                rec["prev_depth_rank"]=int(prev["depth_rank"]) if prev else 0
                rec["prev_depth_team"]=str(prev["team"]) if prev else ""
                rec["prev_depth_position"]=str(prev.get("depth_position") or "") if prev else ""
            # choose the strongest role if duplicated across teams in a transaction week
            prev=sorted(group,key=lambda z:(int(z["depth_rank"]),str(z["team"])))[0]
    return best,{"rowsRead":rows_read,"uniquePlayerWeeks":len(best),"years":sorted(need)}


def attach_depth(rows: Sequence[dict[str,Any]], dmap: dict[tuple[int,int,str,str],dict[str,Any]]) -> list[dict[str,Any]]:
    out=[]
    for r0 in rows:
        r=dict(r0); season=int(r["season"]); week=int(r["week"]); team=normteam(r.get("team")); pid=str(r.get("player_id") or "")
        r["team"]=team; d=dmap.get((season,week,team,pid))
        if d:
            r.update({"depth_present":1,"depth_rank":d["depth_rank"],"depth_position":d.get("depth_position",""),
                      "prev_depth_rank":d.get("prev_depth_rank",0),"prev_depth_team":d.get("prev_depth_team",""),
                      "prev_depth_position":d.get("prev_depth_position","")})
        else:
            r.update({"depth_present":0,"depth_rank":0,"depth_position":"","prev_depth_rank":0,"prev_depth_team":"","prev_depth_position":""})
        prev=int(num(r.get("prev_depth_rank"))); rank=int(num(r.get("depth_rank")))
        r["prev_depth_present"]=1 if prev>0 else 0
        r["promoted_to_rank1"]=1 if rank==1 and prev>=2 else 0
        r["demoted_from_rank1"]=1 if prev==1 and rank>=2 else 0
        r["rank_improvement"]=max(0,prev-rank) if rank and prev else 0
        r["rank_demotion"]=max(0,rank-prev) if rank and prev else 0
        out.append(r)
    return out


def choose_role_l2(rows: Sequence[dict[str,Any]], cr) -> tuple[float,list[dict[str,Any]]]:
    results=[]
    for lam in cr.L2_GRID:
        vals=[]
        for year in (2021,2022,2023):
            train=[r for r in rows if int(r["season"])<year]; val=[r for r in rows if int(r["season"])==year]
            if not train or not val: continue
            m=cr.fit_correction(train,lam)
            mae=fmean(abs(float(r["actual_snap_share"])-m.predict(r,float(r["h012_center"]))) for r in val)
            vals.append(mae)
        if vals: results.append({"l2":lam,"folds":len(vals),"meanMAE":fmean(vals)})
    if not results: raise SystemExit("FAIL no role-correction L2 folds")
    results.sort(key=lambda x:(x["meanMAE"],x["l2"]))
    return float(results[0]["l2"]),results


def subset_report(rows: Sequence[dict[str,Any]]) -> dict[str,Any]:
    defs={
        "depthCovered":lambda r:int(num(r.get("depth_present")))==1,
        "rank1":lambda r:int(num(r.get("depth_rank")))==1,
        "rank2":lambda r:int(num(r.get("depth_rank")))==2,
        "rank3plus":lambda r:int(num(r.get("depth_rank")))>=3,
        "promotedToRank1":lambda r:int(num(r.get("promoted_to_rank1")))==1,
        "demotedFromRank1":lambda r:int(num(r.get("demoted_from_rank1")))==1,
        "week1":lambda r:int(num(r.get("week")))==1,
        "week1Rank1":lambda r:int(num(r.get("week")))==1 and int(num(r.get("depth_rank")))==1,
        "coldStart":lambda r:int(num(r.get("prior_games")))==0,
        "coldStartRank1":lambda r:int(num(r.get("prior_games")))==0 and int(num(r.get("depth_rank")))==1,
        "starterConflict":lambda r:int(num(r.get("depth_rank")))==1 and num(r.get("h012_center"))<.65,
        "backupConflict":lambda r:int(num(r.get("depth_rank")))>=2 and num(r.get("h012_center"))>=.65,
    }
    out={}
    for name,fn in defs.items():
        z=[r for r in rows if fn(r)]
        if not z: out[name]={"n":0}; continue
        h=metrics(z,"actual_snap_share","h012_center"); rr=metrics(z,"actual_snap_share","role_center")
        out[name]={"n":len(z),"h012MAE":h["mae"],"roleMAE":rr["mae"],"maeImprovement":h["mae"]-rr["mae"],
                   "h012Bias":h["biasPredMinusActual"],"roleBias":rr["biasPredMinusActual"]}
    return out


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); a=ap.parse_args(); root=Path(a.root).resolve()
    omega=root/"packages/models/nfl/omega"; sys.path.insert(0,str(omega))
    import exposure_role_challenger as er
    import current_role_snap_distribution_challenger as cr
    import snap_share_distribution_challenger as sd
    import xto_xtc_baseline as xb

    # Frozen historical OMEGA foundation.
    fptr=root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION"; eptr=root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE"
    dptr=root/"data/raw/nfl/omega/CURRENT_DEPTH_CHART_SOURCE_AUDIT"; sdp=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_SNAP_DISTRIBUTION_CHALLENGER"
    for p in (fptr,eptr,dptr,sdp):
        if not p.exists(): raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    sid=fptr.read_text().strip()
    if eptr.read_text().strip()!=sid: raise SystemExit("FAIL OMEGA foundation/exposure pointer mismatch")
    if sdp.read_text().strip()!=sid: raise SystemExit("FAIL 0.2.3 snap distribution source mismatch")
    exposure=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    exrows=rcsv(exposure/"omega_tackle_exposure_player_games.csv")
    if any(int(num(r.get("season")))==SEALED_YEAR for r in exrows): raise SystemExit("FAIL 2025 exposure row read")
    team_snaps=xb.estimate_team_defensive_snaps(exrows); preg=er.build_exposure_pregame_rows(exrows,team_snaps)
    if any(int(r["season"])==SEALED_YEAR for r in preg): raise SystemExit("FAIL 2025 pregame row emitted")

    aid=dptr.read_text().strip(); adir=root/"data/raw/nfl/omega/depth_chart_source_audits"/aid
    audit=json.loads((adir/"OMEGA_DEPTH_CHART_SOURCE_AUDIT.json").read_text())
    dmap,dmeta=load_depth_history(adir,audit); rows=attach_depth(preg,dmap)

    # Exact H012 selection remains pre-2024 and unchanged.
    h_l2,h_search=er.choose_l2(preg)
    h_oof: dict[tuple[int,int,str,str,str],float]={}
    correction_rows=[]
    for year in DEV_YEARS:
        train=[r for r in preg if 2017<=int(r["season"])<year]; val=[r for r in rows if int(r["season"])==year]
        if not train or not val: raise SystemExit(f"FAIL H012 chronology for {year}")
        hm=er.fit_ridge(train,h_l2)
        for r in val:
            c=hm.predict(r); key=(int(r["season"]),int(r["week"]),r["team"],r["player_id"],r["game_id"]); h_oof[key]=c
            z=dict(r); z["h012_center"]=c; correction_rows.append(z)

    role_l2,role_search=choose_role_l2(correction_rows,cr)

    # Chronological role-center predictions used to calibrate uncertainty.
    role_oof=[]; role_obs=[]
    for year in DIST_CAL_YEARS:
        train=[r for r in correction_rows if int(r["season"])<year]; val=[r for r in correction_rows if int(r["season"])==year]
        if not train or not val: raise SystemExit(f"FAIL role chronology for {year}")
        rm=cr.fit_correction(train,role_l2)
        for r in val:
            c=rm.predict(r,float(r["h012_center"])); z=dict(r); z["role_center"]=c; role_oof.append(z); role_obs.append(cr.make_role_observation(z,c))
    rcal=cr.RoleResidualCalibrator(role_obs,min_pool=cr.MIN_POOL)

    # Final point models use only data through 2023; 2024 is untouched until scoring.
    h_final=er.fit_ridge([r for r in preg if 2017<=int(r["season"])<=2023],h_l2)
    role_final=cr.fit_correction(correction_rows,role_l2)
    val2024=[r for r in rows if int(r["season"])==TEST_YEAR]
    if not val2024: raise SystemExit("FAIL no 2024 validation rows")

    # Existing 0.2.3 H012 distribution is the incumbent probabilistic baseline.
    sdir=root/"data/models/nfl/omega_tackle_023_snap_distribution"/sid
    base_rows=rcsv(sdir/"omega_2024_snap_share_distribution_validation.csv")
    bmap={(r["game_id"],normteam(r["team"]),r["player_id"]):r for r in base_rows}
    scored=[]
    for r in val2024:
        key=(r["game_id"],normteam(r["team"]),r["player_id"]); b=bmap.get(key)
        if b is None: raise SystemExit(f"FAIL missing 0.2.3 baseline row {key}")
        hc=h_final.predict(r); rc=role_final.predict(r,hc); actual=float(r["actual_snap_share"])
        if abs(hc-num(b.get("h012_point_snap_share")))>1e-8: raise SystemExit(f"FAIL H012 point drift {key}")
        rd=rcal.summarize(r,rc,actual)
        z=dict(r); z.update({"h012_center":hc,"role_center":rc,"role_correction":rc-hc,
                             "baseline_crps":num(b.get("dist_crps")),"baseline_dist_mean":num(b.get("dist_distribution_mean")),
                             "baseline_brier_ge_035":num(b.get("dist_brier_ge_035")),"baseline_brier_ge_065":num(b.get("dist_brier_ge_065")),
                             "baseline_brier_ge_085":num(b.get("dist_brier_ge_085")),
                             "baseline_covered_50":num(b.get("dist_covered_50")),"baseline_covered_80":num(b.get("dist_covered_80")),"baseline_covered_90":num(b.get("dist_covered_90")),
                             "baseline_width_50":num(b.get("dist_width_50")),"baseline_width_80":num(b.get("dist_width_80")),"baseline_width_90":num(b.get("dist_width_90"))})
        for k,v in rd.items(): z[f"role_dist_{k}"]=v
        ts=num(b.get("predicted_team_defensive_snaps")); rate=num(b.get("shrunk_credit_rate_per_snap"))
        z["actual_xtc"]=num(b.get("actual_xtc")); z["h012_point_xtc"]=hc*ts*rate; z["role_point_xtc"]=rc*ts*rate
        z["h012_dist_mean_xtc"]=num(b.get("dist_mean_xtc")); z["role_dist_mean_xtc"]=num(rd.get("distribution_mean"))*ts*rate
        scored.append(z)
    if len(scored)!=len(base_rows): raise SystemExit(f"FAIL 2024 row count mismatch role={len(scored)} baseline={len(base_rows)}")

    ph=metrics(scored,"actual_snap_share","h012_center"); pr=metrics(scored,"actual_snap_share","role_center")
    xh=metrics(scored,"actual_xtc","h012_point_xtc"); xr=metrics(scored,"actual_xtc","role_point_xtc")
    xhd=metrics(scored,"actual_xtc","h012_dist_mean_xtc"); xrd=metrics(scored,"actual_xtc","role_dist_mean_xtc")
    crps_h=fmean(num(r.get("baseline_crps")) for r in scored); crps_r=fmean(num(r.get("role_dist_crps")) for r in scored)
    brier_h=threshold_brier(scored,"baseline"); brier_r=threshold_brier(scored,"role_dist")
    boot=game_cluster_bootstrap(scored,"role_dist_crps","baseline_crps")
    sub=subset_report(scored); cov=sum(int(num(r.get("depth_present"))) for r in scored)/len(scored)
    int_h=interval_summary(scored,"baseline"); int_r=interval_summary(scored,"role_dist")
    ci=boot.get("improvementCI95",[0,0]); conflict=sub.get("starterConflict",{})
    strong=(pr["mae"]<ph["mae"] and crps_r<crps_h and brier_r<brier_h and ci[0]>0 and (conflict.get("n",0)<10 or conflict.get("maeImprovement",0)>0))
    if strong: verdict="H012R_CURRENT_ROLE_DISTRIBUTION_STRONG_PASS"
    elif pr["mae"]<ph["mae"] and crps_r<crps_h: verdict="H012R_CURRENT_ROLE_DISTRIBUTION_DIRECTIONAL_PASS"
    elif pr["mae"]>=ph["mae"] and crps_r>=crps_h: verdict="H012R_CURRENT_ROLE_DISTRIBUTION_FAIL"
    else: verdict="H012R_CURRENT_ROLE_DISTRIBUTION_MIXED"

    coef=sorted(({"feature":n,"standardizedCoefficient":c} for n,c in zip(cr.FEATURE_NAMES,role_final.coefficients)),key=lambda x:abs(x["standardizedCoefficient"]),reverse=True)
    report={
      "schemaVersion":SCHEMA,"version":cr.VERSION,"lineage":cr.LINEAGE,"generatedAt":now(),"sourceSnapshotId":sid,"depthAuditId":aid,
      "targetDefinition":"defensive snap share conditional on recording at least one defensive snap; availability/no-play probability separate",
      "integrity":{"omega2025RowsRead":0,"depthChart2025RowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,"frozenOmegaModified":False,"tackleRateChanged":False,"teamSnapModelChanged":False,"2024UsedForFit":False},
      "depthHistory":dmeta | {"validation2024Coverage":cov,"joinKey":"season+week+normalized_team+gsis_id","rankSemantics":"depth_team 1/2/3+"},
      "chronology":{"h012SelectedL2":h_l2,"h012L2Search":h_search,"h012FinalFitYears":list(range(2017,2024)),"roleResidualDevelopmentYears":list(DEV_YEARS),"roleDistributionCalibrationYears":list(DIST_CAL_YEARS),"roleSelectedL2":role_l2,"roleL2Search":role_search,"diagnosticTestYear":TEST_YEAR,"sealedHoldout":SEALED_YEAR},
      "method":{"anchor":"H012 historical usage point model","roleLayer":"ridge correction to chronological H012 residual using current weekly depth rank and strictly-prior rank transition state","missingDepthFallback":"exact H012","distribution":"empirical role-aware residual pools","minPool":cr.MIN_POOL,"roleFeatureNames":list(cr.FEATURE_NAMES)},
      "validation2024":{"rows":len(scored),"pointSnapShare":{"h012":ph,"h012CurrentRole":pr,"maeImprovement":ph["mae"]-pr["mae"]},
                        "distribution":{"h012D_CRPS":crps_h,"currentRoleCRPS":crps_r,"crpsImprovement":crps_h-crps_r,"h012D_Brier":brier_h,"currentRoleBrier":brier_r,"brierImprovement":brier_h-brier_r,"gameClusterBootstrap":boot,"h012DIntervals":int_h,"currentRoleIntervals":int_r},
                        "subsets":sub,"downstreamExposureOnlyXTC":{"h012Point":xh,"currentRolePoint":xr,"h012DistributionMean":xhd,"currentRoleDistributionMean":xrd}},
      "topStandardizedRoleCoefficients":coef[:20],"verdict":verdict,
      "interpretation":"2024 is diagnostic confirmation. Positive results justify prospective 2026 role-aware snap-distribution freezes; they do not alter frozen OMEGA or consume 2025.",
    }

    outbase=root/"data/models/nfl/omega_tackle_027_current_role_snap_distribution"; oid=f"{sid}__{aid}"; out=outbase/oid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable OMEGA 0.2.7 output: {out}")
    st=outbase/("."+oid+".staging"); st.mkdir(parents=True,exist_ok=False)
    try:
        wcsv(st/"omega_role_correction_chronological_training.csv",correction_rows)
        wcsv(st/"omega_role_distribution_oof.csv",role_oof)
        wcsv(st/"omega_2024_current_role_snap_distribution_validation.csv",scored)
        wcsv(st/"omega_current_role_distribution_pool_summary.csv",rcal.pool_summary())
        (st/"omega_current_role_model.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"depthAuditId":aid,"h012SelectedL2":h_l2,"roleSelectedL2":role_l2,"roleModel":role_final.to_dict(),"topStandardizedCoefficients":coef},indent=2)+"\n")
        (st/"OMEGA_0.2.7_CURRENT_ROLE_SNAP_DISTRIBUTION_AUDIT.json").write_text(json.dumps(report,indent=2)+"\n")
        md=["# OMEGA 0.2.7 — Current-Role Snap-Share Distribution Challenger","","**RESEARCH ONLY · FROZEN OMEGA UNCHANGED · 2025 SEALED · MARKET DATA 0**","",
            f"Source snapshot: `{sid}`  ",f"Depth audit: `{aid}`  ",f"Generated: {report['generatedAt']}","","## 2024 diagnostic result","",
            f"- Depth-chart coverage: **{cov:.1%}**",f"- Point MAE: H012 **{ph['mae']:.5f}** → current-role **{pr['mae']:.5f}** · improvement **{ph['mae']-pr['mae']:+.5f}**",
            f"- CRPS: H012D **{crps_h:.5f}** → current-role **{crps_r:.5f}** · improvement **{crps_h-crps_r:+.5f}**",
            f"- Role-threshold Brier: H012D **{brier_h:.5f}** → current-role **{brier_r:.5f}** · improvement **{brier_h-brier_r:+.5f}**",
            f"- CRPS game-cluster bootstrap 95% CI: **[{ci[0]:+.5f}, {ci[1]:+.5f}]**",f"- Exposure-only xTC point MAE: H012 **{xh['mae']:.4f}** → current-role **{xr['mae']:.4f}**","","## Critical subsets",""]
        for name in ("starterConflict","backupConflict","promotedToRank1","demotedFromRank1","week1Rank1","coldStartRank1"):
            q=sub.get(name,{})
            if q.get("n",0): md.append(f"- {name}: n={q['n']} · H012 MAE **{q['h012MAE']:.4f}** → role **{q['roleMAE']:.4f}** · improvement **{q['maeImprovement']:+.4f}**")
        md += ["","## Verdict","",f"**{verdict}**","",report["interpretation"],""]
        (st/"OMEGA_0.2.7_CURRENT_ROLE_SNAP_DISTRIBUTION_AUDIT.md").write_text("\n".join(md))
        files=[]
        for p in sorted(st.iterdir()):
            if p.is_file(): files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
        (st/"OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"depthAuditId":aid,"createdAt":now(),"files":files},indent=2)+"\n")
        os.replace(st,out); ptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_CURRENT_ROLE_SNAP_DISTRIBUTION_CHALLENGER"; tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(oid+"\n"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(st,ignore_errors=True); raise

    print("OMEGA 0.2.7 — CURRENT-ROLE SNAP-SHARE DISTRIBUTION CHALLENGER")
    print(f"PASS OMEGA source {sid} · depth audit {aid}")
    print("PASS 2025 rows read 0 · market fields 0 · frozen OMEGA writes 0")
    print(f"2024 depth coverage {cov:.1%} · rows {len(scored)}")
    print(f"2024 point MAE H012 {ph['mae']:.5f} -> ROLE {pr['mae']:.5f} · improvement {ph['mae']-pr['mae']:+.5f}")
    print(f"2024 CRPS H012D {crps_h:.5f} -> ROLE {crps_r:.5f} · improvement {crps_h-crps_r:+.5f}")
    print(f"2024 threshold Brier H012D {brier_h:.5f} -> ROLE {brier_r:.5f} · improvement {brier_h-brier_r:+.5f}")
    print(f"CRPS game-cluster bootstrap 95% CI {ci}")
    for name in ("starterConflict","backupConflict","promotedToRank1","demotedFromRank1","week1Rank1","coldStartRank1"):
        q=sub.get(name,{})
        if q.get("n",0): print(f"{name}: n {q['n']} · MAE {q['h012MAE']:.4f} -> {q['roleMAE']:.4f} · improvement {q['maeImprovement']:+.4f}")
    print(f"VERDICT: {verdict}")
    print(f"REPORT: {out/'OMEGA_0.2.7_CURRENT_ROLE_SNAP_DISTRIBUTION_AUDIT.md'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

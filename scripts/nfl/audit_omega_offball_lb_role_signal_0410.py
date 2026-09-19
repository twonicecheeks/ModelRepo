#!/usr/bin/env python3
"""OMEGA 0.41.0 — clean off-ball-LB current-role/depth signal audit.

Diagnostic only. No model fit.

Attaches immutable historical nflverse weekly depth-chart state (2019-2024) to the
chronological frozen H012/H008 control rows and asks whether clean explicit ILB/MLB
snap-share errors concentrate in pregame role conflicts:

- STARTER_CONFLICT: depth rank 1 while H012 snap share < 0.65
- BACKUP_CONFLICT: depth rank >=2 while H012 snap share >= 0.65
- PROMOTED_TO_R1
- DEMOTED_FROM_R1
- STABLE_R1 / STABLE_BACKUP

For each slice we report H012 snap MAE/bias, direction of residual, and the
historical xTC headroom from replacing only snap share with the realized share while
keeping frozen H008 opportunity/rates. Oracle values are diagnostic only.

2025 remains sealed. 2026 is not read. Markets are not read.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from math import sqrt
import argparse,csv,json,os,sys,uuid


def rcsv(path:Path):
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))


def num(v,d=0.0):
    try:
        if v in (None,""):return float(d)
        x=float(v);return x if x==x else float(d)
    except:return float(d)


def metrics(rows,actual,pred):
    if not rows:return {"n":0}
    e=[num(r.get(pred))-num(r.get(actual)) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(x) for x in e),"rmse":sqrt(fmean(x*x for x in e)),
            "biasPredMinusActual":fmean(e)}


def role_state(r):
    rank=int(num(r.get("depth_rank")));prev=int(num(r.get("prev_depth_rank")))
    h=num(r.get("predicted_snap_share"))
    if rank<=0:return "NO_DEPTH"
    if rank==1 and h<.65:return "STARTER_CONFLICT"
    if rank>=2 and h>=.65:return "BACKUP_CONFLICT"
    if rank==1 and prev>=2:return "PROMOTED_TO_R1"
    if prev==1 and rank>=2:return "DEMOTED_FROM_R1"
    if rank==1:return "STABLE_R1"
    return "STABLE_BACKUP"


def enrich(rows):
    out=[]
    for r in rows:
        z=dict(r);state=role_state(z);z["audit_role_state"]=state
        pred=max(0.0,min(1.0,num(z.get("predicted_snap_share"))))
        actual=max(0.0,min(1.0,num(z.get("actual_snap_share"))))
        z["audit_snap_residual_actual_minus_pred"]=actual-pred
        base=0.0;oracle=0.0
        for f in ("RUSH","COMPLETE_PASS","SCRAMBLE","SACK","OTHER_PASS"):
            opp=max(0.0,num(z.get(f"pred_opp_{f}")));rate=max(0.0,num(z.get(f"shrunk_rate_{f}")))
            base+=opp*pred*rate;oracle+=opp*actual*rate
        z["audit_control_xtc_rebuilt"]=base
        z["audit_snap_oracle_xtc"]=oracle
        out.append(z)
    return out


def summarize(rows):
    if not rows:return {"n":0}
    snap=metrics(rows,"actual_snap_share","predicted_snap_share")
    base=metrics(rows,"actual_xtc","audit_control_xtc_rebuilt")
    oracle=metrics(rows,"actual_xtc","audit_snap_oracle_xtc")
    residuals=[num(r.get("audit_snap_residual_actual_minus_pred")) for r in rows]
    positive=sum(x>0 for x in residuals)/len(residuals)
    negative=sum(x<0 for x in residuals)/len(residuals)
    return {
        "n":len(rows),"snap":snap,
        "meanSnapResidualActualMinusPred":fmean(residuals),
        "positiveResidualRate":positive,"negativeResidualRate":negative,
        "controlXtc":base,"snapOracleXtc":oracle,
        "snapOracleMaeGain":base["mae"]-oracle["mae"],
    }


def grouped(rows,key):
    g=defaultdict(list)
    for r in rows:g[str(r.get(key) or "UNKNOWN")].append(r)
    return {k:summarize(v) for k,v in sorted(g.items())}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--data-root",default="")
    ap.add_argument("--evaluation-seasons",default="2021,2022,2023,2024")
    a=ap.parse_args();root=Path(a.root).expanduser().resolve()
    data_root=Path(a.data_root).expanduser().resolve() if a.data_root else root
    years=[int(x) for x in a.evaluation_seasons.split(",") if x.strip()]
    if years!=sorted(years) or not years or min(years)<2019 or max(years)>=2025:
        raise ValueError("evaluation seasons must be chronological depth-covered development years <2025")

    sys.path[:0]=[str(root/"packages/models/nfl/omega"),str(root/"scripts/nfl")]
    import frozen_spec as fs
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import lb_edge_archetype_0363 as arch
    import analyze_omega_position_specific_challenger_0360 as base
    import build_omega_tackle_027_current_role_snap_distribution as rolebuild

    fptr=data_root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    dptr=data_root/"data/raw/nfl/omega/CURRENT_DEPTH_CHART_SOURCE_AUDIT"
    for p in (fptr,dptr):
        if not p.exists():raise FileNotFoundError(p)
    sid=fptr.read_text().strip()
    foundation=data_root/"data/normalized/nfl/omega_tackle"/sid
    exdir=data_root/"data/normalized/nfl/omega_tackle_exposure"/sid
    histp=rcsv(foundation/"omega_tackle_play_opportunities.csv")
    histe=rcsv(foundation/"omega_tackle_credit_events.csv")
    histex=rcsv(exdir/"omega_tackle_exposure_player_games.csv")
    if any(int(num(r.get("season")))>=2025 for r in histp+histe+histex):
        raise ValueError("sealed/prospective row entered 0.41 audit")

    teamout=xb.aggregate_team_game_outcomes(histp,histex)
    teamrows=xb.build_team_pregame_rows(teamout)
    team_snaps=xb.estimate_team_defensive_snaps(histex)
    exposure_rows=er.build_exposure_pregame_rows(histex,team_snaps)
    fam_out=tf.aggregate_team_family_opportunities(histp)
    fam_pred=tf.build_team_family_share_pregame_rows(fam_out)
    fam_map=base.family_share_map(fam_pred,fs.FAMILIES)
    pfc=tf.aggregate_player_family_credits(histe)
    topology=tf.build_player_topology_rows(histex,fam_out,pfc,team_snaps)

    aid=dptr.read_text().strip();adir=data_root/"data/raw/nfl/omega/depth_chart_source_audits"/aid
    audit=json.loads((adir/"OMEGA_DEPTH_CHART_SOURCE_AUDIT.json").read_text())
    dmap,dmeta=rolebuild.load_depth_history(adir,audit)

    pooled=[];folds=[]
    for year in years:
        control,_,_=base.score_for_fit_year(
            fit_end=year-1,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
            fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
        )
        clean=[r for r in control if int(r["season"])==year and arch.explicit_role_label(r)=="OFFBALL_LB"]
        attached=rolebuild.attach_depth(clean,dmap)
        e=enrich(attached);pooled.extend(e)
        covered=[r for r in e if int(num(r.get("depth_present")))==1]
        states=grouped(e,"audit_role_state")
        fold={"season":year,"rows":len(e),"depthCovered":len(covered),
              "depthCoverage":len(covered)/len(e) if e else None,
              "overall":summarize(e),"states":states}
        folds.append(fold)
        sc=states.get("STARTER_CONFLICT",{"n":0});bc=states.get("BACKUP_CONFLICT",{"n":0})
        print(
            f"PASS {year} · LB {len(e):,} · depth {len(covered)/len(e):.1%} · "
            f"starter-conflict n {sc.get('n',0)} residual {sc.get('meanSnapResidualActualMinusPred',0):+.3f} · "
            f"backup-conflict n {bc.get('n',0)} residual {bc.get('meanSnapResidualActualMinusPred',0):+.3f}"
        )

    states=grouped(pooled,"audit_role_state")
    covered=[r for r in pooled if int(num(r.get("depth_present")))==1]
    overall=summarize(pooled)
    sc=states.get("STARTER_CONFLICT",{"n":0})
    bc=states.get("BACKUP_CONFLICT",{"n":0})

    starter_signal=bool(
        sc.get("n",0)>=30 and sc.get("meanSnapResidualActualMinusPred",0)>=.10
        and sc.get("positiveResidualRate",0)>=.65
    )
    backup_signal=bool(
        bc.get("n",0)>=30 and bc.get("meanSnapResidualActualMinusPred",0)<=-.10
        and bc.get("negativeResidualRate",0)>=.65
    )
    material=starter_signal or backup_signal
    conclusion="DEPTH_ROLE_CONFLICT_SIGNAL_MATERIAL" if material else "DEPTH_ROLE_CONFLICT_SIGNAL_WEAK"
    next_gate="BUILD_0.41_DEPTH_AWARE_LB_EXPOSURE_CHALLENGER" if material else "STOP_DEPTH_ROLE_PATH_AND_AUDIT_OTHER_EXPOSURE_SIGNALS"

    report={
        "schemaVersion":"OMEGA_OFFBALL_LB_CURRENT_ROLE_SIGNAL_AUDIT_0.41.0",
        "createdAt":datetime.now(timezone.utc).isoformat(),"sourceSnapshotId":sid,"depthAuditId":aid,
        "codeRoot":str(root),"dataRoot":str(data_root),
        "evaluationSeasons":years,"sealedHoldoutSeason":2025,"prospectiveSeason":2026,
        "holdoutOpened":False,"prospectiveRowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,
        "depthHistory":dmeta,"rows":len(pooled),"depthCoveredRows":len(covered),
        "depthCoverage":len(covered)/len(pooled) if pooled else None,
        "overall":overall,"states":states,"folds":folds,
        "decisionRule":{
            "starterConflict":"n>=30 AND mean(actual-pred)>=+0.10 AND positive residual rate>=65%",
            "backupConflict":"n>=30 AND mean(actual-pred)<=-0.10 AND negative residual rate>=65%",
            "material":"either conflict rule passes",
        },
        "starterConflictSignalPass":starter_signal,"backupConflictSignalPass":backup_signal,
        "conclusion":conclusion,"nextGate":next_gate,
        "integrity":{"diagnosticOnly":True,"modelFit":False,"oracleUsedForAttributionOnly":True,
                     "productionPromotion":False,"frozenOmegaMutation":False},
    }

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=data_root/"data/models/nfl/omega_lb_role_signal_audit_0410"/run_id;out.mkdir(parents=True,exist_ok=False)
    jp=out/"OMEGA_0.41.0_LB_CURRENT_ROLE_SIGNAL_AUDIT.json";jp.write_text(json.dumps(report,indent=2)+"\n")
    lines=[
        "OMEGA 0.41.0 — OFF-BALL LB CURRENT-ROLE/DEPTH SIGNAL AUDIT","",
        f"Source snapshot: {sid}",f"Depth audit: {aid}",
        "2025 SEALED · 2026 NOT READ · market fields 0 · model fit 0","",
        f"CONCLUSION: {conclusion}",f"NEXT GATE: {next_gate}","",
        f"POOLED rows {len(pooled):,} · depth coverage {len(covered)/len(pooled):.1%}",
        f"H012 snap MAE {overall['snap']['mae']:.5f} · snap-oracle xTC gain {overall['snapOracleMaeGain']:+.4f}","",
        "ROLE STATES",
    ]
    for name,z in states.items():
        lines.append(
            f"  {name}: n {z['n']:,} · snap MAE {z['snap']['mae']:.4f} · "
            f"mean actual-pred {z['meanSnapResidualActualMinusPred']:+.4f} · "
            f"+resid {z['positiveResidualRate']:.1%} · -resid {z['negativeResidualRate']:.1%} · "
            f"snap-oracle xTC gain {z['snapOracleMaeGain']:+.4f}"
        )
    lines += ["","SIGNAL GATES",
              f"  starter conflict: {'PASS' if starter_signal else 'FAIL'}",
              f"  backup conflict: {'PASS' if backup_signal else 'FAIL'}","",
              "No model is fit or promoted by this command.",f"REPORT: {jp}"]
    tp=out/"OMEGA_0.41.0_LB_CURRENT_ROLE_SIGNAL_AUDIT.txt";tp.write_text("\n".join(lines)+"\n")
    ptr=data_root/"data/models/nfl/CURRENT_OMEGA_LB_ROLE_SIGNAL_AUDIT_0410";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n");os.replace(tmp,ptr)
    print();print(tp.read_text())
    print("PASS OMEGA 0.41 role-signal audit · diagnostic only · production unchanged")
    return 0

if __name__=="__main__":raise SystemExit(main())

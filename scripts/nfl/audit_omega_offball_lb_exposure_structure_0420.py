#!/usr/bin/env python3
"""OMEGA 0.42.0 — clean off-ball-LB exposure residual structure audit.

Diagnostic only. No model fit.

After 0.41 rejected simple depth-rank conflict as a useful exposure signal, this
audit asks whether H012 snap-share residuals are systematically predictable from
pregame-observable state already available before kickoff:

- H012 role band
- recent snap trend (last1 - last4)
- recent snap volatility (last4 std)
- prior-game history length
- clean off-ball-LB room size
- within-room predicted snap competition
- depth coverage state

A slice is considered materially directional only if:
  n >= 100
  |mean(actual - predicted)| >= 0.05
  residual direction rate >= 65%
  direction is consistent in at least 3 of 4 chronological seasons

If such a slice exists, the next gate is a preregistered piecewise/calibration
challenger on the identified observable state. If none exists, large H012 oracle
headroom is treated as mostly nonrecoverable with the current pregame information
set and the next research target shifts toward new external role/injury inputs.

2025 sealed. 2026 not read. Market fields not read.
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


def role_band(v):
    x=num(v)
    if x<.35:return "LOW_<35"
    if x<.65:return "ROTATION_35-65"
    if x<.85:return "STARTER_65-85"
    return "EVERY_DOWN_85+"


def trend_band(v):
    x=num(v)
    if x<=-.15:return "DOWN_15+"
    if x<=-.05:return "DOWN_05-15"
    if x<.05:return "FLAT_05"
    if x<.15:return "UP_05-15"
    return "UP_15+"


def volatility_band(v):
    x=num(v)
    if x<.05:return "STD_<05"
    if x<.10:return "STD_05-10"
    if x<.20:return "STD_10-20"
    return "STD_20+"


def history_band(v):
    n=int(num(v))
    if n<=1:return "0-1"
    if n<=4:return "2-4"
    if n<=8:return "5-8"
    return "9+"


def room_count_band(v):
    n=int(num(v))
    if n<=1:return "ONE"
    if n==2:return "TWO"
    return "THREE_PLUS"


def competition_band(v):
    x=num(v)
    if x<.35:return "OTHER_<35"
    if x<.65:return "OTHER_35-65"
    if x<.85:return "OTHER_65-85"
    return "OTHER_85+"


def metrics(rows,actual,pred):
    if not rows:return {"n":0}
    e=[num(r.get(pred))-num(r.get(actual)) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(x) for x in e),"rmse":sqrt(fmean(x*x for x in e)),
            "biasPredMinusActual":fmean(e)}


def summarize(rows):
    if not rows:return {"n":0}
    residual=[num(r.get("snap_residual_actual_minus_pred")) for r in rows]
    positive=sum(x>0 for x in residual)/len(residual)
    negative=sum(x<0 for x in residual)/len(residual)
    base=metrics(rows,"actual_snap_share","predicted_snap_share")
    return {
        "n":len(rows),"snap":base,
        "meanResidualActualMinusPred":fmean(residual),
        "positiveResidualRate":positive,"negativeResidualRate":negative,
        "meanAbsResidual":fmean(abs(x) for x in residual),
    }


def grouped(rows,key):
    g=defaultdict(list)
    for r in rows:g[str(r.get(key) or "UNKNOWN")].append(r)
    return {k:summarize(v) for k,v in sorted(g.items())}


def direction(z):
    r=num(z.get("meanResidualActualMinusPred"))
    if r>0:return 1
    if r<0:return -1
    return 0


def material_slice(name, pooled, yearly):
    if pooled.get("n",0)<100:return False
    mean=num(pooled.get("meanResidualActualMinusPred"))
    if abs(mean)<.05:return False
    rate=pooled.get("positiveResidualRate",0) if mean>0 else pooled.get("negativeResidualRate",0)
    if rate<.65:return False
    want=1 if mean>0 else -1
    consistent=sum(1 for y in yearly.values() if y.get("n",0)>0 and direction(y)==want)
    return consistent>=3


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--data-root",default="")
    ap.add_argument("--evaluation-seasons",default="2021,2022,2023,2024")
    a=ap.parse_args();root=Path(a.root).expanduser().resolve()
    data_root=Path(a.data_root).expanduser().resolve() if a.data_root else root
    years=[int(x) for x in a.evaluation_seasons.split(",") if x.strip()]
    if years!=sorted(years) or len(years)<3 or min(years)<2018 or max(years)>=2025:
        raise ValueError("evaluation seasons must be chronological development years <2025")

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
        raise ValueError("sealed/prospective row entered 0.42 audit")

    teamout=xb.aggregate_team_game_outcomes(histp,histex)
    teamrows=xb.build_team_pregame_rows(teamout)
    team_snaps=xb.estimate_team_defensive_snaps(histex)
    exposure_rows=er.build_exposure_pregame_rows(histex,team_snaps)
    exp_map={(str(r.get("game_id") or ""),str(r.get("team") or ""),str(r.get("player_id") or "")):r for r in exposure_rows}
    fam_out=tf.aggregate_team_family_opportunities(histp)
    fam_pred=tf.build_team_family_share_pregame_rows(fam_out)
    fam_map=base.family_share_map(fam_pred,fs.FAMILIES)
    pfc=tf.aggregate_player_family_credits(histe)
    topology=tf.build_player_topology_rows(histex,fam_out,pfc,team_snaps)

    aid=dptr.read_text().strip();adir=data_root/"data/raw/nfl/omega/depth_chart_source_audits"/aid
    audit=json.loads((adir/"OMEGA_DEPTH_CHART_SOURCE_AUDIT.json").read_text())
    dmap,dmeta=rolebuild.load_depth_history(adir,audit)

    pooled=[];by_year_rows={}
    for year in years:
        control,_,_=base.score_for_fit_year(
            fit_end=year-1,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
            fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
        )
        clean=[r for r in control if int(r["season"])==year and arch.explicit_role_label(r)=="OFFBALL_LB"]
        attached=rolebuild.attach_depth(clean,dmap)

        rooms=defaultdict(list)
        for r in attached:
            rooms[(str(r.get("game_id") or ""),str(r.get("team") or ""))].append(r)

        rows=[]
        for r in attached:
            key=(str(r.get("game_id") or ""),str(r.get("team") or ""),str(r.get("player_id") or ""))
            e=exp_map.get(key,{})
            z=dict(r)
            pred=num(r.get("predicted_snap_share"));actual=num(r.get("actual_snap_share"))
            z["snap_residual_actual_minus_pred"]=actual-pred
            z["audit_role_band"]=role_band(pred)
            z["audit_trend_band"]=trend_band(e.get("last1_minus_last4"))
            z["audit_volatility_band"]=volatility_band(e.get("last4_snap_share_std"))
            z["audit_history_band"]=history_band(r.get("prior_games"))
            room=rooms[(str(r.get("game_id") or ""),str(r.get("team") or ""))]
            z["audit_room_count"]=len(room)
            z["audit_room_count_band"]=room_count_band(len(room))
            others=[num(x.get("predicted_snap_share")) for x in room if str(x.get("player_id") or "")!=str(r.get("player_id") or "")]
            mx=max(others) if others else 0.0
            z["audit_max_other_predicted_snap"]=mx
            z["audit_competition_band"]=competition_band(mx)
            z["audit_depth_state"]="DEPTH_PRESENT" if int(num(r.get("depth_present")))==1 else "NO_DEPTH"
            z["audit_last1_minus_last4"]=num(e.get("last1_minus_last4"))
            z["audit_last4_snap_share_std"]=num(e.get("last4_snap_share_std"))
            rows.append(z)
        by_year_rows[year]=rows;pooled.extend(rows)
        print(
            f"PASS {year} · LB {len(rows):,} · mean residual {fmean(num(r['snap_residual_actual_minus_pred']) for r in rows):+.4f} · "
            f"MAE {metrics(rows,'actual_snap_share','predicted_snap_share')['mae']:.4f}"
        )

    dimensions={
        "roleBand":"audit_role_band",
        "trendBand":"audit_trend_band",
        "volatilityBand":"audit_volatility_band",
        "historyBand":"audit_history_band",
        "roomCount":"audit_room_count_band",
        "competition":"audit_competition_band",
        "depthState":"audit_depth_state",
    }

    pooled_groups={name:grouped(pooled,key) for name,key in dimensions.items()}
    yearly_groups={year:{name:grouped(rows,key) for name,key in dimensions.items()} for year,rows in by_year_rows.items()}

    candidates=[]
    for dim,pgr in pooled_groups.items():
        for label,pz in pgr.items():
            yz={str(y):yearly_groups[y][dim].get(label,{"n":0}) for y in years}
            passed=material_slice(f"{dim}:{label}",pz,yz)
            if passed:
                candidates.append({
                    "dimension":dim,"slice":label,"pooled":pz,"byYear":yz,
                    "absMeanResidual":abs(num(pz.get("meanResidualActualMinusPred"))),
                })
    candidates.sort(key=lambda x:(-x["absMeanResidual"],-x["pooled"]["n"],x["dimension"],x["slice"]))

    conclusion="OBSERVABLE_EXPOSURE_RESIDUAL_STRUCTURE_FOUND" if candidates else "NO_STRONG_OBSERVABLE_EXPOSURE_RESIDUAL_STRUCTURE"
    next_gate="BUILD_0.42_PREREGISTERED_EXPOSURE_CALIBRATION_CHALLENGER" if candidates else "SEEK_NEW_EXTERNAL_PREGAME_ROLE_OR_INJURY_INPUTS"

    report={
        "schemaVersion":"OMEGA_OFFBALL_LB_EXPOSURE_RESIDUAL_STRUCTURE_AUDIT_0.42.0",
        "createdAt":datetime.now(timezone.utc).isoformat(),"sourceSnapshotId":sid,"depthAuditId":aid,
        "codeRoot":str(root),"dataRoot":str(data_root),
        "evaluationSeasons":years,"sealedHoldoutSeason":2025,"prospectiveSeason":2026,
        "holdoutOpened":False,"prospectiveRowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,
        "rows":len(pooled),"overall":summarize(pooled),"dimensions":pooled_groups,
        "yearlyDimensions":yearly_groups,"materialCandidates":candidates,
        "decisionRule":"n>=100; |mean actual-pred|>=0.05; matching residual direction >=65%; same direction in >=3 evaluation seasons",
        "conclusion":conclusion,"nextGate":next_gate,
        "integrity":{"diagnosticOnly":True,"modelFit":False,"productionPromotion":False,"frozenOmegaMutation":False},
    }

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=data_root/"data/models/nfl/omega_lb_exposure_structure_audit_0420"/run_id;out.mkdir(parents=True,exist_ok=False)
    jp=out/"OMEGA_0.42.0_LB_EXPOSURE_RESIDUAL_STRUCTURE_AUDIT.json";jp.write_text(json.dumps(report,indent=2)+"\n")
    lines=[
        "OMEGA 0.42.0 — OFF-BALL LB EXPOSURE RESIDUAL STRUCTURE AUDIT","",
        f"Source snapshot: {sid}",f"Depth audit: {aid}",
        "2025 SEALED · 2026 NOT READ · market fields 0 · model fit 0","",
        f"CONCLUSION: {conclusion}",f"NEXT GATE: {next_gate}","",
        f"POOLED n {len(pooled):,} · snap MAE {report['overall']['snap']['mae']:.5f} · "
        f"mean actual-pred {report['overall']['meanResidualActualMinusPred']:+.5f}","",
        "MATERIAL SLICES",
    ]
    if candidates:
        for q in candidates:
            z=q["pooled"];mean=num(z.get("meanResidualActualMinusPred"))
            rate=z["positiveResidualRate"] if mean>0 else z["negativeResidualRate"]
            lines.append(
                f"  {q['dimension']} / {q['slice']}: n {z['n']:,} · mean residual {mean:+.4f} · "
                f"direction rate {rate:.1%} · MAE {z['snap']['mae']:.4f}"
            )
    else:
        lines.append("  NONE")
    lines += ["","No model is fit or promoted by this command.",f"REPORT: {jp}"]
    tp=out/"OMEGA_0.42.0_LB_EXPOSURE_RESIDUAL_STRUCTURE_AUDIT.txt";tp.write_text("\n".join(lines)+"\n")
    ptr=data_root/"data/models/nfl/CURRENT_OMEGA_LB_EXPOSURE_STRUCTURE_AUDIT_0420";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n");os.replace(tmp,ptr)
    print();print(tp.read_text())
    print("PASS OMEGA 0.42 exposure-structure audit · diagnostic only · production unchanged")
    return 0

if __name__=="__main__":raise SystemExit(main())

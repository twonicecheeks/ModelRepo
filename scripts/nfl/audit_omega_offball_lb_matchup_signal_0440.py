#!/usr/bin/env python3
"""OMEGA 0.44.0 — off-ball-LB matchup-conditioned exposure signal audit.

DIAGNOSTIC ONLY. NO MODEL FIT.

After 0.42 found no strong residual structure in H012's own role-history state and
0.43.1 found no material strict-prior injury signal, this audit asks whether clean
off-ball-LB snap-share residuals depend on the pregame matchup mix already forecast
by leakage-safe H008 family shares.

Signals:
- predicted RUSH share
- predicted COMPLETE_PASS share
- predicted SCRAMBLE share
- predicted SACK share
- predicted OTHER_PASS share
- predicted PASS_FAMILY share = COMPLETE_PASS + SACK + OTHER_PASS
- predicted RUSH_MINUS_PASS mix

Each signal is evaluated:
- pooled Pearson correlation with actual_snap_share - predicted_snap_share;
- sign consistency across 2021-2024;
- within fixed H012 role bands.

Preregistered material signal:
- pooled n >= 200
- |pooled Pearson r| >= 0.15
- same correlation sign in >=3/4 seasons
- at least one H012 role band with n>=100 and |r|>=0.15 in the same direction

2025 sealed. 2026 not read. Market fields not read.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from math import sqrt
import argparse,csv,json,os,sys,uuid

FAMILIES=("RUSH","COMPLETE_PASS","SCRAMBLE","SACK","OTHER_PASS")


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


def pearson(rows,xkey,ykey="snap_residual_actual_minus_pred"):
    if len(rows)<2:return None
    xs=[num(r.get(xkey)) for r in rows];ys=[num(r.get(ykey)) for r in rows]
    mx=fmean(xs);my=fmean(ys)
    vx=sum((x-mx)**2 for x in xs);vy=sum((y-my)**2 for y in ys)
    if vx<=1e-15 or vy<=1e-15:return 0.0
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sqrt(vx*vy)


def summarize_signal(rows,xkey):
    r=pearson(rows,xkey)
    return {
        "n":len(rows),
        "pearson":r,
        "featureMean":fmean(num(z.get(xkey)) for z in rows) if rows else None,
        "residualMean":fmean(num(z.get("snap_residual_actual_minus_pred")) for z in rows) if rows else None,
    }


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

    fptr=data_root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not fptr.exists():raise FileNotFoundError(fptr)
    sid=fptr.read_text().strip()
    foundation=data_root/"data/normalized/nfl/omega_tackle"/sid
    exdir=data_root/"data/normalized/nfl/omega_tackle_exposure"/sid
    histp=rcsv(foundation/"omega_tackle_play_opportunities.csv")
    histe=rcsv(foundation/"omega_tackle_credit_events.csv")
    histex=rcsv(exdir/"omega_tackle_exposure_player_games.csv")
    if any(int(num(r.get("season")))>=2025 for r in histp+histe+histex):
        raise ValueError("sealed/prospective row entered 0.44 audit")

    teamout=xb.aggregate_team_game_outcomes(histp,histex)
    teamrows=xb.build_team_pregame_rows(teamout)
    team_snaps=xb.estimate_team_defensive_snaps(histex)
    exposure_rows=er.build_exposure_pregame_rows(histex,team_snaps)
    fam_out=tf.aggregate_team_family_opportunities(histp)
    fam_pred=tf.build_team_family_share_pregame_rows(fam_out)
    fam_map=base.family_share_map(fam_pred,fs.FAMILIES)
    pfc=tf.aggregate_player_family_credits(histe)
    topology=tf.build_player_topology_rows(histex,fam_out,pfc,team_snaps)

    pooled=[];by_year={}
    for year in years:
        control,_,_=base.score_for_fit_year(
            fit_end=year-1,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
            fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
        )
        clean=[r for r in control if int(r["season"])==year and arch.explicit_role_label(r)=="OFFBALL_LB"]
        rows=[]
        for r in clean:
            z=dict(r)
            z["snap_residual_actual_minus_pred"]=num(r.get("actual_snap_share"))-num(r.get("predicted_snap_share"))
            for f in FAMILIES:
                z[f"mix_{f}"]=num(r.get(f"pred_share_{f}"))
            z["mix_PASS_FAMILY"]=z["mix_COMPLETE_PASS"]+z["mix_SACK"]+z["mix_OTHER_PASS"]
            z["mix_RUSH_MINUS_PASS"]=z["mix_RUSH"]-z["mix_PASS_FAMILY"]
            z["h012_role_band"]=role_band(r.get("predicted_snap_share"))
            rows.append(z)
        by_year[year]=rows;pooled.extend(rows)
        print(f"PASS {year} · LB {len(rows):,} · residual mean {fmean(num(r['snap_residual_actual_minus_pred']) for r in rows):+.4f}")

    signals={
        "RUSH":"mix_RUSH",
        "COMPLETE_PASS":"mix_COMPLETE_PASS",
        "SCRAMBLE":"mix_SCRAMBLE",
        "SACK":"mix_SACK",
        "OTHER_PASS":"mix_OTHER_PASS",
        "PASS_FAMILY":"mix_PASS_FAMILY",
        "RUSH_MINUS_PASS":"mix_RUSH_MINUS_PASS",
    }
    bands=("LOW_<35","ROTATION_35-65","STARTER_65-85","EVERY_DOWN_85+")
    results={};candidates=[]
    for name,key in signals.items():
        pooled_s=summarize_signal(pooled,key)
        yearly={str(y):summarize_signal(by_year[y],key) for y in years}
        rb={}
        for b in bands:
            zr=[r for r in pooled if r["h012_role_band"]==b]
            rb[b]=summarize_signal(zr,key)
        pr=pooled_s["pearson"] or 0.0
        sign=1 if pr>0 else (-1 if pr<0 else 0)
        sign_years=sum(1 for y in yearly.values() if y["pearson"] is not None and ((y["pearson"]>0 and sign>0) or (y["pearson"]<0 and sign<0)))
        role_support=[
            b for b,z in rb.items()
            if z["n"]>=100 and z["pearson"] is not None and abs(z["pearson"])>=.15
            and ((z["pearson"]>0 and sign>0) or (z["pearson"]<0 and sign<0))
        ]
        material=bool(pooled_s["n"]>=200 and abs(pr)>=.15 and sign_years>=3 and role_support)
        results[name]={
            "pooled":pooled_s,"byYear":yearly,"byRoleBand":rb,
            "sameSignYears":sign_years,"supportingRoleBands":role_support,"material":material,
        }
        if material:candidates.append({"signal":name,**results[name]})

    conclusion="MATCHUP_CONDITIONED_EXPOSURE_SIGNAL_MATERIAL" if candidates else "MATCHUP_CONDITIONED_EXPOSURE_SIGNAL_WEAK"
    next_gate="BUILD_0.45_MATCHUP_AWARE_LB_EXPOSURE_CHALLENGER" if candidates else "STOP_CURRENT_LB_EXPOSURE_RESEARCH_AND_RETAIN_FROZEN_CONTROL"

    report={
        "schemaVersion":"OMEGA_OFFBALL_LB_MATCHUP_EXPOSURE_SIGNAL_AUDIT_0.44.0",
        "createdAt":datetime.now(timezone.utc).isoformat(),"sourceSnapshotId":sid,
        "codeRoot":str(root),"dataRoot":str(data_root),
        "evaluationSeasons":years,"sealedHoldoutSeason":2025,"prospectiveSeason":2026,
        "holdoutOpened":False,"prospectiveRowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,
        "rows":len(pooled),"signals":results,"materialCandidates":candidates,
        "decisionRule":"pooled n>=200; |Pearson r|>=0.15; same sign >=3/4 seasons; >=1 H012 role band n>=100 with |r|>=0.15 same sign",
        "conclusion":conclusion,"nextGate":next_gate,
        "integrity":{"diagnosticOnly":True,"modelFit":False,"productionPromotion":False,"frozenOmegaMutation":False},
    }

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=data_root/"data/models/nfl/omega_lb_matchup_signal_audit_0440"/run_id;out.mkdir(parents=True,exist_ok=False)
    jp=out/"OMEGA_0.44.0_LB_MATCHUP_EXPOSURE_SIGNAL_AUDIT.json";jp.write_text(json.dumps(report,indent=2)+"\n")
    lines=[
        "OMEGA 0.44.0 — OFF-BALL LB MATCHUP-CONDITIONED EXPOSURE SIGNAL AUDIT","",
        f"Source snapshot: {sid}",
        "2025 SEALED · 2026 NOT READ · market fields 0 · model fit 0","",
        f"CONCLUSION: {conclusion}",f"NEXT GATE: {next_gate}","",
        f"POOLED n {len(pooled):,}","",
        "SIGNALS",
    ]
    for name,z in results.items():
        p=z["pooled"]
        lines.append(
            f"  {name}: r {p['pearson']:+.4f} · same-sign years {z['sameSignYears']}/4 · "
            f"role support {','.join(z['supportingRoleBands']) if z['supportingRoleBands'] else 'NONE'} · "
            f"{'PASS' if z['material'] else 'FAIL'}"
        )
    lines += ["","No model is fit or promoted by this command.",f"REPORT: {jp}"]
    tp=out/"OMEGA_0.44.0_LB_MATCHUP_EXPOSURE_SIGNAL_AUDIT.txt";tp.write_text("\n".join(lines)+"\n")
    ptr=data_root/"data/models/nfl/CURRENT_OMEGA_LB_MATCHUP_SIGNAL_AUDIT_0440";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n");os.replace(tmp,ptr)
    print();print(tp.read_text())
    print("PASS OMEGA 0.44 matchup signal audit · diagnostic only · production unchanged")
    return 0

if __name__=="__main__":raise SystemExit(main())

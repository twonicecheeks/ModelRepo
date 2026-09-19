#!/usr/bin/env python3
"""OMEGA 0.39.0 — clean off-ball-LB error-attribution audit.

For clean explicit off-ball LBs only, decompose H008/H012 tackle-credit error into:
1) team family-opportunity forecast error,
2) player defensive-snap exposure forecast error,
3) residual player family conversion/allocation error.

Chronological control rows are rebuilt for 2021-2024 with prior-season fit state.
Oracle swaps are diagnostics only and use target-game outcomes solely to attribute
historical error; they are never serialized as forecast models.

2025 remains sealed. 2026 is not read. Market fields are not read.
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


def num(v,default=0.0):
    try:
        if v in (None,""):return float(default)
        x=float(v);return x if x==x else float(default)
    except:return float(default)


def metrics(rows,actual_key,pred_key):
    if not rows:return {"n":0}
    e=[num(r.get(pred_key))-num(r.get(actual_key)) for r in rows]
    return {
        "n":len(rows),
        "mae":fmean(abs(x) for x in e),
        "rmse":sqrt(fmean(x*x for x in e)),
        "biasPredMinusActual":fmean(e),
    }


def bucket_snap(v):
    x=num(v)
    if x<.50:return "<0.50"
    if x<.75:return "0.50-0.75"
    return ">=0.75"


def bucket_history(v):
    x=int(num(v))
    if x<=1:return "0-1"
    if x<=5:return "2-5"
    return ">=6"


def enrich(rows):
    out=[]
    for r in rows:
        z=dict(r)
        total_actual=total_base=total_opp=total_snap=total_both=0.0
        ps=max(0.0,min(1.0,num(r.get("predicted_snap_share"))))
        aas=max(0.0,min(1.0,num(r.get("actual_snap_share"))))
        for fam in FAMILIES:
            actual=max(0.0,num(r.get(f"actual_credit_{fam}")))
            pred_opp=max(0.0,num(r.get(f"pred_opp_{fam}")))
            actual_opp=max(0.0,num(r.get(f"actual_team_opp_{fam}")))
            rate=max(0.0,num(r.get(f"shrunk_rate_{fam}")))
            base=max(0.0,num(r.get(f"pred_credit_{fam}")))
            opp_oracle=actual_opp*ps*rate
            snap_oracle=pred_opp*aas*rate
            both_oracle=actual_opp*aas*rate
            z[f"audit_actual_{fam}"]=actual
            z[f"audit_base_{fam}"]=base
            z[f"audit_oracle_opp_{fam}"]=opp_oracle
            z[f"audit_oracle_snap_{fam}"]=snap_oracle
            z[f"audit_oracle_both_{fam}"]=both_oracle
            total_actual+=actual;total_base+=base;total_opp+=opp_oracle;total_snap+=snap_oracle;total_both+=both_oracle
        z["audit_actual_total"]=total_actual
        z["audit_base_total"]=total_base
        z["audit_oracle_opp_total"]=total_opp
        z["audit_oracle_snap_total"]=total_snap
        z["audit_oracle_both_total"]=total_both
        z["audit_snap_bucket"]=bucket_snap(ps)
        z["audit_history_bucket"]=bucket_history(r.get("prior_games"))
        out.append(z)
    return out


def summarize(rows):
    base=metrics(rows,"audit_actual_total","audit_base_total")
    opp=metrics(rows,"audit_actual_total","audit_oracle_opp_total")
    snap=metrics(rows,"audit_actual_total","audit_oracle_snap_total")
    both=metrics(rows,"audit_actual_total","audit_oracle_both_total")
    fam={}
    for f in FAMILIES:
        bm=metrics(rows,f"audit_actual_{f}",f"audit_base_{f}")
        om=metrics(rows,f"audit_actual_{f}",f"audit_oracle_opp_{f}")
        sm=metrics(rows,f"audit_actual_{f}",f"audit_oracle_snap_{f}")
        xm=metrics(rows,f"audit_actual_{f}",f"audit_oracle_both_{f}")
        fam[f]={
            "baseline":bm,
            "oracleTeamOpportunity":om,
            "oracleSnap":sm,
            "oracleBoth":xm,
            "maeGainFromTeamOpportunityOracle":bm["mae"]-om["mae"],
            "maeGainFromSnapOracle":bm["mae"]-sm["mae"],
            "maeGainFromBothOracle":bm["mae"]-xm["mae"],
        }
    return {
        "baseline":base,
        "oracleTeamOpportunity":opp,
        "oracleSnap":snap,
        "oracleBoth":both,
        "maeGainFromTeamOpportunityOracle":base["mae"]-opp["mae"],
        "maeGainFromSnapOracle":base["mae"]-snap["mae"],
        "maeGainFromBothOracle":base["mae"]-both["mae"],
        "families":fam,
    }


def grouped(rows,key):
    g=defaultdict(list)
    for r in rows:g[str(r.get(key) or "UNKNOWN")].append(r)
    return {k:summarize(v) for k,v in sorted(g.items())}


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--data-root",default="")
    ap.add_argument("--evaluation-seasons",default="2021,2022,2023,2024")
    args=ap.parse_args();root=Path(args.root).expanduser().resolve()
    data_root=Path(args.data_root).expanduser().resolve() if args.data_root else root
    years=[int(x) for x in args.evaluation_seasons.split(",") if x.strip()]
    if years!=sorted(years) or not years or min(years)<2018 or max(years)>=2025:
        raise ValueError("evaluation seasons must be chronological development years <2025")

    sys.path[:0]=[str(root/"packages/models/nfl/omega"),str(root/"scripts/nfl")]
    import frozen_spec as fs
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import lb_edge_archetype_0363 as arch
    import analyze_omega_position_specific_challenger_0360 as base

    ptr=data_root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not ptr.exists():raise FileNotFoundError(ptr)
    sid=ptr.read_text(encoding="utf-8").strip()
    foundation=data_root/"data/normalized/nfl/omega_tackle"/sid
    exdir=data_root/"data/normalized/nfl/omega_tackle_exposure"/sid
    histp=rcsv(foundation/"omega_tackle_play_opportunities.csv")
    histe=rcsv(foundation/"omega_tackle_credit_events.csv")
    histex=rcsv(exdir/"omega_tackle_exposure_player_games.csv")
    if any(int(num(r.get("season")))>=2025 for r in histp+histe+histex):
        raise ValueError("sealed/prospective row entered OMEGA 0.39 audit")

    teamout=xb.aggregate_team_game_outcomes(histp,histex)
    teamrows=xb.build_team_pregame_rows(teamout)
    team_snaps=xb.estimate_team_defensive_snaps(histex)
    exposure_rows=er.build_exposure_pregame_rows(histex,team_snaps)
    fam_out=tf.aggregate_team_family_opportunities(histp)
    fam_pred=tf.build_team_family_share_pregame_rows(fam_out)
    fam_map=base.family_share_map(fam_pred,fs.FAMILIES)
    pfc=tf.aggregate_player_family_credits(histe)
    topology=tf.build_player_topology_rows(histex,fam_out,pfc,team_snaps)

    pooled=[];folds=[]
    for year in years:
        control,_,_=base.score_for_fit_year(
            fit_end=year-1,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
            fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
        )
        clean=[r for r in control if int(r["season"])==year and arch.explicit_role_label(r)=="OFFBALL_LB"]
        e=enrich(clean);s=summarize(e)
        folds.append({"season":year,"rows":len(e),"summary":s});pooled.extend(e)
        print(
            f"PASS {year} · n {len(e):,} · baseline MAE {s['baseline']['mae']:.3f} · "
            f"opp-oracle gain {s['maeGainFromTeamOpportunityOracle']:+.3f} · "
            f"snap-oracle gain {s['maeGainFromSnapOracle']:+.3f} · "
            f"both gain {s['maeGainFromBothOracle']:+.3f}"
        )

    p=summarize(pooled)
    candidate_causes={
        "TEAM_FAMILY_OPPORTUNITY":p["maeGainFromTeamOpportunityOracle"],
        "PLAYER_SNAP_EXPOSURE":p["maeGainFromSnapOracle"],
        "JOINT_OPPORTUNITY_AND_SNAP":p["maeGainFromBothOracle"],
    }
    best=max(candidate_causes,key=candidate_causes.get)
    best_gain=candidate_causes[best]
    # If even perfect historical opportunity+snap inputs cannot recover >=0.10 MAE,
    # the dominant remaining problem is conversion/allocation rather than exposure.
    if p["maeGainFromBothOracle"]<.10:
        conclusion="PLAYER_FAMILY_CONVERSION_ALLOCATION_DOMINANT"
        next_gate="BUILD_FAMILY_SPECIFIC_PLAYER_HAZARD_CHALLENGER"
    elif best=="PLAYER_SNAP_EXPOSURE":
        conclusion="SNAP_EXPOSURE_DOMINANT"
        next_gate="BUILD_OFFBALL_LB_ROLE_EXPOSURE_CHALLENGER"
    elif best=="TEAM_FAMILY_OPPORTUNITY":
        conclusion="TEAM_FAMILY_OPPORTUNITY_DOMINANT"
        next_gate="BUILD_LB_MATCHUP_OPPORTUNITY_CHALLENGER"
    else:
        conclusion="JOINT_EXPOSURE_AND_OPPORTUNITY_MATERIAL"
        next_gate="BUILD_JOINT_LB_EXPOSURE_OPPORTUNITY_CHALLENGER"

    report={
        "schemaVersion":"OMEGA_OFFBALL_LB_ERROR_ATTRIBUTION_0.39.0",
        "createdAt":datetime.now(timezone.utc).isoformat(),"sourceSnapshotId":sid,
        "codeRoot":str(root),"dataRoot":str(data_root),
        "evaluationSeasons":years,"sealedHoldoutSeason":2025,"prospectiveSeason":2026,
        "holdoutOpened":False,"prospectiveRowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,
        "rows":len(pooled),"pooled":p,"folds":folds,
        "byPredictedSnapShare":grouped(pooled,"audit_snap_bucket"),
        "byPriorGames":grouped(pooled,"audit_history_bucket"),
        "conclusion":conclusion,"nextGate":next_gate,
        "decisionRule":"If joint opportunity+snap oracle improves MAE <0.10, attribute dominant remaining error to player family conversion/allocation; otherwise choose largest material oracle source.",
        "integrity":{"diagnosticOracleOnly":True,"modelFit":False,"productionPromotion":False,"frozenOmegaMutation":False},
    }
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=data_root/"data/models/nfl/omega_lb_error_audit_0390"/run_id;out.mkdir(parents=True,exist_ok=False)
    jp=out/"OMEGA_0.39.0_LB_ERROR_ATTRIBUTION.json";jp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    lines=[
        "OMEGA 0.39.0 — OFF-BALL LB ERROR ATTRIBUTION","",
        f"Source snapshot: {sid}",
        "2025 SEALED · 2026 NOT READ · market fields 0 · model fit 0","",
        f"CONCLUSION: {conclusion}",
        f"NEXT GATE: {next_gate}","",
        "POOLED PLAYER xTC",
        f"  n {len(pooled):,}",
        f"  baseline MAE {p['baseline']['mae']:.4f} · RMSE {p['baseline']['rmse']:.4f} · bias {p['baseline']['biasPredMinusActual']:+.4f}",
        f"  perfect team-family opportunity oracle MAE {p['oracleTeamOpportunity']['mae']:.4f} · gain {p['maeGainFromTeamOpportunityOracle']:+.4f}",
        f"  perfect player-snap oracle MAE {p['oracleSnap']['mae']:.4f} · gain {p['maeGainFromSnapOracle']:+.4f}",
        f"  perfect opportunity+snap oracle MAE {p['oracleBoth']['mae']:.4f} · gain {p['maeGainFromBothOracle']:+.4f}","",
        "BY FAMILY",
    ]
    for fam in FAMILIES:
        z=p["families"][fam]
        lines.append(
            f"  {fam}: baseline MAE {z['baseline']['mae']:.4f} · "
            f"opp gain {z['maeGainFromTeamOpportunityOracle']:+.4f} · "
            f"snap gain {z['maeGainFromSnapOracle']:+.4f} · both gain {z['maeGainFromBothOracle']:+.4f} · "
            f"bias {z['baseline']['biasPredMinusActual']:+.4f}"
        )
    lines += ["","FOLDS"]
    for f in folds:
        s=f["summary"]
        lines.append(
            f"  {f['season']} · n {f['rows']:,} · baseline {s['baseline']['mae']:.4f} · "
            f"opp {s['maeGainFromTeamOpportunityOracle']:+.4f} · snap {s['maeGainFromSnapOracle']:+.4f} · both {s['maeGainFromBothOracle']:+.4f}"
        )
    lines += ["","Oracle swaps are historical diagnostics only; they are not forecast features.",
              f"REPORT: {jp}"]
    tp=out/"OMEGA_0.39.0_LB_ERROR_ATTRIBUTION.txt";tp.write_text("\n".join(lines)+"\n",encoding="utf-8")
    ptr=data_root/"data/models/nfl/CURRENT_OMEGA_LB_ERROR_AUDIT_0390";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n",encoding="utf-8");os.replace(tmp,ptr)
    print();print(tp.read_text(encoding="utf-8"))
    print("PASS OMEGA 0.39 error attribution · diagnostic only · production unchanged")
    return 0

if __name__=="__main__":raise SystemExit(main())

#!/usr/bin/env python3
"""OMEGA 0.36 — development-only position-specific challenger bake-off.

Builds the existing strictly-lagged H008/H012 control for 2017-2024, then tests:
- DL: exact control/no change,
- LB: fixed-L2 residual using rush/scramble/sack allocation features,
- DB: fixed-L2 residual using pass-family/run-support allocation features.

Evaluation folds are chronological 2021-2024. 2025 remains sealed and 2026 is not
read. The existing frozen NB_ROLE distribution is used only as a common development
mapping for paired OVER-probability Brier/log-loss diagnostics; no distribution
parameters are retuned here.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse
import csv
import json
import math
import os
import sys
import uuid


def rcsv(path:Path)->list[dict[str,str]]:
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))


def pct(v):return "NA" if v is None else f"{100*float(v):+.3f} pp"
def fmt(v,d=4):return "NA" if v is None else f"{float(v):.{d}f}"


def probability_metrics(rows, pred_key, dist, params):
    b=[];ll=[]
    for r in rows:
        mean=max(0.0,float(r[pred_key]));actual=float(r["actual_xtc"])
        tier=dist.role_tier(float(r.get("predicted_snap_share") or 0.0))
        for whole in range(15):
            line=whole+.5
            p=dist.over_probability(line,mean,"NB_ROLE",params,tier)
            y=1.0 if actual>line else 0.0
            b.append((p-y)**2)
            pp=max(1e-12,min(1-1e-12,p))
            ll.append(-(y*math.log(pp)+(1-y)*math.log(1-pp)))
    return {"n":len(b),"brier":fmean(b) if b else None,"logLoss":fmean(ll) if ll else None}


def family_share_map(rows, families):
    out={}
    for r in rows:
        out[(str(r.get("game_id") or ""),str(r.get("defense_team") or ""))]={
            f:float(r.get("pred_share_"+f) or 0.0) for f in families
        }
    return out


def score_for_fit_year(*,fit_end,teamrows,exposure_rows,topology_rows,fam_map,xb,er,tf,fs):
    train_team=[r for r in teamrows if 2017<=int(r["season"])<=fit_end]
    train_exp=[r for r in exposure_rows if 2017<=int(r["season"])<=fit_end]
    if not train_team or not train_exp:raise ValueError(f"empty control fit through {fit_end}")
    xto=xb.fit_ridge(train_team,target_key="actual_opportunity_plays",l2=fs.XTO_L2)
    role=er.fit_ridge(train_exp,fs.EXPOSURE_L2)

    xto_pred={}
    for r in teamrows:
        season=int(r["season"])
        if 2017<=season<=fit_end+1:
            xto_pred[(str(r["game_id"]),str(r["defense_team"]))]=xto.predict([float(r[n]) for n in xb.TEAM_FEATURE_NAMES])
    exp_pred={}
    for r in exposure_rows:
        season=int(r["season"])
        if 2017<=season<=fit_end+1:
            exp_pred[(str(r["game_id"]),str(r["team"]),str(r["player_id"]))]=role.predict(r)

    eligible=[r for r in topology_rows if 2017<=int(r["season"])<=fit_end+1]
    return tf.score_rows(
        eligible,alpha=fs.FAMILY_ALPHA,xto_predictions=xto_pred,
        exposure_predictions=exp_pred,family_share_predictions=fam_map,out_key="control_xtc"
    ),xto,role


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--evaluation-seasons",default="2021,2022,2023,2024")
    ap.add_argument("--bootstrap-reps",type=int,default=1000)
    args=ap.parse_args();root=Path(args.root).expanduser().resolve()
    eval_years=[int(x) for x in args.evaluation_seasons.split(",") if x.strip()]
    if not eval_years or min(eval_years)<2018 or max(eval_years)>=2025:raise ValueError("evaluation seasons must be development-only and <2025")

    sys.path[:0]=[str(root/"packages/models/nfl/omega")]
    import frozen_spec as fs
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import tackle_count_distribution as dist
    import position_specific_challenger_0360 as pc

    pc.assert_development_only(range(2017,2025))
    ptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not ptr.exists():raise FileNotFoundError(ptr)
    sid=ptr.read_text(encoding="utf-8").strip()
    foundation=root/"data/normalized/nfl/omega_tackle"/sid
    exdir=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    for p in (foundation/"omega_tackle_play_opportunities.csv",foundation/"omega_tackle_credit_events.csv",exdir/"omega_tackle_exposure_player_games.csv"):
        if not p.exists():raise FileNotFoundError(p)

    histp=rcsv(foundation/"omega_tackle_play_opportunities.csv")
    histe=rcsv(foundation/"omega_tackle_credit_events.csv")
    histex=rcsv(exdir/"omega_tackle_exposure_player_games.csv")
    if any(int(float(r.get("season") or 0))>=2025 for r in histp+histe+histex):
        raise ValueError("normalized development inputs unexpectedly include sealed/prospective seasons")

    teamout=xb.aggregate_team_game_outcomes(histp,histex)
    teamrows=xb.build_team_pregame_rows(teamout)
    team_snaps=xb.estimate_team_defensive_snaps(histex)
    exposure_rows=er.build_exposure_pregame_rows(histex,team_snaps)
    fam_out=tf.aggregate_team_family_opportunities(histp)
    fam_pred=tf.build_team_family_share_pregame_rows(fam_out)
    fam_map=family_share_map(fam_pred,fs.FAMILIES)
    pfc=tf.aggregate_player_family_credits(histe)
    topology=tf.build_player_topology_rows(histex,fam_out,pfc,team_snaps)

    pspec=root/"data/models/nfl/omega_tackle_016_probability_frozen"/sid/"OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json"
    if not pspec.exists():raise FileNotFoundError(pspec)
    pmeta=json.loads(pspec.read_text(encoding="utf-8"))
    params=pmeta["distributionParamsFitThrough2024"]

    fold_rows=[];pooled=defaultdict(list)
    for year in eval_years:
        control,_,_=score_for_fit_year(
            fit_end=year-1,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
            fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
        )
        train=[r for r in control if 2017<=int(r["season"])<year]
        test=[r for r in control if int(r["season"])==year]
        models={}
        for pos in ("LB","DB"):
            models[pos]=pc.fit_residual(train,pos,pc.FIXED_L2)
        scored=pc.apply_challengers(test,models)
        for r in scored:pooled[pc.canonical_position_row(r)].append(r)
        fold={"season":year,"trainRows":len(train),"testRows":len(test),"positions":{}}
        for pos in pc.POSITIONS:
            rr=[r for r in scored if pc.canonical_position_row(r)==pos]
            if not rr:continue
            base=pc.count_metrics(rr,"control_xtc");cand=pc.count_metrics(rr,"position_challenger_xtc")
            bp=probability_metrics(rr,"control_xtc",dist,params);cp=probability_metrics(rr,"position_challenger_xtc",dist,params)
            fold["positions"][pos]={
                "control":base,"challenger":cand,
                "maeImprovement":base["mae"]-cand["mae"],
                "rmseImprovement":base["rmse"]-cand["rmse"],
                "biasAbsImprovement":abs(base["biasPredMinusActual"])-abs(cand["biasPredMinusActual"]),
                "controlProbability":bp,"challengerProbability":cp,
                "brierImprovement":None if bp["brier"] is None or cp["brier"] is None else bp["brier"]-cp["brier"],
            }
        fold_rows.append(fold)
        print(f"PASS chronological fold {year} · train {len(train):,} · test {len(test):,}")

    pooled_result={}
    gates={}
    for pos in pc.POSITIONS:
        rr=pooled.get(pos,[])
        if not rr:continue
        base=pc.count_metrics(rr,"control_xtc");cand=pc.count_metrics(rr,"position_challenger_xtc")
        bp=probability_metrics(rr,"control_xtc",dist,params);cp=probability_metrics(rr,"position_challenger_xtc",dist,params)
        bimp=None if bp["brier"] is None or cp["brier"] is None else bp["brier"]-cp["brier"]
        boot=pc.paired_game_bootstrap(rr,"control_xtc","position_challenger_xtc",reps=args.bootstrap_reps,seed=20260919+pc.POSITIONS.index(pos))
        gate=pc.promotion_gate(pos,base,cand,boot,bimp)
        pooled_result[pos]={"control":base,"challenger":cand,"controlProbability":bp,"challengerProbability":cp,
                            "brierImprovement":bimp,"bootstrap":boot,"gate":gate}
        gates[pos]=gate["status"]

    all_rows=[r for pos in pc.POSITIONS for r in pooled.get(pos,[])]
    overall_control=pc.count_metrics(all_rows,"control_xtc")
    overall_cand=pc.count_metrics(all_rows,"position_challenger_xtc")
    overall_bp=probability_metrics(all_rows,"control_xtc",dist,params)
    overall_cp=probability_metrics(all_rows,"position_challenger_xtc",dist,params)

    # Serialize full-development shadow models only; this is NOT promotion.
    full_control,_,_=score_for_fit_year(
        fit_end=2024,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
        fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
    )
    full_models={pos:pc.fit_residual(full_control,pos,pc.FIXED_L2) for pos in ("LB","DB")}

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=root/"data/models/nfl/omega_position_challenger_0360"/run_id
    out.mkdir(parents=True,exist_ok=False)
    report={
        "schemaVersion":"OMEGA_POSITION_CHALLENGER_BAKEOFF_0.36.0","version":pc.VERSION,"lineage":pc.LINEAGE,
        "createdAt":datetime.now(timezone.utc).isoformat(),"runId":run_id,"sourceSnapshotId":sid,
        "developmentSeasons":[2017,2018,2019,2020,2021,2022,2023,2024],"evaluationSeasons":eval_years,
        "sealedHoldoutSeason":2025,"prospectiveSeason":2026,"holdoutOpened":False,"prospectiveRowsRead":0,
        "marketFieldsRead":0,"oddsPapiRequests":0,"frozenOmegaMutation":False,"productionPromotion":False,
        "positionTaxonomy":"RAW_POSITION_PRECEDENCE_V1",
        "challengerDesign":{
            "DL":"CONTROL_NO_CHANGE",
            "LB":"fixed-L2 residual on H008/H012 rush/scramble/sack + role allocation features",
            "DB":"fixed-L2 residual on H008/H012 completed-pass/other-pass/rush + role allocation features",
            "l2":pc.FIXED_L2,"maxAbsCorrection":pc.MAX_ABS_CORRECTION,
            "hyperparameterSearches":0,
        },
        "folds":fold_rows,"pooledByPosition":pooled_result,
        "overall":{"control":overall_control,"challenger":overall_cand,
                   "controlProbability":overall_bp,"challengerProbability":overall_cp,
                   "brierImprovement":overall_bp["brier"]-overall_cp["brier"]},
        "gateSummary":gates,
        "nextGate":"PROSPECTIVE_SHADOW_ONLY_FOR_POSITIONS_WITH_NEXT_STAGE_SHADOW_SIGNAL",
    }
    (out/"OMEGA_0.36_POSITION_CHALLENGER_BAKEOFF.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    models={"version":pc.VERSION,"status":"SHADOW_NOT_PROMOTED","sourceSnapshotId":sid,
            "LB":full_models["LB"].to_dict(),"DB":full_models["DB"].to_dict(),
            "DL":{"track":"CONTROL_NO_CHANGE"}}
    (out/"OMEGA_0.36_POSITION_CHALLENGER_MODELS.json").write_text(json.dumps(models,indent=2)+"\n",encoding="utf-8")

    lines=[
        "OMEGA 0.36 — POSITION-SPECIFIC CHALLENGER BAKE-OFF","",
        f"Source snapshot: {sid}",
        "Development: 2017-2024 · chronological evaluation 2021-2024",
        "2025 holdout: SEALED · 2026 prospective: NOT READ",
        "Market dependency: NO · refits to production 0 · hyperparameter searches 0","",
        "OVERALL",
        f"  control MAE {overall_control['mae']:.4f} RMSE {overall_control['rmse']:.4f} bias {overall_control['biasPredMinusActual']:+.4f}",
        f"  shadow  MAE {overall_cand['mae']:.4f} RMSE {overall_cand['rmse']:.4f} bias {overall_cand['biasPredMinusActual']:+.4f}",
        f"  OVER-probability Brier {overall_bp['brier']:.5f} -> {overall_cp['brier']:.5f} · improvement {overall_bp['brier']-overall_cp['brier']:+.5f}",
        "",
        "BY POSITION",
    ]
    for pos in pc.POSITIONS:
        r=pooled_result.get(pos)
        if not r:continue
        b=r["control"];c=r["challenger"];g=r["gate"];bt=r["bootstrap"]["ci95"]
        lines += [
            "",
            f"  {pos} · {g['status']}",
            f"    count: MAE {b['mae']:.4f}->{c['mae']:.4f} ({b['mae']-c['mae']:+.4f}) · RMSE {b['rmse']:.4f}->{c['rmse']:.4f} ({b['rmse']-c['rmse']:+.4f})",
            f"    bias: {b['biasPredMinusActual']:+.4f}->{c['biasPredMinusActual']:+.4f}",
            f"    Brier: {r['controlProbability']['brier']:.5f}->{r['challengerProbability']['brier']:.5f} ({r['brierImprovement']:+.5f})",
            f"    bootstrap MAE improvement CI [{bt['maeImprovement']['low']:+.4f}, {bt['maeImprovement']['high']:+.4f}]",
            f"    bootstrap RMSE improvement CI [{bt['rmseImprovement']['low']:+.4f}, {bt['rmseImprovement']['high']:+.4f}]",
        ]
    lines += ["","Interpretation:",
              "  DL is deliberately unchanged. LB/DB require paired count improvement, positive Brier improvement, and bootstrap support before even entering prospective shadow.",
              "  This command cannot promote a model into production or open the sealed 2025 holdout.",
              "",f"REPORT: {out/'OMEGA_0.36_POSITION_CHALLENGER_BAKEOFF.json'}",
              f"MODELS: {out/'OMEGA_0.36_POSITION_CHALLENGER_MODELS.json'}"]
    txt=out/"OMEGA_0.36_POSITION_CHALLENGER_BAKEOFF.txt";txt.write_text("\n".join(lines)+"\n",encoding="utf-8")
    ptr=root/"data/models/nfl/CURRENT_OMEGA_POSITION_CHALLENGER_0360";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n",encoding="utf-8");os.replace(tmp,ptr)
    print();print(txt.read_text(encoding="utf-8"))
    print("PASS OMEGA 0.36 development-only position bake-off · 2025 sealed · 2026 excluded · production unchanged")
    return 0

if __name__=="__main__":raise SystemExit(main())

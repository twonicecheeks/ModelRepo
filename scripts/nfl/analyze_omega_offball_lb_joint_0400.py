#!/usr/bin/env python3
"""OMEGA 0.40.3 — chronological joint LB exposure/opportunity bake-off.

Development 2017-2024. Evaluation folds 2021-2024.
2025 sealed. 2026 not read. Markets not read.

Historical advancement is based on count/component metrics only. Existing frozen
NB_ROLE probability parameters were fit through 2024, so they are deliberately
excluded from this chronological advancement gate to avoid calibration lookahead.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse,csv,json,os,sys,uuid


def rcsv(path:Path):
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))


def mean_family_mae(rows,pred_prefix,actual_prefix="actual_opp_"):
    vals=[]
    for r in rows:
        for f in ("RUSH","COMPLETE_PASS","SCRAMBLE","SACK","OTHER_PASS"):
            vals.append(abs(float(r[f"{pred_prefix}{f}"])-float(r[f"{actual_prefix}{f}"])))
    return fmean(vals) if vals else 0.0


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--data-root",default="")
    ap.add_argument("--evaluation-seasons",default="2021,2022,2023,2024")
    ap.add_argument("--bootstrap-reps",type=int,default=1000)
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
    import offball_lb_joint_0400 as m
    import analyze_omega_position_specific_challenger_0360 as base

    m.assert_development_only(range(2017,2025))
    ptr=data_root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not ptr.exists():raise FileNotFoundError(ptr)
    sid=ptr.read_text(encoding="utf-8").strip()
    foundation=data_root/"data/normalized/nfl/omega_tackle"/sid
    exdir=data_root/"data/normalized/nfl/omega_tackle_exposure"/sid
    for p in (
        foundation/"omega_tackle_play_opportunities.csv",
        foundation/"omega_tackle_credit_events.csv",
        exdir/"omega_tackle_exposure_player_games.csv",
    ):
        if not p.exists():raise FileNotFoundError(p)

    histp=rcsv(foundation/"omega_tackle_play_opportunities.csv")
    histe=rcsv(foundation/"omega_tackle_credit_events.csv")
    histex=rcsv(exdir/"omega_tackle_exposure_player_games.csv")
    if any(int(float(r.get("season") or 0))>=2025 for r in histp+histe+histex):
        raise ValueError("normalized development inputs unexpectedly include 2025+")

    teamout=xb.aggregate_team_game_outcomes(histp,histex)
    teamrows=xb.build_team_pregame_rows(teamout)
    team_snaps=xb.estimate_team_defensive_snaps(histex)
    exposure_rows=er.build_exposure_pregame_rows(histex,team_snaps)
    fam_out=tf.aggregate_team_family_opportunities(histp)
    fam_pred=tf.build_team_family_share_pregame_rows(fam_out)
    fam_map=base.family_share_map(fam_pred,fs.FAMILIES)
    pfc=tf.aggregate_player_family_credits(histe)
    topology=tf.build_player_topology_rows(histex,fam_out,pfc,team_snaps)
    opp_all=m.build_opportunity_examples(teamrows,fam_pred)

    folds=[];pooled=[];pooled_snap=[];pooled_opp=[]
    for year in years:
        control,xto_model,_=base.score_for_fit_year(
            fit_end=year-1,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
            fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
        )
        clean_train=[r for r in control if 2017<=int(r["season"])<year and arch.explicit_role_label(r)=="OFFBALL_LB"]
        clean_test=[r for r in control if int(r["season"])==year and arch.explicit_role_label(r)=="OFFBALL_LB"]
        exp_train=m.build_exposure_examples(clean_train,exposure_rows)
        exp_test=m.build_exposure_examples(clean_test,exposure_rows)
        opp_train=[r for r in opp_all if 2017<=int(r["season"])<year]
        opp_test=[dict(r) for r in opp_all if int(r["season"])==year]
        if min(len(exp_train),len(exp_test),len(opp_train),len(opp_test),len(clean_test))<=0:
            raise ValueError(f"empty OMEGA 0.40 fold {year}")

        exposure_model=m.fit_exposure(exp_train)
        opp_models=m.fit_opportunities(opp_train)

        # Target-year baseline opportunity predictions use the target fold's
        # prior-season-only frozen xTO model plus strictly-lagged H008 shares.
        for r in opp_test:
            xto=xto_model.predict([float(r[n]) for n in xb.TEAM_FEATURE_NAMES])
            for f in m.FAMILIES:
                r[f"baseline_opp_{f}"]=max(0.0,xto*float(r[f"pred_share_{f}"]))
                r[f"challenger_opp_{f}"]=opp_models[f].predict(r)

        exp_map={(str(r["game_id"]),str(r["team"]),str(r["player_id"])):r for r in exp_test}
        opp_map={(str(r["game_id"]),str(r["defense_team"])):r for r in opp_test}
        scored=m.score_ablation(clean_test,exposure_model,exp_map,opp_models,opp_map)
        if len(scored)!=len(clean_test):
            raise ValueError(f"OMEGA 0.40 join loss in {year}: scored {len(scored)} / clean {len(clean_test)}")
        max_control_drift=max(abs(float(r.get("control_xtc") or 0)-float(r["omega040_control_xtc"])) for r in scored)
        if max_control_drift>1e-8:
            raise ValueError(f"OMEGA 0.40 control reconstruction drift in {year}: {max_control_drift}")

        base_met=m.metrics(scored,"omega040_control_xtc")
        exp_met=m.metrics(scored,"omega040_exposure_only_xtc")
        opp_met=m.metrics(scored,"omega040_opportunity_only_xtc")
        joint_met=m.metrics(scored,"omega040_joint_xtc")
        snap_base=m.snap_metrics(scored,"predicted_snap_share")
        snap_chal=m.snap_metrics(scored,"omega040_exposure_snap_share")
        family_base=mean_family_mae(opp_test,"baseline_opp_")
        family_chal=mean_family_mae(opp_test,"challenger_opp_")
        fam_detail={}
        for f in m.FAMILIES:
            bm=m.opportunity_metrics(opp_test,f,f"baseline_opp_{f}")
            cm=m.opportunity_metrics(opp_test,f,f"challenger_opp_{f}")
            fam_detail[f]={"control":bm,"challenger":cm,"maeImprovement":bm["mae"]-cm["mae"]}

        fold={
            "season":year,
            "cleanLbTrainRows":len(clean_train),"cleanLbTestRows":len(clean_test),
            "maxControlReconstructionDrift":max_control_drift,
            "exposureTrainRows":len(exp_train),"opportunityTrainRows":len(opp_train),
            "control":base_met,"exposureOnly":exp_met,"opportunityOnly":opp_met,"joint":joint_met,
            "exposureComponent":{
                "control":snap_base,"challenger":snap_chal,
                "maeImprovement":snap_base["mae"]-snap_chal["mae"],
            },
            "opportunityComponent":{
                "controlMeanFamilyMae":family_base,"challengerMeanFamilyMae":family_chal,
                "maeImprovement":family_base-family_chal,"families":fam_detail,
            },
            "exposureOnlyMaeImprovement":base_met["mae"]-exp_met["mae"],
            "opportunityOnlyMaeImprovement":base_met["mae"]-opp_met["mae"],
            "jointMaeImprovement":base_met["mae"]-joint_met["mae"],
            "jointRmseImprovement":base_met["rmse"]-joint_met["rmse"],
        }
        folds.append(fold);pooled.extend(scored);pooled_snap.extend(scored);pooled_opp.extend(opp_test)
        print(
            f"PASS fold {year} · LB {len(scored):,} · "
            f"snap MAE {snap_base['mae']:.4f}->{snap_chal['mae']:.4f} · "
            f"family-opp MAE {family_base:.3f}->{family_chal:.3f} · "
            f"player control {base_met['mae']:.3f} · exposure {exp_met['mae']:.3f} · "
            f"opportunity {opp_met['mae']:.3f} · joint {joint_met['mae']:.3f}"
        )

    pbase=m.metrics(pooled,"omega040_control_xtc")
    pexp=m.metrics(pooled,"omega040_exposure_only_xtc")
    popp=m.metrics(pooled,"omega040_opportunity_only_xtc")
    pjoint=m.metrics(pooled,"omega040_joint_xtc")
    snap_base=m.snap_metrics(pooled_snap,"predicted_snap_share")
    snap_chal=m.snap_metrics(pooled_snap,"omega040_exposure_snap_share")
    opp_base=mean_family_mae(pooled_opp,"baseline_opp_")
    opp_chal=mean_family_mae(pooled_opp,"challenger_opp_")
    boot=m.paired_game_bootstrap(pooled,"omega040_control_xtc","omega040_joint_xtc",args.bootstrap_reps,20260919)
    gate=m.advancement_gate(
        folds,pbase,pjoint,boot,
        snap_base["mae"]-snap_chal["mae"],
        opp_base-opp_chal,
    )

    # Full development-only research artifact for later shadow only if gate passes.
    full_control,_,_=base.score_for_fit_year(
        fit_end=2024,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
        fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
    )
    full_clean=[r for r in full_control if 2017<=int(r["season"])<=2024 and arch.explicit_role_label(r)=="OFFBALL_LB"]
    full_exp=m.build_exposure_examples(full_clean,exposure_rows)
    full_opp=[r for r in opp_all if 2017<=int(r["season"])<=2024]
    exposure_model=m.fit_exposure(full_exp);opp_models=m.fit_opportunities(full_opp)

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=data_root/"data/models/nfl/omega_offball_lb_joint_0400"/run_id;out.mkdir(parents=True,exist_ok=False)
    ci=boot["ci95"]
    report={
        "schemaVersion":"OMEGA_OFFBALL_LB_JOINT_BAKEOFF_0.40.3",
        "version":m.VERSION,"lineage":m.LINEAGE,"createdAt":datetime.now(timezone.utc).isoformat(),
        "runId":run_id,"sourceSnapshotId":sid,"codeRoot":str(root),"dataRoot":str(data_root),
        "developmentSeasons":list(range(2017,2025)),"evaluationSeasons":years,
        "sealedHoldoutSeason":2025,"prospectiveSeason":2026,"holdoutOpened":False,"prospectiveRowsRead":0,
        "marketFieldsRead":0,"oddsPapiRequests":0,"frozenOmegaMutation":False,"productionPromotion":False,
        "design":{
            "roleUniverse":"clean explicit ILB/MLB only",
            "exposure":"same strictly-lagged H012 features, LB-specific fit",
            "opportunity":"one direct fixed-L2 model per H008 family using lagged team features + lagged family shares",
            "playerFamilyConversionRates":"FROZEN_H008",
            "exposureL2":m.EXPOSURE_L2,"opportunityL2":m.OPPORTUNITY_L2,
            "hyperparameterSearches":0,
            "probabilityCalibrationHistoricalGate":"DEFERRED_DUE_TO_FROZEN_2024_DISTRIBUTION_LOOKAHEAD",
        },
        "folds":folds,
        "pooled":{
            "control":pbase,"exposureOnly":pexp,"opportunityOnly":popp,"joint":pjoint,
            "exposureComponent":{"control":snap_base,"challenger":snap_chal,
                                 "maeImprovement":snap_base["mae"]-snap_chal["mae"]},
            "opportunityComponent":{"controlMeanFamilyMae":opp_base,"challengerMeanFamilyMae":opp_chal,
                                    "maeImprovement":opp_base-opp_chal},
            "bootstrapJointVsControl":boot,
        },
        "gate":gate,
        "nextGate":"PROSPECTIVE_SHADOW_ONLY_IF_NEXT_STAGE_SHADOW_SIGNAL",
    }
    rp=out/"OMEGA_0.40.3_OFFBALL_LB_JOINT_BAKEOFF.json";rp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    models={
        "version":m.VERSION,"lineage":m.LINEAGE,
        "status":"SHADOW_NOT_PROMOTED" if gate["status"]=="NEXT_STAGE_SHADOW_SIGNAL" else "RESEARCH_ONLY_NO_PROMOTION",
        "roleUniverse":"clean explicit ILB/MLB",
        "exposureModel":exposure_model.to_dict(),
        "familyOpportunityModels":{f:opp_models[f].to_dict() for f in m.FAMILIES},
        "playerFamilyConversionRates":"USE_FROZEN_H008_AT_SCORING_TIME",
    }
    mp=out/"OMEGA_0.40_OFFBALL_LB_JOINT_MODELS.json";mp.write_text(json.dumps(models,indent=2)+"\n",encoding="utf-8")

    lines=[
        "OMEGA 0.40.3 — JOINT OFF-BALL LB EXPOSURE + OPPORTUNITY CHALLENGER","",
        f"Source snapshot: {sid}",
        "Development 2017-2024 · chronological evaluation 2021-2024",
        "2025 SEALED · 2026 NOT READ · market fields 0 · hyperparameter searches 0",
        "Historical probability calibration gate DEFERRED (avoid 2024 distribution lookahead)","",
        f"GATE: {gate['status']}","",
        "COMPONENTS",
        f"  Snap-share MAE: {snap_base['mae']:.5f} -> {snap_chal['mae']:.5f} · improvement {snap_base['mae']-snap_chal['mae']:+.5f}",
        f"  Mean family-opportunity MAE: {opp_base:.5f} -> {opp_chal:.5f} · improvement {opp_base-opp_chal:+.5f}","",
        "PLAYER xTC ABLATIONS",
        f"  Control MAE {pbase['mae']:.4f} · RMSE {pbase['rmse']:.4f} · bias {pbase['biasPredMinusActual']:+.4f}",
        f"  Exposure-only MAE {pexp['mae']:.4f} · improvement {pbase['mae']-pexp['mae']:+.4f}",
        f"  Opportunity-only MAE {popp['mae']:.4f} · improvement {pbase['mae']-popp['mae']:+.4f}",
        f"  Joint MAE {pjoint['mae']:.4f} · improvement {pbase['mae']-pjoint['mae']:+.4f}",
        f"  Joint RMSE {pjoint['rmse']:.4f} · improvement {pbase['rmse']-pjoint['rmse']:+.4f}",
        f"  Joint bias {pjoint['biasPredMinusActual']:+.4f}",
        f"  Bootstrap MAE improvement CI [{ci['maeImprovement']['low']:+.4f}, {ci['maeImprovement']['high']:+.4f}]",
        f"  Bootstrap RMSE improvement CI [{ci['rmseImprovement']['low']:+.4f}, {ci['rmseImprovement']['high']:+.4f}]",
        f"  Positive joint-MAE seasons {gate['positiveJointMaeSeasons']}/4 · required >=3",
        f"  Bias gate {'PASS' if gate['absBiasGatePass'] else 'FAIL'}","",
        "FOLDS",
    ]
    for f in folds:
        lines.append(
            f"  {f['season']} · snap {f['exposureComponent']['maeImprovement']:+.5f} · "
            f"opp {f['opportunityComponent']['maeImprovement']:+.4f} · "
            f"player exposure {f['exposureOnlyMaeImprovement']:+.4f} · "
            f"opportunity {f['opportunityOnlyMaeImprovement']:+.4f} · joint {f['jointMaeImprovement']:+.4f}"
        )
    lines += ["","No model is promoted by this command. Passing authorizes prospective shadow only.",
              f"REPORT: {rp}",f"MODELS: {mp}"]
    tp=out/"OMEGA_0.40.3_OFFBALL_LB_JOINT_BAKEOFF.txt";tp.write_text("\n".join(lines)+"\n",encoding="utf-8")
    ptr=data_root/"data/models/nfl/CURRENT_OMEGA_OFFBALL_LB_JOINT_0400";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n",encoding="utf-8");os.replace(tmp,ptr)
    print();print(tp.read_text(encoding="utf-8"))
    print("PASS OMEGA 0.40 development-only joint bakeoff · production unchanged")
    return 0

if __name__=="__main__":raise SystemExit(main())

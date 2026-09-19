#!/usr/bin/env python3
"""OMEGA 0.37.3 — chronological off-ball-LB generative challenger bake-off.

Tests a decomposed challenger against frozen H008/H012 control:
  0.37.0 predicted team off-ball-LB tackle-credit pool
  0.37.1 predicted player share of that pool
  0.37.2 combined player xTC = pool * share

Development only: 2017-2024. Evaluation folds: 2021-2024.
2025 remains sealed. 2026 outcomes/markets are not read.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse,csv,json,math,os,sys,uuid


def rcsv(path:Path):
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))


def probability_metrics(rows,pred_key,dist,params):
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


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--evaluation-seasons",default="2021,2022,2023,2024")
    ap.add_argument("--bootstrap-reps",type=int,default=1000)
    args=ap.parse_args();root=Path(args.root).expanduser().resolve()
    eval_years=[int(x) for x in args.evaluation_seasons.split(",") if x.strip()]
    if eval_years!=sorted(eval_years) or not eval_years or min(eval_years)<2018 or max(eval_years)>=2025:
        raise ValueError("evaluation seasons must be chronological development years <2025")

    sys.path[:0]=[str(root/"packages/models/nfl/omega"),str(root/"scripts/nfl")]
    import frozen_spec as fs
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import tackle_count_distribution as dist
    import lb_edge_archetype_0363 as arch
    import offball_lb_opportunity_0370 as lb
    import analyze_omega_position_specific_challenger_0360 as base

    lb.assert_development_only(range(2017,2025))
    ptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not ptr.exists():raise FileNotFoundError(ptr)
    sid=ptr.read_text(encoding="utf-8").strip()
    foundation=root/"data/normalized/nfl/omega_tackle"/sid
    exdir=root/"data/normalized/nfl/omega_tackle_exposure"/sid
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

    pspec=root/"data/models/nfl/omega_tackle_016_probability_frozen"/sid/"OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json"
    pmeta=json.loads(pspec.read_text(encoding="utf-8"))
    params=pmeta["distributionParamsFitThrough2024"]

    folds=[];pooled_players=[];pooled_teams=[]
    for year in eval_years:
        control,_,_=base.score_for_fit_year(
            fit_end=year-1,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
            fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
        )
        clean=[r for r in control if arch.explicit_role_label(r)=="OFFBALL_LB" and 2017<=int(r["season"])<=year]
        team_dec,player_dec=lb.build_decomposition_rows(clean)
        train_team=[r for r in team_dec if int(r["season"])<year]
        test_team=[r for r in team_dec if int(r["season"])==year]
        train_player=[r for r in player_dec if int(r["season"])<year]
        test_player=[r for r in player_dec if int(r["season"])==year]
        train_alloc=[r for r in train_player if float(r.get("actual_lb_pool") or 0)>0]
        test_alloc=[r for r in test_player if float(r.get("actual_lb_pool") or 0)>0]
        if min(len(train_team),len(train_player),len(test_team),len(test_player))<=0:
            raise ValueError(f"empty OMEGA 0.37 fold {year}")

        team_model=lb.fit_ridge(train_team,lb.TEAM_FEATURES,"actual_lb_pool",lb.FIXED_L2_TEAM)
        alloc_model=lb.fit_ridge(train_alloc,lb.ALLOC_FEATURES,"actual_lb_share",lb.FIXED_L2_ALLOC,clip_high=1.0)

        scored=lb.apply_combined(test_team,test_player,team_model,alloc_model)
        team_pred=[]
        team_model_map={}
        for r in test_team:
            z=dict(r);z["omega_037_team_pool"]=team_model.predict(r)
            team_pred.append(z);team_model_map[(r["game_id"],r["team"])]=z["omega_037_team_pool"]

        alloc_scored=lb.normalize_allocation_predictions(test_alloc,alloc_model)
        t_control=lb.team_metrics(team_pred,"control_lb_pool")
        t_cand=lb.team_metrics(team_pred,"omega_037_team_pool")
        a_control=lb.allocation_metrics(alloc_scored,"control_lb_share")
        a_cand=lb.allocation_metrics(alloc_scored,"predicted_lb_share")
        p_control=lb.count_metrics(scored,"control_xtc")
        p_cand=lb.count_metrics(scored,"omega_037_xtc")
        prob_control=probability_metrics(scored,"control_xtc",dist,params)
        prob_cand=probability_metrics(scored,"omega_037_xtc",dist,params)

        fold={
            "season":year,"trainTeamRows":len(train_team),"testTeamRows":len(test_team),
            "trainPlayerRows":len(train_player),"testPlayerRows":len(test_player),
            "trainAllocationRows":len(train_alloc),"testAllocationRows":len(test_alloc),
            "teamPool":{"control":t_control,"challenger":t_cand,"maeImprovement":t_control["mae"]-t_cand["mae"]},
            "allocation":{"control":a_control,"challenger":a_cand,"maeImprovement":a_control["mae"]-a_cand["mae"]},
            "player":{
                "control":p_control,"challenger":p_cand,
                "maeImprovement":p_control["mae"]-p_cand["mae"],
                "rmseImprovement":p_control["rmse"]-p_cand["rmse"],
                "biasAbsImprovement":abs(p_control["biasPredMinusActual"])-abs(p_cand["biasPredMinusActual"]),
                "controlProbability":prob_control,"challengerProbability":prob_cand,
                "brierImprovement":prob_control["brier"]-prob_cand["brier"],
            },
        }
        folds.append(fold);pooled_players.extend(scored);pooled_teams.extend(team_pred)
        print(
            f"PASS fold {year} · team {len(test_team):,} · player {len(scored):,} · "
            f"team-pool MAE {t_control['mae']:.3f}->{t_cand['mae']:.3f} · "
            f"allocation MAE {a_control['mae']:.4f}->{a_cand['mae']:.4f} · "
            f"player MAE {p_control['mae']:.3f}->{p_cand['mae']:.3f}"
        )

    # Pooled evaluation uses unique year folds.
    pbase=lb.count_metrics(pooled_players,"control_xtc")
    pcand=lb.count_metrics(pooled_players,"omega_037_xtc")
    pb=probability_metrics(pooled_players,"control_xtc",dist,params)
    pc=probability_metrics(pooled_players,"omega_037_xtc",dist,params)
    boot=lb.paired_game_bootstrap(pooled_players,"control_xtc","omega_037_xtc",args.bootstrap_reps,20260919)

    tbase=lb.team_metrics(pooled_teams,"control_lb_pool")
    tcand=lb.team_metrics(pooled_teams,"omega_037_team_pool")
    # Allocation share is defined only when the realized clean-LB pool is positive.
    pooled_alloc=[r for r in pooled_players if float(r.get("actual_lb_pool") or 0)>0]
    abase=lb.allocation_metrics(pooled_alloc,"control_lb_share")
    acand=lb.allocation_metrics(pooled_alloc,"predicted_lb_share")
    team_imp=tbase["mae"]-tcand["mae"]
    alloc_imp=abase["mae"]-acand["mae"]
    brier_imp=pb["brier"]-pc["brier"]
    gate=lb.promotion_gate(
        folds=[{"maeImprovement":f["player"]["maeImprovement"]} for f in folds],
        base=pbase,cand=pcand,brier_improvement=brier_imp,bootstrap=boot,
        team_pool_improvement=team_imp,allocation_improvement=alloc_imp,
    )

    # Fit full development-only models through 2024 for immutable research artifact.
    full_control,_,_=base.score_for_fit_year(
        fit_end=2024,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
        fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
    )
    full_clean=[r for r in full_control if arch.explicit_role_label(r)=="OFFBALL_LB" and 2017<=int(r["season"])<=2024]
    full_team,full_player=lb.build_decomposition_rows(full_clean)
    team_model=lb.fit_ridge(full_team,lb.TEAM_FEATURES,"actual_lb_pool",lb.FIXED_L2_TEAM)
    full_alloc=[r for r in full_player if float(r.get("actual_lb_pool") or 0)>0]
    alloc_model=lb.fit_ridge(full_alloc,lb.ALLOC_FEATURES,"actual_lb_share",lb.FIXED_L2_ALLOC,clip_high=1.0)

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=root/"data/models/nfl/omega_offball_lb_0370"/run_id
    out.mkdir(parents=True,exist_ok=False)
    report={
        "schemaVersion":"OMEGA_OFFBALL_LB_GENERATIVE_BAKEOFF_0.37.3",
        "version":lb.VERSION,"lineage":lb.LINEAGE,"createdAt":datetime.now(timezone.utc).isoformat(),
        "runId":run_id,"sourceSnapshotId":sid,
        "developmentSeasons":list(range(2017,2025)),"evaluationSeasons":eval_years,
        "sealedHoldoutSeason":2025,"prospectiveSeason":2026,"holdoutOpened":False,"prospectiveRowsRead":0,
        "marketFieldsRead":0,"oddsPapiRequests":0,"frozenOmegaMutation":False,"productionPromotion":False,
        "design":{
            "teamPool":"0.37.0 fixed-L2 team off-ball-LB tackle-credit pool",
            "playerAllocation":"0.37.1 fixed-L2 normalized player share of LB pool",
            "combined":"0.37.2 pool × allocation share",
            "roleUniverse":"clean explicit ILB/MLB only",
            "teamL2":lb.FIXED_L2_TEAM,"allocationL2":lb.FIXED_L2_ALLOC,
            "hyperparameterSearches":0,
        },
        "folds":folds,
        "pooled":{
            "teamPool":{"control":tbase,"challenger":tcand,"maeImprovement":team_imp},
            "allocation":{"control":abase,"challenger":acand,"maeImprovement":alloc_imp},
            "player":{"control":pbase,"challenger":pcand,
                      "maeImprovement":pbase["mae"]-pcand["mae"],
                      "rmseImprovement":pbase["rmse"]-pcand["rmse"],
                      "controlProbability":pb,"challengerProbability":pc,
                      "brierImprovement":brier_imp,"bootstrap":boot},
        },
        "gate":gate,
        "nextGate":"PROSPECTIVE_SHADOW_ONLY_IF_NEXT_STAGE_SHADOW_SIGNAL",
    }
    (out/"OMEGA_0.37.3_OFFBALL_LB_BAKEOFF.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    models={
        "version":lb.VERSION,"lineage":lb.LINEAGE,
        "status":"SHADOW_NOT_PROMOTED" if gate["status"]=="NEXT_STAGE_SHADOW_SIGNAL" else "RESEARCH_ONLY_NO_PROMOTION",
        "roleUniverse":"clean explicit ILB/MLB",
        "teamPoolModel":team_model.to_dict(),
        "playerAllocationModel":alloc_model.to_dict(),
    }
    (out/"OMEGA_0.37_OFFBALL_LB_MODELS.json").write_text(json.dumps(models,indent=2)+"\n",encoding="utf-8")

    ci=boot["ci95"]
    lines=[
        "OMEGA 0.37.3 — OFF-BALL LB GENERATIVE CHALLENGER","",
        f"Source snapshot: {sid}",
        "Development 2017-2024 · chronological evaluation 2021-2024",
        "2025 SEALED · 2026 NOT READ · market fields 0 · hyperparameter searches 0","",
        f"GATE: {gate['status']}","",
        "DECOMPOSITION",
        f"  Team LB pool MAE: {tbase['mae']:.4f} -> {tcand['mae']:.4f} · improvement {team_imp:+.4f}",
        f"  Player allocation-share MAE: {abase['mae']:.5f} -> {acand['mae']:.5f} · improvement {alloc_imp:+.5f}","",
        "COMBINED PLAYER xTC",
        f"  MAE: {pbase['mae']:.4f} -> {pcand['mae']:.4f} · improvement {pbase['mae']-pcand['mae']:+.4f}",
        f"  RMSE: {pbase['rmse']:.4f} -> {pcand['rmse']:.4f} · improvement {pbase['rmse']-pcand['rmse']:+.4f}",
        f"  Bias: {pbase['biasPredMinusActual']:+.4f} -> {pcand['biasPredMinusActual']:+.4f}",
        f"  Brier: {pb['brier']:.5f} -> {pc['brier']:.5f} · improvement {brier_imp:+.5f}",
        f"  Bootstrap MAE improvement CI: [{ci['maeImprovement']['low']:+.4f}, {ci['maeImprovement']['high']:+.4f}]",
        f"  Bootstrap RMSE improvement CI: [{ci['rmseImprovement']['low']:+.4f}, {ci['rmseImprovement']['high']:+.4f}]",
        f"  Positive MAE seasons: {gate['positiveMaeSeasons']}/4 · required >=3",
        f"  Bias gate: {'PASS' if gate['absBiasGatePass'] else 'FAIL'}","",
        "FOLDS",
    ]
    for f in folds:
        lines += [
            f"  {f['season']} · team pool {f['teamPool']['maeImprovement']:+.4f} MAE · "
            f"allocation {f['allocation']['maeImprovement']:+.5f} MAE · "
            f"player {f['player']['maeImprovement']:+.4f} MAE / {f['player']['rmseImprovement']:+.4f} RMSE / "
            f"{f['player']['brierImprovement']:+.5f} Brier",
        ]
    lines += ["","Interpretation:",
              "  Team-pool and player-allocation improvements are reported separately so volume and assignment failures cannot hide inside one aggregate metric.",
              "  No model is promoted by this command. A passing gate authorizes prospective shadow only.",
              "",f"REPORT: {out/'OMEGA_0.37.3_OFFBALL_LB_BAKEOFF.json'}",
              f"MODELS: {out/'OMEGA_0.37_OFFBALL_LB_MODELS.json'}"]
    txt=out/"OMEGA_0.37.3_OFFBALL_LB_BAKEOFF.txt";txt.write_text("\n".join(lines)+"\n",encoding="utf-8")
    ptr=root/"data/models/nfl/CURRENT_OMEGA_OFFBALL_LB_0370";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n",encoding="utf-8");os.replace(tmp,ptr)
    print();print(txt.read_text(encoding="utf-8"))
    print("PASS OMEGA 0.37 development-only bakeoff · 2025 sealed · 2026 excluded · production unchanged")
    return 0

if __name__=="__main__":raise SystemExit(main())

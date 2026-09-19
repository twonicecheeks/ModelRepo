#!/usr/bin/env python3
"""OMEGA 0.38.0 — off-ball LB room-completeness audit.

Diagnoses whether OMEGA 0.37's clean explicit ILB/MLB room is an incomplete target.

For each chronological evaluation season:
- rebuild frozen-control H008/H012 rows using only prior-season fit state;
- fit the 0.36.3 LB-vs-EDGE archetype on prior development rows;
- classify target-season generic-LB rows out-of-fold;
- add only high-confidence p(off-ball)>=0.80 generic-LB rows to the explicit room;
- measure how much player/credit/team-room coverage changes.

This command is diagnostic only. It fits no tackle challenger, reads no markets,
opens no 2025 holdout, reads no 2026 outcomes, and cannot promote a model.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse,csv,json,math,os,sys,uuid


def rcsv(path:Path):
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))


def mae_pairs(pairs):
    return fmean(abs(float(p)-float(a)) for p,a in pairs) if pairs else None


def group_rooms(rows):
    g=defaultdict(list)
    for r in rows:
        key=(str(r.get("game_id") or ""),str(r.get("team") or ""))
        if key[0] and key[1]:g[key].append(r)
    return g


def summarize_rooms(explicit_rows,added_rows):
    eg=group_rooms(explicit_rows);ag=group_rooms(added_rows)
    keys=sorted(set(eg)|set(ag))
    total_exp_actual=total_add_actual=total_complete_actual=0.0
    total_exp_control=total_add_control=0.0
    with_add=0;rooms=[]
    explicit_pairs=[];complete_pairs=[]
    for k in keys:
        er=eg.get(k,[]);ar=ag.get(k,[])
        ea=sum(float(r.get("actual_xtc") or 0) for r in er)
        ec=sum(float(r.get("control_xtc") or 0) for r in er)
        aa=sum(float(r.get("actual_xtc") or 0) for r in ar)
        ac=sum(float(r.get("control_xtc") or 0) for r in ar)
        ca=ea+aa;cc=ec+ac
        total_exp_actual+=ea;total_add_actual+=aa;total_complete_actual+=ca
        total_exp_control+=ec;total_add_control+=ac
        if ar:with_add+=1
        explicit_pairs.append((ec,ea));complete_pairs.append((cc,ca))
        rooms.append({
            "game_id":k[0],"team":k[1],
            "explicitPlayers":len(er),"addedHighConfidenceGenericLbPlayers":len(ar),
            "explicitActualCredits":ea,"addedActualCredits":aa,"completedActualCredits":ca,
            "explicitControlCredits":ec,"addedControlCredits":ac,"completedControlCredits":cc,
        })
    return {
        "teamGames":len(keys),
        "teamGamesWithHighConfidenceGenericAddition":with_add,
        "teamGameAdditionRate":with_add/len(keys) if keys else None,
        "explicitActualCredits":total_exp_actual,
        "addedActualCredits":total_add_actual,
        "completedActualCredits":total_complete_actual,
        "addedShareOfCompletedActualCredits":total_add_actual/total_complete_actual if total_complete_actual>0 else None,
        "explicitControlPoolMae":mae_pairs(explicit_pairs),
        "completedControlPoolMae":mae_pairs(complete_pairs),
        "rooms":rooms,
    }


def bin_prob(p):
    if p<.2:return "0.00-0.20"
    if p<.5:return "0.20-0.50"
    if p<.8:return "0.50-0.80"
    return "0.80-1.00"


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--evaluation-seasons",default="2021,2022,2023,2024")
    args=ap.parse_args();root=Path(args.root).expanduser().resolve()
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

    ptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not ptr.exists():raise FileNotFoundError(ptr)
    sid=ptr.read_text(encoding="utf-8").strip()
    foundation=root/"data/normalized/nfl/omega_tackle"/sid
    exdir=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    histp=rcsv(foundation/"omega_tackle_play_opportunities.csv")
    histe=rcsv(foundation/"omega_tackle_credit_events.csv")
    histex=rcsv(exdir/"omega_tackle_exposure_player_games.csv")
    if any(int(float(r.get("season") or 0))>=2025 for r in histp+histe+histex):
        raise ValueError("sealed/prospective rows entered 0.38 audit")

    teamout=xb.aggregate_team_game_outcomes(histp,histex)
    teamrows=xb.build_team_pregame_rows(teamout)
    team_snaps=xb.estimate_team_defensive_snaps(histex)
    exposure_rows=er.build_exposure_pregame_rows(histex,team_snaps)
    fam_out=tf.aggregate_team_family_opportunities(histp)
    fam_pred=tf.build_team_family_share_pregame_rows(fam_out)
    fam_map=base.family_share_map(fam_pred,fs.FAMILIES)
    pfc=tf.aggregate_player_family_credits(histe)
    topology=tf.build_player_topology_rows(histex,fam_out,pfc,team_snaps)

    folds=[];all_explicit=[];all_added=[];prob_bins=defaultdict(lambda:{"n":0,"actualCredits":0.0,"controlCredits":0.0})
    for year in years:
        control,_,_=base.score_for_fit_year(
            fit_end=year-1,teamrows=teamrows,exposure_rows=exposure_rows,topology_rows=topology,
            fam_map=fam_map,xb=xb,er=er,tf=tf,fs=fs
        )
        train=[r for r in control if 2017<=int(r["season"])<year]
        test=[r for r in control if int(r["season"])==year]
        model=arch.fit(train,arch.FIXED_L2)

        explicit=[r for r in test if arch.explicit_role_label(r)=="OFFBALL_LB"]
        generic=[r for r in test if arch.explicit_role_label(r)=="AMBIG_LB"]
        added=[];blocked=[]
        for r in generic:
            p=model.probability_offball(r)
            z=dict(r);z["audit_offball_probability"]=p
            b=prob_bins[bin_prob(p)];b["n"]+=1
            b["actualCredits"]+=float(r.get("actual_xtc") or 0)
            b["controlCredits"]+=float(r.get("control_xtc") or 0)
            if p>=arch.GENERIC_LB_OFFBALL_THRESHOLD:added.append(z)
            else:blocked.append(z)

        s=summarize_rooms(explicit,added)
        exp_player_mae=mae_pairs([(r["control_xtc"],r["actual_xtc"]) for r in explicit])
        add_player_mae=mae_pairs([(r["control_xtc"],r["actual_xtc"]) for r in added])
        fold={
            "season":year,
            "archetypeTrainingRows":len(train),
            "explicitOffballPlayers":len(explicit),
            "genericLbPlayers":len(generic),
            "highConfidenceGenericOffballPlayers":len(added),
            "blockedGenericLbPlayers":len(blocked),
            "highConfidenceAdditionRateAmongGeneric":len(added)/len(generic) if generic else None,
            "explicitPlayerControlMae":exp_player_mae,
            "addedGenericPlayerControlMae":add_player_mae,
            "roomSummary":{k:v for k,v in s.items() if k!="rooms"},
        }
        folds.append(fold);all_explicit.extend(explicit);all_added.extend(added)
        print(
            f"PASS {year} · explicit {len(explicit):,} · generic {len(generic):,} · "
            f"high-conf off-ball added {len(added):,} · rooms with additions {s['teamGameAdditionRate']:.1%} · "
            f"added tackle-credit share {s['addedShareOfCompletedActualCredits']:.1%}"
        )

    pooled=summarize_rooms(all_explicit,all_added)
    pooled_no_rooms={k:v for k,v in pooled.items() if k!="rooms"}
    added_n=len(all_added);explicit_n=len(all_explicit)
    material=bool(
        (pooled.get("addedShareOfCompletedActualCredits") or 0)>=.10
        or (pooled.get("teamGameAdditionRate") or 0)>=.20
    )
    conclusion=(
        "EXPLICIT_ONLY_ROOM_MATERIALLY_INCOMPLETE"
        if material else "EXPLICIT_ONLY_ROOM_NOT_MATERIALLY_INCOMPLETE"
    )
    next_gate=(
        "BUILD_0.38_ARCHETYPE_COMPLETE_ROOM_CHALLENGER"
        if material else "ABANDON_TEAM_POOL_DECOMPOSITION_AND_RESEARCH_OTHER_LB_MECHANISMS"
    )

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=root/"data/models/nfl/omega_lb_room_audit_0380"/run_id
    out.mkdir(parents=True,exist_ok=False)
    report={
        "schemaVersion":"OMEGA_LB_ROOM_COMPLETENESS_AUDIT_0.38.0",
        "createdAt":datetime.now(timezone.utc).isoformat(),"runId":run_id,"sourceSnapshotId":sid,
        "evaluationSeasons":years,"sealedHoldoutSeason":2025,"prospectiveSeason":2026,
        "holdoutOpened":False,"prospectiveRowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,
        "classifier":{"version":arch.VERSION,"threshold":arch.GENERIC_LB_OFFBALL_THRESHOLD,
                      "fitPolicy":"prior seasons only for each target season"},
        "folds":folds,
        "pooled":{
            "explicitOffballPlayers":explicit_n,
            "highConfidenceGenericOffballPlayersAdded":added_n,
            **pooled_no_rooms,
            "genericProbabilityBins":dict(sorted(prob_bins.items())),
        },
        "materialityRule":"added tackle-credit share >=10% OR team-game addition rate >=20%",
        "conclusion":conclusion,"nextGate":next_gate,
        "integrity":{"modelPromotion":False,"tackleChallengerFit":False,"frozenOmegaMutation":False},
    }
    jp=out/"OMEGA_0.38.0_LB_ROOM_COMPLETENESS_AUDIT.json";jp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    lines=[
        "OMEGA 0.38.0 — OFF-BALL LB ROOM COMPLETENESS AUDIT","",
        f"Source snapshot: {sid}",
        "2025 SEALED · 2026 NOT READ · markets 0 · tackle challenger fit 0","",
        f"CONCLUSION: {conclusion}",
        f"NEXT GATE: {next_gate}","",
        "POOLED",
        f"  explicit off-ball player rows: {explicit_n:,}",
        f"  high-confidence generic-LB rows added: {added_n:,}",
        f"  team games: {pooled['teamGames']:,}",
        f"  rooms with >=1 high-confidence generic addition: {pooled['teamGamesWithHighConfidenceGenericAddition']:,} ({pooled['teamGameAdditionRate']:.1%})",
        f"  added share of completed actual LB tackle credits: {pooled['addedShareOfCompletedActualCredits']:.1%}",
        f"  explicit-room control pool MAE: {pooled['explicitControlPoolMae']:.4f}",
        f"  completed-room control pool MAE: {pooled['completedControlPoolMae']:.4f}","",
        "FOLDS",
    ]
    for f in folds:
        s=f["roomSummary"]
        lines.append(
            f"  {f['season']} · generic {f['genericLbPlayers']:,} · high-conf added {f['highConfidenceGenericOffballPlayers']:,} · "
            f"rooms +generic {s['teamGameAdditionRate']:.1%} · added credit share {s['addedShareOfCompletedActualCredits']:.1%}"
        )
    lines += ["","This is a diagnostic only; it cannot promote or refit OMEGA.",
              f"REPORT: {jp}"]
    tp=out/"OMEGA_0.38.0_LB_ROOM_COMPLETENESS_AUDIT.txt";tp.write_text("\n".join(lines)+"\n",encoding="utf-8")
    ptr=root/"data/models/nfl/CURRENT_OMEGA_LB_ROOM_AUDIT_0380";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n",encoding="utf-8");os.replace(tmp,ptr)
    print();print(tp.read_text(encoding="utf-8"))
    print("PASS OMEGA 0.38 room audit · diagnostic only · 2025 sealed · 2026 excluded")
    return 0

if __name__=="__main__":raise SystemExit(main())

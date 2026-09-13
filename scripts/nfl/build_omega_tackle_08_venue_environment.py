#!/usr/bin/env python3
"""Build OMEGA 0.8 H005 venue/year credit-environment challenger."""
from __future__ import annotations

import argparse, csv, json, math, random, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_TACKLE_VENUE_CREDIT_ENVIRONMENT_CHALLENGER_0.8"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 290080


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_csv_without_2025(path: Path) -> list[dict[str, str]]:
    out=[]
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try: season=int(float(r.get("season") or 0))
            except Exception: season=0
            if season == 2025:
                continue
            out.append(r)
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        w.writeheader()
        for r in rows: w.writerow({k:"" if r.get(k) is None else r.get(k) for k in fields})


def num(v: Any, default: float=0.0) -> float:
    try:
        if v in (None,""): return default
        x=float(v); return default if math.isnan(x) else x
    except (TypeError,ValueError): return default


def metrics(rows: Sequence[dict[str,Any]], actual: str, pred: str) -> dict[str,Any]:
    if not rows: return {"n":0,"mae":0.0,"rmse":0.0,"bias":0.0,"actualMean":0.0,"predictedMean":0.0}
    y=[num(r.get(actual)) for r in rows]; p=[num(r.get(pred)) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(a-b) for a,b in zip(y,p)),"rmse":math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),"bias":fmean(b-a for a,b in zip(y,p)),"actualMean":fmean(y),"predictedMean":fmean(p)}


def compare(rows: Sequence[dict[str,Any]], actual: str, challenger: str, baseline: str) -> dict[str,Any]:
    c=metrics(rows,actual,challenger); b=metrics(rows,actual,baseline)
    return {"challenger":c,"baseline":b,"maeImprovement":b["mae"]-c["mae"],"maeImprovementPct":100*(b["mae"]-c["mae"])/b["mae"] if b["mae"] else None,"rmseImprovement":b["rmse"]-c["rmse"]}


def percentile(xs: Sequence[float], p: float) -> float:
    z=sorted(xs)
    if not z: return 0.0
    q=max(0.0,min(1.0,p))*(len(z)-1); lo=int(math.floor(q)); hi=int(math.ceil(q))
    if lo==hi:return z[lo]
    w=q-lo; return z[lo]*(1-w)+z[hi]*w


def cluster_bootstrap(rows: Sequence[dict[str,Any]], actual: str, challenger: str, baseline: str, seed_offset: int=0) -> dict[str,Any]:
    by=defaultdict(list)
    for r in rows:
        by[str(r.get("game_id") or "")].append((num(r.get(actual)),num(r.get(challenger)),num(r.get(baseline))))
    keys=sorted(k for k in by if k); rng=random.Random(BOOTSTRAP_SEED+seed_offset); ds=[]
    if not keys: return {"clusters":0,"reps":0,"maeImprovementCI95":[0.0,0.0],"probabilityPositive":0.0,"maeImprovementPoint":0.0}
    for _ in range(BOOTSTRAP_REPS):
        ec=eb=0.0;n=0
        for _j in range(len(keys)):
            k=keys[rng.randrange(len(keys))]
            for a,c,b in by[k]: ec+=abs(a-c);eb+=abs(a-b);n+=1
        ds.append((eb-ec)/n)
    point=compare(rows,actual,challenger,baseline)
    return {"cluster":"game_id","clusters":len(keys),"reps":BOOTSTRAP_REPS,"seed":BOOTSTRAP_SEED+seed_offset,"maeImprovementPoint":point["maeImprovement"],"maeImprovementCI95":[percentile(ds,.025),percentile(ds,.975)],"probabilityPositive":sum(x>0 for x in ds)/len(ds)}


def corr(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs)<2 or len(xs)!=len(ys): return 0.0
    mx=fmean(xs);my=fmean(ys);sx=sum((x-mx)**2 for x in xs);sy=sum((y-my)**2 for y in ys)
    if sx<=0 or sy<=0:return 0.0
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/math.sqrt(sx*sy)


def calibration(rows: Sequence[dict[str,Any]], pred: str) -> dict[str,float]:
    xs=[num(r.get(pred)) for r in rows]; ys=[num(r.get("actual_xtc")) for r in rows]
    if len(xs)<2:return {"intercept":0.0,"slope":0.0,"r2":0.0}
    mx=fmean(xs);my=fmean(ys);sxx=sum((x-mx)**2 for x in xs)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sxx if sxx>0 else 0.0; intercept=my-slope*mx
    sst=sum((y-my)**2 for y in ys);sse=sum((y-(intercept+slope*x))**2 for x,y in zip(xs,ys))
    return {"intercept":intercept,"slope":slope,"r2":1-sse/sst if sst>0 else 0.0}


def main() -> int:
    ap=argparse.ArgumentParser();ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL");args=ap.parse_args()
    root=Path(args.root).resolve();sys.path.insert(0,str(root/"packages/models/nfl/omega"))
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import assist_primary_decomposition as ad
    import venue_credit_environment as ve

    ptrs={
      "phase1":root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT",
      "foundation":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION",
      "exposure":root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE",
      "baseline":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE",
      "role":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER",
      "opp":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_OPPORTUNITY_CHALLENGER",
      "footprint":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FOOTPRINT_CHALLENGER",
      "funnel":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FUNNEL_CHALLENGER",
      "roleconv":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_ROLE_CONVEXITY_CHALLENGER",
      "assist":root/"data/models/nfl/CURRENT_OMEGA_TACKLE_ASSIST_DECOMP_CHALLENGER",
    }
    for p in ptrs.values():
        if not p.exists(): raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    sid=ptrs["foundation"].read_text(encoding="utf-8").strip()
    if any(p.read_text(encoding="utf-8").strip()!=sid for p in ptrs.values()): raise SystemExit("FAIL OMEGA/Phase1 prerequisite pointers disagree")

    foundation=root/"data/normalized/nfl/omega_tackle"/sid
    exposure=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    phase1=root/"data/normalized/nfl/phase1"/sid
    base=root/"data/models/nfl/omega_tackle_02"/sid
    role=root/"data/models/nfl/omega_tackle_022_exposure"/sid
    opp=root/"data/models/nfl/omega_tackle_03_opportunity"/sid
    footprint=root/"data/models/nfl/omega_tackle_04_footprint"/sid
    funnel=root/"data/models/nfl/omega_tackle_05_funnel"/sid
    roleconv=root/"data/models/nfl/omega_tackle_06_role_convexity"/sid
    assist=root/"data/models/nfl/omega_tackle_07_assist_decomp"/sid
    req=[
      foundation/"OMEGA_TACKLE_FOUNDATION_AUDIT.json",foundation/"omega_tackle_play_opportunities.csv",foundation/"omega_tackle_credit_events.csv",
      exposure/"OMEGA_TACKLE_EXPOSURE_AUDIT.json",exposure/"omega_tackle_exposure_player_games.csv",
      phase1/"game_identity.csv",base/"OMEGA_0.2_AUDIT.json",role/"OMEGA_0.2.2_AUDIT.json",opp/"OMEGA_0.3_AUDIT.json",
      footprint/"OMEGA_0.4_AUDIT.json",footprint/"omega_2024_footprint_validation.csv",funnel/"OMEGA_0.5_AUDIT.json",
      roleconv/"OMEGA_0.6_AUDIT.json",assist/"OMEGA_0.7_AUDIT.json",assist/"omega_2024_assist_primary_validation.csv",
    ]
    for p in req:
        if not p.exists():raise SystemExit(f"FAIL required source missing: {p}")

    fa=json.loads(req[0].read_text());ea=json.loads(req[3].read_text());ba=json.loads(req[6].read_text());ra=json.loads(req[7].read_text());oa=json.loads(req[8].read_text());fpa=json.loads(req[9].read_text());fua=json.loads(req[11].read_text());rca=json.loads(req[12].read_text());ada=json.loads(req[13].read_text())
    seals=[fa.get("omegaHoldoutPbpRowsRead",0),ea.get("omegaHoldoutRowsRead",0),ba.get("integrity",{}).get("omega2025RowsRead",0),ra.get("integrity",{}).get("omega2025RowsRead",0),oa.get("integrity",{}).get("omega2025RowsRead",0),fpa.get("integrity",{}).get("omega2025RowsRead",0),fua.get("integrity",{}).get("omega2025RowsRead",0),rca.get("integrity",{}).get("omega2025RowsRead",0),ada.get("integrity",{}).get("omega2025RowsRead",0)]
    if any(int(x)!=0 for x in seals):raise SystemExit("FAIL OMEGA 2025 seal not clean")
    if str(ra.get("verdict"))!="H012_EXPOSURE_CHALLENGER_PASS":raise SystemExit("FAIL H012 not frozen PASS")
    if str(oa.get("verdict"))!="H011_FAIL":raise SystemExit("FAIL H011 expected rejected")
    if str(fpa.get("verdict"))!="H008_TACKLE_OPPORTUNITY_FOOTPRINT_PASS":raise SystemExit("FAIL H008 not frozen PASS")
    if str(fua.get("verdict")) not in {"H002_MIXED","H002_FAIL"}:raise SystemExit("FAIL H002 unexpectedly promoted")
    if str(rca.get("verdict"))!="H003_FAIL":raise SystemExit("FAIL H003 expected rejected")
    if str(ada.get("verdict")) not in {"H004_DIRECTIONAL_PASS","H004_ASSIST_PRIMARY_DECOMPOSITION_PASS"}:raise SystemExit(f"FAIL H005 requires usable H004 decomposition scaffold: {ada.get('verdict')}")

    exposure_rows=read_csv(exposure/"omega_tackle_exposure_player_games.csv")
    plays=read_csv(foundation/"omega_tackle_play_opportunities.csv")
    events=read_csv(foundation/"omega_tackle_credit_events.csv")
    if any(int(num(r.get("season")))==2025 for r in exposure_rows+plays+events):raise SystemExit("FAIL 2025 tackle row read")
    identity_rows=read_csv_without_2025(phase1/"game_identity.csv")
    game_identity=ve.build_game_identity_map(identity_rows)

    team_outcomes=xb.aggregate_team_game_outcomes(plays,exposure_rows);team_rows=xb.build_team_pregame_rows(team_outcomes);team_snap_totals=xb.estimate_team_defensive_snaps(exposure_rows)
    role_rows=er.build_exposure_pregame_rows(exposure_rows,team_snap_totals)
    family_outcomes=tf.aggregate_team_family_opportunities(plays);family_share_rows=tf.build_team_family_share_pregame_rows(family_outcomes)
    family_share_by_season=defaultdict(dict)
    for r in family_share_rows: family_share_by_season[int(r["season"])][(r["game_id"],r["defense_team"])]= {f:float(r[f"pred_share_{f}"]) for f in tf.FAMILIES}
    class_credits=ad.aggregate_player_family_credit_classes(events,tf.FAMILIES)
    class_rows=ad.build_player_credit_class_rows(exposure_rows,family_outcomes,class_credits,team_snap_totals,tf.FAMILIES)
    mismatches=[r for r in class_rows if abs(float(r["actual_credit_class_sum"])-float(r["actual_xtc"]))>1e-9]
    if mismatches:raise SystemExit(f"FAIL H005 credit-class reconciliation mismatches: {len(mismatches)}")

    xto_l2=float(ba["selection"]["xTOL2"]);role_l2=float(ra["selection"]["selectedL2"]);h008_alpha=float(fpa["selection"]["familyOpportunityShrinkageAlpha"])
    primary_alpha=float(ada["selection"]["primaryAlpha"]);assist_alpha=float(ada["selection"]["assistAlpha"])

    # Reconstruct strictly chronological H004 research-scaffold predictions for 2021-2023.
    dev_scored=[]
    for year in ve.DEV_VENUE_SEASONS:
        ttrain=[r for r in team_rows if 2017<=int(r["season"])<year];tval=[r for r in team_rows if int(r["season"])==year]
        rrtrain=[r for r in role_rows if 2017<=int(r["season"])<year];rrval=[r for r in role_rows if int(r["season"])==year]
        pval=[r for r in class_rows if int(r["season"])==year]
        if not ttrain or not tval or not rrtrain or not rrval or not pval:raise SystemExit(f"FAIL insufficient H005 chronological scaffold rows for {year}")
        xm=xb.fit_ridge(ttrain,target_key="actual_opportunity_plays",l2=xto_l2);em=er.fit_ridge(rrtrain,role_l2)
        xpred={(r["game_id"],r["defense_team"]):xm.predict([float(r[n]) for n in xb.TEAM_FEATURE_NAMES]) for r in tval}
        epred={(r["game_id"],r["team"],r["player_id"]):em.predict(r) for r in rrval}
        scored=ad.score_rows(pval,primary_alpha=primary_alpha,assist_alpha=assist_alpha,xto_predictions=xpred,exposure_predictions=epred,family_share_predictions=family_share_by_season.get(year,{}),families=tf.FAMILIES)
        dev_scored.extend(scored)
    dev_games=ve.aggregate_game_credit_predictions(dev_scored)
    prior=ve.build_environment_prior(dev_games,game_identity)

    h004_2024=read_csv(assist/"omega_2024_assist_primary_validation.csv")
    h008_2024=read_csv(footprint/"omega_2024_footprint_validation.csv")
    scored2024=ve.apply_environment(h004_2024,game_identity,prior)
    h008map={(r.get("game_id"),r.get("team"),r.get("player_id")):r for r in h008_2024}
    joined=[]
    for r in scored2024:
        b=h008map.get((r.get("game_id"),r.get("team"),r.get("player_id")))
        if b is None:continue
        z=dict(r);z["h008_xtc"]=num(b.get("topology_xtc"));z["raw_last4_xtc"]=num(b.get("raw_last4_xtc"));joined.append(z)
    if not joined:raise SystemExit("FAIL no H005 2024 joined rows")

    overall_vs_h008=compare(joined,"actual_xtc","h005_xtc","h008_xtc")
    overall_vs_h004=compare(joined,"actual_xtc","h005_xtc","h004_xtc")
    year_only_vs_h004=compare(joined,"actual_xtc","h005_year_only_xtc","h004_xtc")
    assist_vs_h004=compare(joined,"actual_assist_total","h005_assist","pred_assist_total")
    assist_venue_vs_year=compare(joined,"actual_assist_total","h005_assist","h005_year_only_assist")
    boot_ta=cluster_bootstrap(joined,"actual_xtc","h005_xtc","h008_xtc",0)
    boot_assist=cluster_bootstrap(joined,"actual_assist_total","h005_assist","pred_assist_total",1)
    boot_venue=cluster_bootstrap(joined,"actual_assist_total","h005_assist","h005_year_only_assist",2)

    by_pos={}
    for pg in sorted({str(r.get("position_group") or "UNK") for r in joined}):
        rr=[r for r in joined if str(r.get("position_group") or "UNK")==pg];by_pos[pg]=compare(rr,"actual_xtc","h005_xtc","h008_xtc")
    core=[r for r in joined if str(r.get("position_group")) in {"DB","DL","LB"}];corecmp=compare(core,"actual_xtc","h005_xtc","h008_xtc")
    pos_improved=sum(1 for pg in ("DB","DL","LB") if by_pos.get(pg,{}).get("maeImprovement",0)>0)

    # Venue persistence diagnostic: development venue residual vs 2024 aggregated assist residual.
    game2024=ve.aggregate_game_credit_predictions(joined)
    venue2024=defaultdict(lambda:{"games":0,"actual":0.0,"pred":0.0})
    for g in game2024:
        meta=game_identity.get(str(g.get("game_id") or ""),{})
        if not ve.is_home_location(meta.get("location")):continue
        venue=str(meta.get("source_home_team") or "")
        if not venue:continue
        venue2024[venue]["games"]+=1;venue2024[venue]["actual"]+=num(g.get("actual_assist"));venue2024[venue]["pred"]+=num(g.get("pred_assist"))
    venue_diag=[];xs=[];ys=[]
    devglobal=float(prior["development_global_assist_ratio"])
    for venue,p in sorted(prior["venue_profiles"].items()):
        v24=venue2024.get(venue)
        if not v24 or v24["pred"]<=0:continue
        actual24ratio=v24["actual"]/v24["pred"]
        relative24=actual24ratio/(sum(v["actual"] for v in venue2024.values())/sum(v["pred"] for v in venue2024.values())) if sum(v["pred"] for v in venue2024.values())>0 else 1.0
        x=float(p["shrunk_relative_assist_multiplier"]);y=relative24
        xs.append(x);ys.append(y)
        venue_diag.append({"venue_proxy":venue,"dev_games":p["games"],"dev_relative_multiplier":x,"2024_games":v24["games"],"2024_actual_assist":v24["actual"],"2024_h004_pred_assist":v24["pred"],"2024_relative_assist_ratio":y})
    venue_persistence_corr=corr(xs,ys)

    cal_h008=calibration(joined,"h008_xtc");cal_h005=calibration(joined,"h005_xtc")
    ta_pass=(overall_vs_h008["maeImprovement"]>0 and corecmp["maeImprovement"]>0 and pos_improved>=2 and boot_ta["maeImprovementCI95"][0]>0)
    assist_pass=(assist_vs_h004["maeImprovement"]>0 and boot_assist["maeImprovementCI95"][0]>0)
    venue_incremental=(assist_venue_vs_year["maeImprovement"]>0 and boot_venue["maeImprovementCI95"][0]>0 and venue_persistence_corr>0)
    if ta_pass and assist_pass and venue_incremental: verdict="H005_VENUE_YEAR_TA_PASS"
    elif assist_pass and venue_incremental: verdict="H005_ASSIST_ENVIRONMENT_DIAGNOSTIC_PASS"
    elif assist_pass and not venue_incremental: verdict="H005_YEAR_ENVIRONMENT_ONLY_SIGNAL"
    elif overall_vs_h008["maeImprovement"]>0 or assist_vs_h004["maeImprovement"]>0: verdict="H005_MIXED"
    else: verdict="H005_FAIL"

    outbase=root/"data/models/nfl/omega_tackle_08_venue_environment";out=outbase/sid
    if out.exists():raise SystemExit(f"Refusing overwrite immutable OMEGA 0.8 output: {out}")
    staging=outbase/("."+sid+".staging");staging.mkdir(parents=True,exist_ok=False)
    try:
        write_csv(staging/"omega_2024_venue_environment_validation.csv",joined)
        write_csv(staging/"omega_0.8_venue_profiles_development.csv",[{"venue_proxy":k,**v} for k,v in sorted(prior["venue_profiles"].items())])
        write_csv(staging/"omega_0.8_venue_persistence_2024.csv",venue_diag)
        audit={
          "schemaVersion":SCHEMA,"generatedAt":now(),"sourceSnapshotId":sid,
          "integrity":{"omega2025TackleRowsRead":0,"omega2025ScheduleRowsUsed":0,"marketFieldsRead":0,"oddsPapiRequests":0,"postseasonIncluded":False,"h012Frozen":True,"h008Frozen":True,"h011Rejected":True,"h002Promoted":False,"h003Rejected":True,"h004TackleChampionPromoted":False,"sportsbookSettlementAssumed":False},
          "preregisteredHypothesis":{"id":"H005","name":"Venue / credit environment","origin":"OMEGA 0.1 hypothesis registry","mechanism":"Human scoring may create persistent venue-level solo/assist tendencies after football opportunity and player mix are controlled.","expectedDirection":"A pre-2024 assist-credit environment should improve 2024 assist prediction only if the scoring tendency persists out of sample."},
          "importantLimitation":{"venueIdentifier":"source_home_team for schedule rows with location=Home","actualStadiumOrScorerIdentityAvailable":False,"interpretation":"home-franchise venue proxy only; any signal requires later stadium/scorer verification before production"},
          "h004Context":{"verdict":ada.get("verdict"),"primaryAlpha":primary_alpha,"assistAlpha":assist_alpha,"promotionPolicy":"H004 decomposition used only as H005 research scaffold; H008 remains T+A champion unless H005 robustly beats it."},
          "environmentPrior":{"developmentSeasons":list(ve.DEV_VENUE_SEASONS),"yearAnchorSeason":ve.YEAR_ANCHOR_SEASON,"venueFullWeightGames":ve.VENUE_FULL_WEIGHT_GAMES,"developmentGlobalAssistRatio":prior["development_global_assist_ratio"],"yearAssistMultiplier":prior["year_assist_multiplier"],"venueProfiles":len(prior["venue_profiles"]),"excludedNonhomeOrUnknownGames":prior["excluded_nonhome_or_unknown_games"]},
          "formula":{"yearOnlyAssist":"H004 predicted assist * 2023 league actual/predicted assist ratio","venueRelative":"2021-2023 venue actual/predicted assist ratio divided by 2021-2023 league ratio, credibility-weighted toward 1 until 24 home games","h005Assist":"H004 predicted assist * year multiplier * venue-relative multiplier","h005Primary":"H004 predicted primary unchanged","h005Combined":"h005Primary + h005Assist"},
          "validation2024":{"rows":len(joined),"combinedVsH008":overall_vs_h008,"combinedVsH004":overall_vs_h004,"yearOnlyCombinedVsH004":year_only_vs_h004,"assistVsH004":assist_vs_h004,"assistVenuePlusYearVsYearOnly":assist_venue_vs_year,"coreDBDLLBVsH008":corecmp,"positiveCorePositions":pos_improved,"byPosition":by_pos,"bootstrapCombinedVsH008":boot_ta,"bootstrapAssistVsH004":boot_assist,"bootstrapVenueAssistVsYearOnly":boot_venue,"venuePersistenceCorrelation":venue_persistence_corr,"venuePersistencePairs":len(venue_diag),"calibrationH008":cal_h008,"calibrationH005":cal_h005},
          "verdict":verdict,
          "nextGate":"If H005 produces a robust venue-specific assist signal, preserve it only as a credit-environment component and verify actual stadium/stat-crew identity before production. H008 remains the T+A champion unless the combined-count gate is passed. OMEGA 2025 remains sealed."
        }
        (staging/"OMEGA_0.8_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        pos_lines=[]
        for pg,v in by_pos.items():
            pct=v.get("maeImprovementPct");pt=f"{pct:+.2f}%" if pct is not None else "n/a";pos_lines.append(f"- {pg}: n={v['challenger']['n']} · H005 MAE {v['challenger']['mae']:.4f} · H008 {v['baseline']['mae']:.4f} · improvement {pt}")
        md=f"""# OMEGA Tackle Model 0.8 — Venue / Year Credit Environment Audit

Generated: {audit['generatedAt']}

**SINGLE PRE-REGISTERED MECHANISM: H005. H008 REMAINS THE FROZEN T+A CHAMPION. H004 IS A CREDIT-CLASS RESEARCH SCAFFOLD, NOT A PROMOTED T+A MODEL. NO MARKET DATA. OMEGA 2025 REMAINS SEALED.**

## Why H005 follows H004

H004 selected materially different shrinkage for primary (**{primary_alpha}**) and assist (**{assist_alpha}**) credit, but its combined T+A gain was only directional and its bootstrap interval crossed zero. OMEGA therefore does **not** promote H004 over H008. H005 uses the H004 decomposition only to test the pre-registered scoring-environment question: does assist credit show a persistent venue/year residual after player, role, play-family and opportunity effects are already modeled?

## Critical venue limitation

The frozen Phase1 schedule artifact has `source_home_team` and `location`, but no actual stadium ID or statistician/crew ID. Therefore H005 uses **source home franchise as a venue proxy only when `location=Home`**. Neutral-site games receive no venue adjustment. A positive result would be a lead to investigate, not proof of a scorer effect.

## Integrity

- Source snapshot: `{sid}`
- 2025 tackle rows read: **0**
- 2025 schedule rows used: **0**
- Market fields read: **0**
- OddsPapi requests: **0**
- H012 exposure changed: **NO**
- H008 topology changed: **NO**
- H004 promoted as T+A champion: **NO**
- Sportsbook settlement convention assumed: **NO**

## H005 mechanism

Development venue prior: **2021–2023**. Year anchor: **2023**.

`year_multiplier = league actual assists / H004 predicted assists in 2023`

`venue_relative = (venue actual/pred assist ratio in 2021–2023) / (league actual/pred assist ratio in 2021–2023)`

The venue-relative factor is credibility-weighted toward 1.0 until **24 prior home games** are available.

`H005 assist = H004 predicted assist × year_multiplier × venue_relative`

`H005 primary = H004 predicted primary` (unchanged)

`H005 T+A = H005 primary + H005 assist`

## Development environment prior

- 2021–2023 league assist actual/pred ratio: **{prior['development_global_assist_ratio']:.4f}**
- 2023 year assist multiplier: **{prior['year_assist_multiplier']:.4f}**
- Venue proxies with development history: **{len(prior['venue_profiles'])}**
- Neutral/unknown development games excluded from venue prior: **{prior['excluded_nonhome_or_unknown_games']}**

## 2024 combined T+A result

- Rows: **{len(joined)}**
- H005 MAE vs H008: **{overall_vs_h008['challenger']['mae']:.4f}** vs **{overall_vs_h008['baseline']['mae']:.4f}** · improvement **{overall_vs_h008['maeImprovement']:+.4f}** ({overall_vs_h008['maeImprovementPct']:+.2f}%)
- H005 RMSE improvement vs H008: **{overall_vs_h008['rmseImprovement']:+.4f}**
- Bootstrap combined Δ (H008 - H005): **{boot_ta['maeImprovementPoint']:+.4f}**, 95% CI **[{boot_ta['maeImprovementCI95'][0]:+.4f}, {boot_ta['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{boot_ta['probabilityPositive']:.3f}**
- Core DB/DL/LB positions improved: **{pos_improved}/3**

## Assist-environment result

- H005 assist MAE vs H004 assist: **{assist_vs_h004['challenger']['mae']:.4f}** vs **{assist_vs_h004['baseline']['mae']:.4f}** · improvement **{assist_vs_h004['maeImprovement']:+.4f}** ({assist_vs_h004['maeImprovementPct']:+.2f}%)
- Bootstrap assist Δ (H004 - H005): **{boot_assist['maeImprovementPoint']:+.4f}**, 95% CI **[{boot_assist['maeImprovementCI95'][0]:+.4f}, {boot_assist['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{boot_assist['probabilityPositive']:.3f}**
- Venue incremental assist improvement over year-only: **{assist_venue_vs_year['maeImprovement']:+.4f}** ({assist_venue_vs_year['maeImprovementPct']:+.2f}%)
- Bootstrap venue incremental Δ (year-only - venue+year): **{boot_venue['maeImprovementPoint']:+.4f}**, 95% CI **[{boot_venue['maeImprovementCI95'][0]:+.4f}, {boot_venue['maeImprovementCI95'][1]:+.4f}]**, P(Δ>0) **{boot_venue['probabilityPositive']:.3f}**
- Corr(development venue assist residual, 2024 venue assist residual): **{venue_persistence_corr:.4f}** across **{len(venue_diag)}** venue proxies

## Position slices vs H008 T+A champion

{chr(10).join(pos_lines)}

## Count calibration

- H008 actual~predicted: intercept **{cal_h008['intercept']:.4f}**, slope **{cal_h008['slope']:.4f}**, R² **{cal_h008['r2']:.4f}**
- H005 actual~predicted: intercept **{cal_h005['intercept']:.4f}**, slope **{cal_h005['slope']:.4f}**, R² **{cal_h005['r2']:.4f}**

## Verdict

**{verdict}**

This is predictive research only. It is not evidence of sportsbook edge or proof of an NFL scorer effect.

## Next gate

If H005 produces a robust venue-specific assist signal, preserve it only as a credit-environment component and verify actual stadium/stat-crew identity before production. **H008 remains the T+A champion unless the combined-count gate is passed.** If venue adds nothing beyond year calibration, reject the venue hypothesis without rescue and move to another pre-registered mechanism. OMEGA 2025 remains sealed.
"""
        (staging/"OMEGA_0.8_AUDIT.md").write_text(md,encoding="utf-8")
        (staging/"OMEGA_0.8_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"verdict":verdict,"files":[p.name for p in staging.iterdir() if p.is_file()]},indent=2)+"\n",encoding="utf-8")
        staging.rename(out)
        (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_VENUE_ENVIRONMENT_CHALLENGER").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True);raise

    print("OMEGA 0.8 VENUE / YEAR CREDIT ENVIRONMENT")
    print()
    print(f"PASS source snapshot: {sid}")
    print(f"PASS H004 decomposition scaffold: primary alpha {primary_alpha} · assist alpha {assist_alpha} · not promoted as T+A champion")
    print(f"PASS 2024 assist delta vs H004: {assist_vs_h004['maeImprovement']:+.6f} · venue incremental {assist_venue_vs_year['maeImprovement']:+.6f}")
    print(f"PASS 2024 combined delta vs H008: {overall_vs_h008['maeImprovement']:+.6f} · verdict {verdict}")
    print("PASS OMEGA 2025 tackle data untouched · schedule 2025 unused · market fields 0 · OddsPapi 0")
    print()
    print("REPORT:",out/"OMEGA_0.8_AUDIT.md")
    return 0

if __name__=="__main__":raise SystemExit(main())

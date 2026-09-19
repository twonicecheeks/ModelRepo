#!/usr/bin/env python3
"""OMEGA 0.43.1 — strict-prior-day off-ball-LB injury/practice signal audit.

DIAGNOSTIC ONLY. NO MODEL FIT.

Uses only rows from the immutable OMEGA 0.43 injury source audit whose
date_modified is strictly before scheduled gameday. SAME_GAMEDAY, AFTER_GAMEDAY,
MISSING_DATE and unjoined records are not eligible.

For clean explicit ILB/MLB chronological control rows (2021-2024), audit whether
pregame injury/practice state identifies H012 snap-share residual structure.

Player state hierarchy:
  OUT > DOUBTFUL > QUESTIONABLE > PRACTICE_DNP > PRACTICE_LIMITED
      > PRACTICE_FULL > REPORT_BLANK > NOT_LISTED

Room context:
- count/share of other clean off-ball LBs with strict-prior injury/practice reports;
- count of teammates OUT/DOUBTFUL/QUESTIONABLE;
- strongest teammate severity.

No sportsbook fields. 2025 sealed. 2026 not read.
"""
from __future__ import annotations

from collections import Counter,defaultdict
from datetime import datetime, timezone, date
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


def asint(v,d=0):
    try:return int(float(v))
    except:return d


def normteam(v):
    x=str(v or "").strip().upper()
    return {"ARZ":"ARI","BLT":"BAL","CLV":"CLE","GNB":"GB","JAC":"JAX","KAN":"KC",
            "LVR":"LV","OAK":"LV","LAR":"LA","STL":"LA","SD":"LAC","NWE":"NE",
            "NOR":"NO","SFO":"SF","TAM":"TB","WSH":"WAS"}.get(x,x)


def parse_date(v):
    if v in (None,""):return None
    s=str(v).strip()
    if not s:return None
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).date()
    except Exception:
        try:return date.fromisoformat(s[:10])
        except Exception:return None


def timing_class(modified,gameday):
    md=parse_date(modified);gd=parse_date(gameday)
    if md is None:return "MISSING_DATE"
    if gd is None:return "NO_SCHEDULE"
    if md<gd:return "STRICT_PRIOR_DAY"
    if md==gd:return "SAME_GAMEDAY"
    return "AFTER_GAMEDAY"


def load_schedule(path:Path,years:set[int]):
    out={}
    with path.open(newline="",encoding="utf-8-sig") as f:
        rd=csv.DictReader(f)
        for r in rd:
            season=asint(r.get("season"));week=asint(r.get("week"))
            if season not in years or str(r.get("game_type") or "").strip().upper()!="REG":continue
            gd=parse_date(r.get("gameday"))
            if not gd:continue
            for team in (normteam(r.get("away_team")),normteam(r.get("home_team"))):
                key=(season,week,team)
                if key in out:raise ValueError(f"duplicate schedule key {key}")
                out[key]={"gameday":gd.isoformat(),"game_id":str(r.get("game_id") or "")}
    return out


def load_injury_asset(path:Path):
    import pyarrow.parquet as pq
    pf=pq.ParquetFile(path);names=set(pf.schema_arrow.names)
    core=[
        "season","team","week","gsis_id","position","full_name",
        "report_primary_injury","report_secondary_injury","report_status",
        "practice_primary_injury","practice_secondary_injury","practice_status",
        "date_modified",
    ]
    miss=[x for x in core if x not in names]
    if miss:raise ValueError(f"{path.name} missing {miss}")
    type_field="season_type" if "season_type" in names else ("game_type" if "game_type" in names else None)
    cols=core+([type_field] if type_field else [])
    return type_field,pf.read(columns=cols).to_pylist()


def state_from_injury(r):
    if r is None:return "NOT_LISTED"
    report=str(r.get("report_status") or "").strip().upper()
    practice=str(r.get("practice_status") or "").strip().upper()
    if report=="OUT":return "OUT"
    if report=="DOUBTFUL":return "DOUBTFUL"
    if report=="QUESTIONABLE":return "QUESTIONABLE"
    if "DID NOT PARTICIPATE" in practice:return "PRACTICE_DNP"
    if "LIMITED PARTICIPATION" in practice:return "PRACTICE_LIMITED"
    if "FULL PARTICIPATION" in practice:return "PRACTICE_FULL"
    return "REPORT_BLANK"


SEVERITY={
    "NOT_LISTED":0,
    "REPORT_BLANK":1,
    "PRACTICE_FULL":2,
    "PRACTICE_LIMITED":3,
    "PRACTICE_DNP":4,
    "QUESTIONABLE":5,
    "DOUBTFUL":6,
    "OUT":7,
}


def state_group(state):
    if state in {"OUT","DOUBTFUL","QUESTIONABLE"}:return "GAME_STATUS"
    if state in {"PRACTICE_DNP","PRACTICE_LIMITED"}:return "PRACTICE_RESTRICTED"
    if state=="PRACTICE_FULL":return "PRACTICE_FULL"
    if state=="REPORT_BLANK":return "REPORT_BLANK"
    return "NOT_LISTED"


def metrics(rows,actual,pred):
    if not rows:return {"n":0}
    e=[num(r.get(pred))-num(r.get(actual)) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(x) for x in e),"rmse":sqrt(fmean(x*x for x in e)),
            "biasPredMinusActual":fmean(e)}


def summarize(rows):
    if not rows:return {"n":0}
    resid=[num(r.get("snap_residual_actual_minus_pred")) for r in rows]
    pos=sum(x>0 for x in resid)/len(resid)
    neg=sum(x<0 for x in resid)/len(resid)
    return {
        "n":len(rows),
        "snap":metrics(rows,"actual_snap_share","predicted_snap_share"),
        "meanResidualActualMinusPred":fmean(resid),
        "positiveResidualRate":pos,"negativeResidualRate":neg,
        "meanAbsResidual":fmean(abs(x) for x in resid),
    }


def grouped(rows,key):
    g=defaultdict(list)
    for r in rows:g[str(r.get(key) or "UNKNOWN")].append(r)
    return {k:summarize(v) for k,v in sorted(g.items())}


def directional_material(pooled,yearly,min_n=60,min_abs=.05,min_rate=.65,min_years=3):
    if pooled.get("n",0)<min_n:return False
    mean=num(pooled.get("meanResidualActualMinusPred"))
    if abs(mean)<min_abs:return False
    want=1 if mean>0 else -1
    rate=pooled.get("positiveResidualRate",0) if want>0 else pooled.get("negativeResidualRate",0)
    if rate<min_rate:return False
    consistent=0
    for y,z in yearly.items():
        if z.get("n",0)<=0:continue
        ym=num(z.get("meanResidualActualMinusPred"))
        if (ym>0 and want>0) or (ym<0 and want<0):consistent+=1
    return consistent>=min_years


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--data-root",default="")
    ap.add_argument("--evaluation-seasons",default="2021,2022,2023,2024")
    a=ap.parse_args();root=Path(a.root).expanduser().resolve()
    data_root=Path(a.data_root).expanduser().resolve() if a.data_root else root
    years=[int(x) for x in a.evaluation_seasons.split(",") if x.strip()]
    if years!=sorted(years) or len(years)<3 or min(years)<2019 or max(years)>=2025:
        raise ValueError("evaluation seasons must be chronological development years <2025")

    sys.path[:0]=[str(root/"packages/models/nfl/omega"),str(root/"scripts/nfl")]
    import frozen_spec as fs
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import lb_edge_archetype_0363 as arch
    import analyze_omega_position_specific_challenger_0360 as base

    iptr=data_root/"data/raw/nfl/omega/CURRENT_INJURY_SOURCE_AUDIT"
    fptr=data_root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not iptr.exists():raise FileNotFoundError(iptr)
    if not fptr.exists():raise FileNotFoundError(fptr)
    iaid=iptr.read_text().strip();idir=data_root/"data/raw/nfl/omega/injury_source_audits"/iaid
    iaudit=json.loads((idir/"OMEGA_0.43.0_INJURY_SOURCE_TIMING_AUDIT.json").read_text())
    if iaudit.get("conclusion")!="STRICT_PRIOR_DAY_INJURY_SOURCE_CANDIDATE":
        raise ValueError("0.43 source audit has not cleared strict-prior-day gate")
    if iaudit.get("sealed2025RowsRead")!=0 or iaudit.get("prospective2026RowsRead")!=0:
        raise ValueError("injury source audit seal violation")

    schedule=load_schedule(idir/"games.csv",set(years))
    injury={}
    timing_counts=Counter()
    duplicate_keys=0
    for year in years:
        p=idir/f"injuries_{year}.parquet"
        type_field,rows=load_injury_asset(p)
        for r in rows:
            season=asint(r.get("season"));week=asint(r.get("week"))
            if season!=year:continue
            if type_field and str(r.get(type_field) or "").strip().upper()!="REG":continue
            team=normteam(r.get("team"));pid=str(r.get("gsis_id") or "").strip()
            sched=schedule.get((season,week,team))
            tc=timing_class(r.get("date_modified"),sched.get("gameday") if sched else None)
            timing_counts[tc]+=1
            if tc!="STRICT_PRIOR_DAY" or not pid:continue
            key=(season,week,team,pid)
            if key in injury:
                duplicate_keys+=1
                # Fail closed: source audit said duplicates were tiny. Keep latest
                # strictly-prior calendar date only; equal-date duplicates are not
                # silently reconciled.
                old=injury[key]
                od=parse_date(old.get("date_modified"));nd=parse_date(r.get("date_modified"))
                if nd and od and nd>od:
                    injury[key]=r
                elif nd==od:
                    fields=("report_status","practice_status","report_primary_injury","report_secondary_injury",
                            "practice_primary_injury","practice_secondary_injury")
                    if any(str(old.get(x) or "").strip().upper()!=str(r.get(x) or "").strip().upper() for x in fields):
                        raise ValueError(f"conflicting equal-date injury duplicate {key}")
                    # Exact semantic duplicate: retain the first immutable row.
                else:
                    # Older duplicate carries no new pregame information.
                    pass
            else:injury[key]=r

    sid=fptr.read_text().strip()
    foundation=data_root/"data/normalized/nfl/omega_tackle"/sid
    exdir=data_root/"data/normalized/nfl/omega_tackle_exposure"/sid
    histp=rcsv(foundation/"omega_tackle_play_opportunities.csv")
    histe=rcsv(foundation/"omega_tackle_credit_events.csv")
    histex=rcsv(exdir/"omega_tackle_exposure_player_games.csv")
    if any(int(num(r.get("season")))>=2025 for r in histp+histe+histex):
        raise ValueError("sealed/prospective row entered 0.43.1 audit")

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
        rooms=defaultdict(list)
        for r in clean:rooms[(str(r.get("game_id") or ""),str(r.get("team") or ""))].append(r)
        rows=[]
        for r in clean:
            season=int(r["season"]);week=int(r["week"]);team=normteam(r.get("team"));pid=str(r.get("player_id") or "")
            ir=injury.get((season,week,team,pid))
            state=state_from_injury(ir)
            z=dict(r)
            z["injury_state"]=state;z["injury_state_group"]=state_group(state)
            z["injury_severity"]=SEVERITY[state]
            z["injury_listed"]=1 if ir is not None else 0
            z["snap_residual_actual_minus_pred"]=num(r.get("actual_snap_share"))-num(r.get("predicted_snap_share"))

            room=rooms[(str(r.get("game_id") or ""),str(r.get("team") or ""))]
            teammate_states=[]
            for q in room:
                qpid=str(q.get("player_id") or "")
                if qpid==pid:continue
                qr=injury.get((season,week,team,qpid))
                teammate_states.append(state_from_injury(qr))
            z["teammate_reported_count"]=sum(s!="NOT_LISTED" for s in teammate_states)
            z["teammate_game_status_count"]=sum(s in {"OUT","DOUBTFUL","QUESTIONABLE"} for s in teammate_states)
            z["teammate_restricted_count"]=sum(s in {"OUT","DOUBTFUL","QUESTIONABLE","PRACTICE_DNP","PRACTICE_LIMITED"} for s in teammate_states)
            z["teammate_max_severity"]=max([SEVERITY[s] for s in teammate_states] or [0])
            z["teammate_game_status_any"]="YES" if z["teammate_game_status_count"]>0 else "NO"
            z["teammate_restricted_any"]="YES" if z["teammate_restricted_count"]>0 else "NO"
            rows.append(z)
        by_year[year]=rows;pooled.extend(rows)
        listed=sum(r["injury_listed"] for r in rows)
        print(f"PASS {year} · LB {len(rows):,} · strict-prior injury listed {listed:,} ({listed/len(rows):.1%}) · "
              f"mean residual {fmean(num(r['snap_residual_actual_minus_pred']) for r in rows):+.4f}")

    dimensions={
        "ownInjuryState":"injury_state",
        "ownInjuryGroup":"injury_state_group",
        "teammateGameStatusAny":"teammate_game_status_any",
        "teammateRestrictedAny":"teammate_restricted_any",
    }
    pooled_groups={name:grouped(pooled,key) for name,key in dimensions.items()}
    yearly_groups={y:{name:grouped(rows,key) for name,key in dimensions.items()} for y,rows in by_year.items()}

    candidates=[]
    for dim,pgr in pooled_groups.items():
        for label,pz in pgr.items():
            yz={str(y):yearly_groups[y][dim].get(label,{"n":0}) for y in years}
            if directional_material(pz,yz):
                candidates.append({"dimension":dim,"slice":label,"pooled":pz,"byYear":yz,
                                   "absMeanResidual":abs(num(pz.get("meanResidualActualMinusPred")))})
    candidates.sort(key=lambda x:(-x["absMeanResidual"],-x["pooled"]["n"],x["dimension"],x["slice"]))

    # Explicitly report the football-interest states even when sample sizes are
    # below the material gate, because rare OUT/DOUBTFUL rows should not disappear.
    interest=["OUT","DOUBTFUL","QUESTIONABLE","PRACTICE_DNP","PRACTICE_LIMITED","PRACTICE_FULL","NOT_LISTED"]
    own_interest={s:pooled_groups["ownInjuryState"].get(s,{"n":0}) for s in interest}

    conclusion="STRICT_PRIOR_INJURY_SIGNAL_MATERIAL" if candidates else "STRICT_PRIOR_INJURY_SIGNAL_WEAK"
    next_gate="BUILD_0.44_INJURY_AWARE_LB_EXPOSURE_CHALLENGER" if candidates else "DO_NOT_ADD_INJURY_TO_H012_WITHOUT_NEW_EVIDENCE"

    report={
        "schemaVersion":"OMEGA_OFFBALL_LB_STRICT_PRIOR_INJURY_SIGNAL_AUDIT_0.43.1",
        "createdAt":datetime.now(timezone.utc).isoformat(),"sourceSnapshotId":sid,
        "injurySourceAuditId":iaid,"codeRoot":str(root),"dataRoot":str(data_root),
        "evaluationSeasons":years,"sealedHoldoutSeason":2025,"prospectiveSeason":2026,
        "holdoutOpened":False,"prospectiveRowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,
        "strictPriorInjuryRows":len(injury),"injuryTimingCounts":dict(timing_counts),
        "duplicateStrictPriorKeysResolvedByLaterPriorDate":duplicate_keys,
        "rows":len(pooled),"overall":summarize(pooled),"ownInterestStates":own_interest,
        "dimensions":pooled_groups,"yearlyDimensions":yearly_groups,
        "materialCandidates":candidates,
        "decisionRule":"n>=60; |mean actual-pred|>=0.05; matching residual direction >=65%; same direction in >=3 evaluation seasons",
        "conclusion":conclusion,"nextGate":next_gate,
        "integrity":{"diagnosticOnly":True,"modelFit":False,"sameGamedayRowsUsed":0,
                     "afterGamedayRowsUsed":0,"productionPromotion":False,"frozenOmegaMutation":False},
    }

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out=data_root/"data/models/nfl/omega_lb_injury_signal_audit_0431"/run_id;out.mkdir(parents=True,exist_ok=False)
    jp=out/"OMEGA_0.43.1_LB_INJURY_SIGNAL_AUDIT.json";jp.write_text(json.dumps(report,indent=2)+"\n")
    lines=[
        "OMEGA 0.43.1 — STRICT-PRIOR-DAY OFF-BALL LB INJURY/PRACTICE SIGNAL AUDIT","",
        f"OMEGA source: {sid}",f"Injury source audit: {iaid}",
        "2025 SEALED · 2026 NOT READ · same-day injury rows USED 0 · market fields 0 · model fit 0","",
        f"CONCLUSION: {conclusion}",f"NEXT GATE: {next_gate}","",
        f"POOLED n {len(pooled):,} · snap MAE {report['overall']['snap']['mae']:.5f} · mean actual-pred {report['overall']['meanResidualActualMinusPred']:+.5f}","",
        "OWN INJURY STATES",
    ]
    for s in interest:
        z=own_interest[s]
        if z.get("n",0):
            mean=num(z.get("meanResidualActualMinusPred"))
            rate=z["positiveResidualRate"] if mean>0 else z["negativeResidualRate"]
            lines.append(f"  {s}: n {z['n']:,} · snap MAE {z['snap']['mae']:.4f} · mean residual {mean:+.4f} · directional {rate:.1%}")
    lines += ["","MATERIAL SLICES"]
    if candidates:
        for q in candidates:
            z=q["pooled"];mean=num(z.get("meanResidualActualMinusPred"))
            rate=z["positiveResidualRate"] if mean>0 else z["negativeResidualRate"]
            lines.append(f"  {q['dimension']} / {q['slice']}: n {z['n']:,} · mean residual {mean:+.4f} · directional {rate:.1%} · MAE {z['snap']['mae']:.4f}")
    else:lines.append("  NONE")
    lines += ["","Only STRICT_PRIOR_DAY injury rows were used. SAME_GAMEDAY remained quarantined.",
              "This is a signal audit only; no injury-aware model is fit.",f"REPORT: {jp}"]
    tp=out/"OMEGA_0.43.1_LB_INJURY_SIGNAL_AUDIT.txt";tp.write_text("\n".join(lines)+"\n")
    ptr=data_root/"data/models/nfl/CURRENT_OMEGA_LB_INJURY_SIGNAL_AUDIT_0431";ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(run_id+"\n");os.replace(tmp,ptr)
    print();print(tp.read_text())
    print("PASS OMEGA 0.43.1 injury signal audit · diagnostic only · production unchanged")
    return 0

if __name__=="__main__":raise SystemExit(main())

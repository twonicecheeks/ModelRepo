#!/usr/bin/env python3
"""OMEGA 0.43.0 — nflverse historical injury/practice source timing audit.

SOURCE AUDIT ONLY. NO MODEL FIT.

Downloads immutable copies of nflverse injury/practice report parquets for
2019-2024 plus the nflverse schedule. It audits:

- required injury schema and GSIS identity coverage;
- duplicate player/team/week semantics;
- regular-season team/week schedule join coverage;
- report/practice status vocabularies;
- date_modified parse coverage;
- modification date relative to scheduled gameday.

Temporal policy for any later challenger:
- STRICT_PRIOR_DAY: eligible historical pregame evidence candidate;
- SAME_GAMEDAY: quarantined until exact timestamp/timezone provenance is verified;
- AFTER_GAMEDAY: forbidden;
- MISSING_DATE: forbidden.

The season-level nflverse injury source ends after 2024 and is explicitly NOT a
2026 production provider. This audit does not read 2025 or 2026.
"""
from __future__ import annotations

from collections import Counter,defaultdict
from datetime import datetime,timezone,date
from pathlib import Path
import argparse,csv,hashlib,json,os,shutil,subprocess,uuid

YEARS=tuple(range(2019,2025))
SEALED_YEAR=2025
PROSPECTIVE_YEAR=2026
INJURY_BASE="https://github.com/nflverse/nflverse-data/releases/download/injuries"
SCHEDULE_URL="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
CORE_REQUIRED=(
    "season","team","week","gsis_id","position","full_name",
    "report_primary_injury","report_secondary_injury","report_status",
    "practice_primary_injury","practice_secondary_injury","practice_status",
    "date_modified",
)
SEASON_TYPE_ALIASES=("season_type","game_type")

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def sha(path:Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def download(url:str,path:Path):
    curl=shutil.which("curl")
    if not curl:raise RuntimeError("system curl not found; refusing to weaken TLS verification")
    path.parent.mkdir(parents=True,exist_ok=True)
    part=path.with_name(path.name+".part");part.unlink(missing_ok=True)
    cmd=[curl,"--fail","--location","--silent","--show-error","--connect-timeout","20",
         "--max-time","180","--retry","2","--retry-delay","1",
         "--user-agent","OMEGA-MODEL/0.43 injury-source-audit","--output",str(part),url]
    r=subprocess.run(cmd,text=True,capture_output=True)
    if r.returncode!=0:
        part.unlink(missing_ok=True)
        raise RuntimeError((r.stderr or r.stdout or f"curl exit {r.returncode}").strip())
    if not part.exists() or part.stat().st_size<=0:raise RuntimeError(f"empty download: {url}")
    os.replace(part,path)

def normteam(v):
    x=str(v or "").strip().upper()
    return {"ARZ":"ARI","BLT":"BAL","CLV":"CLE","GNB":"GB","JAC":"JAX","KAN":"KC",
            "LVR":"LV","OAK":"LV","LAR":"LA","STL":"LA","SD":"LAC","NWE":"NE",
            "NOR":"NO","SFO":"SF","TAM":"TB","WSH":"WAS"}.get(x,x)

def asint(v,d=0):
    try:return int(float(v))
    except:return d

def parse_date(v):
    if v in (None,""):return None
    s=str(v).strip()
    if not s:return None
    # ISO strings from Arrow often include timezone; date portion is sufficient for
    # the conservative calendar-day quarantine used by this audit.
    try:return datetime.fromisoformat(s.replace("Z","+00:00")).date()
    except Exception:
        try:return date.fromisoformat(s[:10])
        except Exception:return None

def load_schedule(path:Path,years:set[int]):
    out={};dups=0
    with path.open(newline="",encoding="utf-8-sig") as f:
        rd=csv.DictReader(f)
        need={"game_id","season","week","game_type","gameday","away_team","home_team"}
        miss=need-set(rd.fieldnames or [])
        if miss:raise ValueError("schedule missing: "+",".join(sorted(miss)))
        for r in rd:
            season=asint(r.get("season"));week=asint(r.get("week"))
            if season not in years or str(r.get("game_type") or "").strip().upper()!="REG":continue
            gd=parse_date(r.get("gameday"))
            if not gd:continue
            for team in (normteam(r.get("away_team")),normteam(r.get("home_team"))):
                key=(season,week,team)
                if key in out:dups+=1
                out[key]={"game_id":str(r.get("game_id") or ""),"gameday":gd.isoformat(),
                          "gametime":str(r.get("gametime") or ""),"team":team}
    if dups:raise ValueError(f"duplicate regular team-week schedule keys: {dups}")
    return out

def parquet_rows(path:Path):
    import pyarrow.parquet as pq
    pf=pq.ParquetFile(path);names=list(pf.schema_arrow.names)
    miss=[c for c in CORE_REQUIRED if c not in names]
    if miss:raise ValueError(f"{path.name} missing required injury columns: {miss}")
    type_field=next((x for x in SEASON_TYPE_ALIASES if x in names),None)
    cols=list(CORE_REQUIRED)+([type_field] if type_field else [])
    rows=pf.read(columns=cols).to_pylist()
    return names,type_field,rows

def timing_class(modified,gameday):
    md=parse_date(modified);gd=parse_date(gameday)
    if md is None:return "MISSING_DATE"
    if gd is None:return "NO_SCHEDULE"
    if md<gd:return "STRICT_PRIOR_DAY"
    if md==gd:return "SAME_GAMEDAY"
    return "AFTER_GAMEDAY"

def summarize_year(year,rows,schedule,type_field):
    schedule_weeks=[k[1] for k in schedule if k[0]==year]
    max_reg_week=max(schedule_weeks) if schedule_weeks else 0
    if type_field:
        reg=[r for r in rows if str(r.get(type_field) or "").strip().upper()=="REG"]
        season_type_policy=f"EXPLICIT_{type_field.upper()}"
    else:
        # Conservative legacy fallback: keep only rows whose week falls inside the
        # regular-season schedule window. Team-week schedule coverage is still audited
        # below, so malformed/unjoinable regular-window rows remain visible as failures.
        reg=[r for r in rows if 1<=asint(r.get("week"))<=max_reg_week]
        season_type_policy="INFERRED_FROM_REGULAR_SCHEDULE_WEEK_WINDOW"
    keys=Counter()
    report=Counter();practice=Counter();timing=Counter();weeks=Counter()
    gsis=0;joined=0;parsed=0
    after_examples=[];same_examples=[]
    for r in reg:
        team=normteam(r.get("team"));week=asint(r.get("week"));pid=str(r.get("gsis_id") or "").strip()
        if pid:gsis+=1
        keys[(year,week,team,pid)]+=1
        report[str(r.get("report_status") or "").strip().upper() or "BLANK"]+=1
        practice[str(r.get("practice_status") or "").strip().upper() or "BLANK"]+=1
        weeks[week]+=1
        s=schedule.get((year,week,team))
        if s:joined+=1
        tc=timing_class(r.get("date_modified"),s.get("gameday") if s else None);timing[tc]+=1
        if parse_date(r.get("date_modified")) is not None:parsed+=1
        ex={"week":week,"team":team,"gsis_id":pid,"full_name":str(r.get("full_name") or ""),
            "date_modified":str(r.get("date_modified") or ""),"gameday":s.get("gameday") if s else None,
            "report_status":str(r.get("report_status") or ""),"practice_status":str(r.get("practice_status") or "")}
        if tc=="AFTER_GAMEDAY" and len(after_examples)<8:after_examples.append(ex)
        if tc=="SAME_GAMEDAY" and len(same_examples)<8:same_examples.append(ex)
    duplicate_rows=sum(n-1 for n in keys.values() if n>1)
    duplicated_keys=sum(1 for n in keys.values() if n>1)
    n=len(reg)
    dated=sum(timing[x] for x in ("STRICT_PRIOR_DAY","SAME_GAMEDAY","AFTER_GAMEDAY"))
    return {
        "year":year,"rows":n,"seasonTypeField":type_field,"seasonTypePolicy":season_type_policy,
        "regularSeasonMaxWeek":max_reg_week,"uniquePlayerTeamWeekKeys":len(keys),
        "duplicateExtraRows":duplicate_rows,"duplicatedKeys":duplicated_keys,
        "duplicateExtraRowRate":duplicate_rows/n if n else None,
        "gsisIdCoverage":gsis/n if n else None,
        "scheduleJoinCoverage":joined/n if n else None,
        "dateParseCoverage":parsed/n if n else None,
        "timingCounts":dict(timing),
        "strictPriorDayRateAmongDated":timing["STRICT_PRIOR_DAY"]/dated if dated else None,
        "sameGamedayRateAmongDated":timing["SAME_GAMEDAY"]/dated if dated else None,
        "afterGamedayRateAmongDated":timing["AFTER_GAMEDAY"]/dated if dated else None,
        "reportStatusCounts":dict(report),"practiceStatusCounts":dict(practice),
        "weekCounts":dict(sorted(weeks.items())),
        "afterGamedayExamples":after_examples,"sameGamedayExamples":same_examples,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--years",default=",".join(map(str,YEARS)))
    a=ap.parse_args();root=Path(a.root).expanduser().resolve()
    years=tuple(sorted({int(x) for x in a.years.split(",") if x.strip()}))
    if not years:raise ValueError("no years")
    if any(y>=SEALED_YEAR for y in years):raise ValueError("0.43 source audit refuses 2025+")
    if min(years)<2009:raise ValueError("nflverse injury source begins 2009")

    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base=root/"data/raw/nfl/omega/injury_source_audits"
    staging=base/("."+stamp+".staging");staging.mkdir(parents=True,exist_ok=False)
    try:
        sp=staging/"games.csv"
        print(f"FETCH schedule: {SCHEDULE_URL}");download(SCHEDULE_URL,sp)
        schedule=load_schedule(sp,set(years))
        assets=[{"source":"schedules","filename":sp.name,"url":SCHEDULE_URL,"sha256":sha(sp),"bytes":sp.stat().st_size}]
        summaries=[]
        for year in years:
            name=f"injuries_{year}.parquet";url=f"{INJURY_BASE}/{name}";p=staging/name
            print(f"FETCH injury {year}: {url}");download(url,p)
            names,type_field,rows=parquet_rows(p)
            summary=summarize_year(year,rows,schedule,type_field);summary["columns"]=names
            summaries.append(summary)
            assets.append({"source":"injuries","year":year,"filename":name,"url":url,
                           "sha256":sha(p),"bytes":p.stat().st_size,"rows":len(rows)})

        target=[s for s in summaries if s["year"] in {2021,2022,2023,2024}]
        required_schema=all(all(c in s["columns"] for c in CORE_REQUIRED) for s in target)
        gsis_ok=all((s["gsisIdCoverage"] or 0)>=.98 for s in target)
        join_ok=all((s["scheduleJoinCoverage"] or 0)>=.98 for s in target)
        parse_ok=all((s["dateParseCoverage"] or 0)>=.98 for s in target)
        after_ok=all((s["afterGamedayRateAmongDated"] or 0)<=.01 for s in target)
        dup_ok=all((s["duplicateExtraRowRate"] or 0)<=.02 for s in target)
        source_candidate=required_schema and gsis_ok and join_ok and parse_ok and after_ok and dup_ok
        conclusion="STRICT_PRIOR_DAY_INJURY_SOURCE_CANDIDATE" if source_candidate else "INJURY_SOURCE_TIMING_OR_SCHEMA_UNRESOLVED"
        next_gate="BUILD_0.43_STRICT_PRIOR_DAY_LB_INJURY_SIGNAL_AUDIT" if source_candidate else "INSPECT_0.43_SOURCE_FAILURES_BEFORE_MODELING"

        audit={
            "schemaVersion":"OMEGA_INJURY_SOURCE_TIMING_AUDIT_0.43.0","createdAt":now(),
            "yearsRead":list(years),"sealed2025RowsRead":0,"prospective2026RowsRead":0,
            "marketFieldsRead":0,"oddsPapiRequests":0,
            "source":{"provider":"nflverse","injuryAvailability":"2009-2024; source dead after 2024",
                      "production2026Provider":False},
            "assets":assets,"summaries":summaries,
            "temporalPolicy":{"STRICT_PRIOR_DAY":"eligible candidate for later historical pregame features",
                              "SAME_GAMEDAY":"QUARANTINED","AFTER_GAMEDAY":"FORBIDDEN",
                              "MISSING_DATE":"FORBIDDEN"},
            "gateChecks":{"requiredSchema":required_schema,"gsisCoverageAtLeast98Pct":gsis_ok,
                          "scheduleJoinAtLeast98Pct":join_ok,"dateParseAtLeast98Pct":parse_ok,
                          "afterGamedayAtMost1Pct":after_ok,"duplicateExtraRowsAtMost2Pct":dup_ok},
            "conclusion":conclusion,"nextGate":next_gate,
            "integrity":{"modelFit":False,"productionPromotion":False,"frozenOmegaMutation":False},
        }
        seed=json.dumps(assets,sort_keys=True,separators=(",",":")).encode()
        sid=f"{stamp}_{hashlib.sha256(seed).hexdigest()[:8]}"
        final=base/sid
        (staging/"OMEGA_0.43.0_INJURY_SOURCE_TIMING_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n")
        lines=["OMEGA 0.43.0 — NFLVERSE INJURY/PRACTICE SOURCE TIMING AUDIT","",
               "2025 READ 0 · 2026 READ 0 · market fields 0 · model fit 0","",
               f"CONCLUSION: {conclusion}",f"NEXT GATE: {next_gate}",""]
        for s in summaries:
            lines += [
                f"{s['year']} · rows {s['rows']:,} · type {s['seasonTypePolicy']} · GSIS {s['gsisIdCoverage']:.1%} · schedule join {s['scheduleJoinCoverage']:.1%} · "
                f"date parse {s['dateParseCoverage']:.1%} · duplicate-extra {s['duplicateExtraRowRate']:.2%}",
                f"  timing: prior {s['strictPriorDayRateAmongDated']:.1%} · same-day {s['sameGamedayRateAmongDated']:.1%} · after {s['afterGamedayRateAmongDated']:.1%}",
                f"  report statuses: {json.dumps(s['reportStatusCounts'],sort_keys=True)}",
                f"  practice statuses: {json.dumps(s['practiceStatusCounts'],sort_keys=True)}",
            ]
        lines += ["","GATES",*(f"  {k}: {'PASS' if v else 'FAIL'}" for k,v in audit["gateChecks"].items()),
                  "","Same-gameday rows remain quarantined regardless of the overall source verdict.",
                  "This source is historical research only; it cannot supply 2026 production injuries.",
                  f"REPORT: {final/'OMEGA_0.43.0_INJURY_SOURCE_TIMING_AUDIT.json'}"]
        (staging/"OMEGA_0.43.0_INJURY_SOURCE_TIMING_AUDIT.txt").write_text("\n".join(lines)+"\n")
        os.replace(staging,final)
        ptr=root/"data/raw/nfl/omega/CURRENT_INJURY_SOURCE_AUDIT"
        ptr.parent.mkdir(parents=True,exist_ok=True);tmp=ptr.with_name("."+ptr.name+".tmp")
        tmp.write_text(sid+"\n");os.replace(tmp,ptr)
        print();print((final/"OMEGA_0.43.0_INJURY_SOURCE_TIMING_AUDIT.txt").read_text())
        print("PASS OMEGA 0.43 injury source audit · diagnostic only")
        return 0
    except Exception:
        shutil.rmtree(staging,ignore_errors=True);raise

if __name__=="__main__":raise SystemExit(main())

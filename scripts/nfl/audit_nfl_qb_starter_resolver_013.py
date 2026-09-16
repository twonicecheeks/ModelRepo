#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import json
import os
import sys
import uuid

try:
    import pyarrow.parquet as pq
except Exception as exc:
    raise SystemExit(f"pyarrow required; run scripts/nfl/bootstrap_phase1_python.command: {exc}")


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def load_jsonl(path: Path) -> list[dict]:
    out=[]
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if line:
                out.append(json.loads(line))
    return out


def bool1(v) -> bool:
    try:
        return float(v) == 1.0
    except Exception:
        return False


def pct(n: int, d: int) -> float | None:
    return None if not d else 100.0 * n / d


def asset_index(manifest: dict) -> dict[tuple[str,int|None],dict]:
    return {(a["source"], a.get("season")): a for a in manifest.get("assets", [])}


def summarize_variant(rows: list[dict], variant: str, resolver) -> dict:
    eligible=[r for r in rows if resolver.eligible_for_variant(r["resolution"], variant)]
    first=sum(r["resolution"].qb_gsis_id == r["first_qb"] for r in eligible)
    primary=sum(r["resolution"].qb_gsis_id == r["primary_qb"] for r in eligible)
    n=len(rows); m=len(eligible)
    return {
        "variant": variant,
        "teamGames": n,
        "resolved": m,
        "coveragePct": pct(m,n),
        "firstQbMatches": first,
        "firstQbAccuracyPct": pct(first,m),
        "primaryQbMatches": primary,
        "primaryQbAccuracyPct": pct(primary,m),
        "gate": resolver.gate(coverage_pct=pct(m,n) or 0.0, first_qb_accuracy_pct=pct(first,m) or 0.0),
    }


def main() -> int:
    ap=argparse.ArgumentParser(description="QB State 0.1.3 conservative historical starter resolver audit")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args=ap.parse_args()

    root=Path(args.root).expanduser().resolve()
    model_dir=root/"packages/models/nfl/game"
    provider_dir=root/"packages/providers/nflverse/src"
    sys.path.insert(0,str(model_dir)); sys.path.insert(0,str(provider_dir))
    import qb_starter_resolver_013 as resolver
    import contract

    seasons=resolver.assert_development_only(parse_seasons(args.seasons))
    season_set=set(seasons)

    raw_ptr=root/"data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    if not raw_ptr.exists(): raise FileNotFoundError("CURRENT_RAW_SNAPSHOT missing")
    sid=raw_ptr.read_text(encoding="utf-8").strip()
    manifest_path=root/"data/raw/nfl/nflverse/snapshots"/sid/"SOURCE_MANIFEST.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    assets=asset_index(manifest)

    phase1_sid=(root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT").read_text(encoding="utf-8").strip()
    if phase1_sid != sid:
        raise ValueError(f"Phase1/raw snapshot mismatch: {phase1_sid} != {sid}")
    phase1=root/"data/normalized/nfl/phase1"/sid

    # REG game universe.
    reg_games=set()
    with (phase1/"game_identity.csv").open("r",encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            if int(r.get("season") or 0) in season_set and str(r.get("game_type") or "").upper()=="REG":
                reg_games.add(str(r["game_id"]))

    # Target-week roster ACT proxy. This is explicitly not an official game-day inactive source.
    active_by=defaultdict(set)
    with (phase1/"qb_roster_weekly.csv").open("r",encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            season=int(r.get("season") or 0)
            if season not in season_set: continue
            if str(r.get("game_type") or "").upper() not in {"","REG"}: continue
            if str(r.get("status") or "").upper() != "ACT": continue
            qid=str(r.get("gsis_id") or "").strip()
            team=str(r.get("team") or "").strip().upper()
            week=int(r.get("week") or 0)
            if qid and team and week:
                active_by[(season,week,team)].add(qid)

    # Legacy target-week depth QB1 proxy.
    depth_ptr=root/"data/normalized/nfl/CURRENT_NFL_QB_DEPTH_CHARTS"
    if not depth_ptr.exists(): raise FileNotFoundError("CURRENT_NFL_QB_DEPTH_CHARTS missing")
    depth_dir=root/depth_ptr.read_text(encoding="utf-8").strip()
    depth_audit=json.loads((depth_dir/"NFL_QB_DEPTH_CHART_AUDIT.json").read_text(encoding="utf-8"))
    if depth_audit.get("holdoutOpened") is not False:
        raise ValueError("depth-chart holdout boundary drift")
    depth_by=defaultdict(list)
    for r in load_jsonl(depth_dir/"NFL_QB_DEPTH_CHARTS.jsonl"):
        season=int(r.get("season") or 0)
        if season not in season_set: continue
        if str(r.get("game_type") or "").upper() not in {"","REG"}: continue
        depth_by[(season,int(r.get("week") or 0),str(r.get("team") or "").upper())].append(r)

    # Retrospective observed labels. Same-game PBP is label-only, never resolver input.
    observed=[]
    for season in seasons:
        asset=assets.get(("play_by_play",season))
        if not asset: raise ValueError(f"raw snapshot missing play_by_play {season}")
        p=root/asset["blobPath"]
        pf=pq.ParquetFile(p)
        names=set(pf.schema_arrow.names)
        required={"game_id","season","week","posteam","qb_dropback","passer_player_id"}
        if not required.issubset(names):
            raise ValueError(f"{p.name} missing starter labels: {sorted(required-names)}")
        cols=list(required)
        for c in ("no_play","qb_kneel","play_type","play_id"):
            if c in names: cols.append(c)
        rows=pf.read(columns=cols).to_pylist()
        grouped=defaultdict(list)
        for idx,r in enumerate(rows):
            gid=str(r.get("game_id") or "")
            if gid not in reg_games or not bool1(r.get("qb_dropback")): continue
            pt=str(r.get("play_type") or "").lower()
            if bool1(r.get("no_play")) or pt=="no_play": continue
            if bool1(r.get("qb_kneel")) or pt=="qb_kneel": continue
            qid=str(r.get("passer_player_id") or "").strip()
            team_raw=str(r.get("posteam") or "").strip().upper()
            if not qid or not team_raw: continue
            team=contract.normalize_team_abbr(team_raw)
            order=float(r.get("play_id") or idx)
            grouped[(gid,team,int(r["season"]),int(r["week"]))].append((order,qid))
        for (gid,team,ss,wk),vals in grouped.items():
            vals.sort(key=lambda x:x[0])
            counts=Counter(q for _,q in vals)
            primary=sorted(counts.items(),key=lambda kv:(-kv[1],kv[0]))[0][0]
            observed.append({
                "game_id":gid,"team":team,"season":ss,"week":wk,
                "first_qb":vals[0][1],"primary_qb":primary,"dropbacks":len(vals),
            })
        print(f"PASS observed labels {season} · team-games {sum(1 for x in observed if x['season']==season):,}")

    observed.sort(key=lambda r:(r["season"],r["week"],r["game_id"],r["team"]))

    # Sequentially resolve before admitting the target game's observed primary into history.
    last_primary={}
    rows=[]
    for o in observed:
        key=(o["season"],o["week"],o["team"])
        drows=depth_by.get(key,[])
        qb1_ids=sorted({str(r.get("gsis_id") or "").strip() for r in drows if int(r.get("depth_rank") or 0)==1 and str(r.get("gsis_id") or "").strip()})
        depth_qb1=qb1_ids[0] if len(qb1_ids)==1 else ""
        active=sorted(active_by.get(key,set()))
        prior=last_primary.get(o["team"],"")
        res=resolver.resolve_starter(prior_primary_qb=prior, depth_qb1=depth_qb1, active_qbs=active)
        rows.append({
            **o,
            "prior_primary_qb": prior,
            "depth_qb1": depth_qb1,
            "depth_qb1_count": len(qb1_ids),
            "active_qbs": active,
            "resolution": res,
        })
        last_primary[o["team"]]=o["primary_qb"]

    # Raw depth baseline from 0.1.2, recomputed on this exact row universe.
    depth_eligible=[r for r in rows if r["depth_qb1"]]
    depth_first=sum(r["depth_qb1"]==r["first_qb"] for r in depth_eligible)
    depth_primary=sum(r["depth_qb1"]==r["primary_qb"] for r in depth_eligible)
    depth_baseline={
        "resolved":len(depth_eligible),
        "coveragePct":pct(len(depth_eligible),len(rows)),
        "firstQbAccuracyPct":pct(depth_first,len(depth_eligible)),
        "primaryQbAccuracyPct":pct(depth_primary,len(depth_eligible)),
    }

    variants={v:summarize_variant(rows,v,resolver) for v in ("STRICT","EXTENDED","ALL_RESOLVED")}

    rule_rows=defaultdict(list)
    for r in rows:
        rule_rows[r["resolution"].rule].append(r)
    by_rule={}
    for rule,rr in sorted(rule_rows.items()):
        resolved=[x for x in rr if x["resolution"].resolved]
        first=sum(x["resolution"].qb_gsis_id==x["first_qb"] for x in resolved)
        primary=sum(x["resolution"].qb_gsis_id==x["primary_qb"] for x in resolved)
        by_rule[rule]={
            "teamGames":len(rr),"resolved":len(resolved),
            "firstQbAccuracyPct":pct(first,len(resolved)),
            "primaryQbAccuracyPct":pct(primary,len(resolved)),
        }

    by_season={}
    for season in seasons:
        sr=[r for r in rows if r["season"]==season]
        by_season[str(season)]={v:summarize_variant(sr,v,resolver) for v in ("STRICT","EXTENDED")}

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out_dir=root/"data/models/nfl/qb_state_013"/run_id
    out_dir.mkdir(parents=True,exist_ok=False)
    report={
        "version":resolver.VERSION,
        "lineage":resolver.LINEAGE,
        "runId":run_id,
        "createdAt":datetime.now(timezone.utc).isoformat(),
        "sourcePbpSnapshotId":sid,
        "sourceDepthDirectory":str(depth_dir.relative_to(root)),
        "developmentSeasons":list(seasons),
        "sealedHoldoutSeason":2025,
        "holdoutOpened":False,
        "marketDependency":False,
        "oddsPapiRequests":0,
        "frozenOmegaMutation":False,
        "modelFitPerformed":False,
        "resolverInputs":"target-week legacy depth QB1 proxy + target-week weekly-roster ACT proxy + strictly lagged observed primary QB",
        "validationLabel":"current-game first attributed eligible dropback QB; current-game PBP never enters resolver inputs",
        "legacyTimingCaveat":"pre-2025 depth data is week-level and lacks exact publication timestamps",
        "weeklyRosterCaveat":"ACT is a roster-membership proxy, not an authoritative game-day inactive designation",
        "teamGames":len(rows),
        "depthBaseline":depth_baseline,
        "variants":variants,
        "byRule":by_rule,
        "bySeason":by_season,
    }
    jp=out_dir/"NFL_QB_STARTER_RESOLVER_AUDIT.json"
    jp.write_text(json.dumps(report,indent=2,default=lambda o:o.__dict__)+"\n",encoding="utf-8")

    print("\nNFL QB STATE 0.1.3 — CONSERVATIVE HISTORICAL STARTER RESOLVER AUDIT")
    print(f"Source PBP snapshot: {sid}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print(f"Observed team-games: {len(rows):,}")
    print("\nRAW DEPTH QB1 BASELINE")
    print(f"  coverage {depth_baseline['coveragePct']:.2f}% · first-QB accuracy {depth_baseline['firstQbAccuracyPct']:.2f}% · primary accuracy {depth_baseline['primaryQbAccuracyPct']:.2f}%")
    print("\nRESOLVER VARIANTS")
    for v in ("STRICT","EXTENDED","ALL_RESOLVED"):
        x=variants[v]
        print(f"  {v}: coverage {x['coveragePct']:.2f}% ({x['resolved']:,}/{x['teamGames']:,}) · first-QB accuracy {x['firstQbAccuracyPct']:.2f}% · primary {x['primaryQbAccuracyPct']:.2f}% · gate {x['gate']}")
    print("\nRULE DIAGNOSTICS")
    for rule,x in by_rule.items():
        if x["resolved"]:
            print(f"  {rule}: n={x['resolved']:,} · first-QB {x['firstQbAccuracyPct']:.2f}% · primary {x['primaryQbAccuracyPct']:.2f}%")
        else:
            print(f"  {rule}: unresolved n={x['teamGames']:,}")
    print("\nSEASON STRICT / EXTENDED")
    for s in seasons:
        a=by_season[str(s)]["STRICT"]; b=by_season[str(s)]["EXTENDED"]
        print(f"  {s}: STRICT cov {a['coveragePct']:.1f}% acc {a['firstQbAccuracyPct']:.2f}% · EXTENDED cov {b['coveragePct']:.1f}% acc {b['firstQbAccuracyPct']:.2f}%")
    print("\nInterpretation guard: same-game PBP is validation label only. No current-game QB identity enters pregame resolution.")
    print("Legacy depth timing remains a historical-proxy caveat even if accuracy is high.")
    print(f"JSON: {jp}")

    ptr=root/"data/models/nfl/CURRENT_QB_STATE_013"
    tmp=ptr.with_name("."+ptr.name+".tmp")
    tmp.write_text(str(out_dir.relative_to(root))+"\n",encoding="utf-8")
    os.replace(tmp,ptr)
    print("PASS QB State 0.1.3 resolver audit · no model fit · 2025 sealed · frozen OMEGA untouched")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

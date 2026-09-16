#!/usr/bin/env python3
from __future__ import annotations
from collections import defaultdict
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
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def load_jsonl(path: Path) -> list[dict]:
    out=[]
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip(): out.append(json.loads(line))
    return out


def asset_index(manifest: dict) -> dict[tuple[str,int|None],dict]:
    return {(a["source"],a.get("season")):a for a in manifest.get("assets",[])}


def bool1(v) -> bool:
    try: return float(v)==1.0
    except Exception: return False


def main() -> int:
    ap=argparse.ArgumentParser(description="Validate legacy nflverse depth_team=1 as a historical QB1 identity proxy")
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons",default="2016-2024")
    args=ap.parse_args()
    root=Path(args.root).expanduser().resolve()
    provider=root/"packages/providers/nflverse/src"
    sys.path.insert(0,str(provider))
    import contract
    import qb_depth_chart_adapter_011 as adapter
    seasons=adapter.assert_development_only(parse_seasons(args.seasons))

    depth_ptr=root/"data/normalized/nfl/CURRENT_NFL_QB_DEPTH_CHARTS"
    if not depth_ptr.exists(): raise FileNotFoundError("CURRENT_NFL_QB_DEPTH_CHARTS missing; run build_nfl_qb_depth_snapshot_011.command")
    depth_dir=root/depth_ptr.read_text(encoding="utf-8").strip()
    depth_audit=json.loads((depth_dir/"NFL_QB_DEPTH_CHART_AUDIT.json").read_text(encoding="utf-8"))
    if depth_audit.get("holdoutOpened") is not False: raise ValueError("depth-chart holdout boundary drift")
    depth_rows=[r for r in load_jsonl(depth_dir/"NFL_QB_DEPTH_CHARTS.jsonl") if int(r.get("season") or 0) in set(seasons)]
    depth_by=defaultdict(list)
    for r in depth_rows:
        if str(r.get("game_type") or "").upper() not in {"","REG"}: continue
        depth_by[(int(r["season"]),int(r["week"]),str(r["team"]))].append(r)

    raw_ptr=root/"data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    sid=raw_ptr.read_text(encoding="utf-8").strip()
    manifest=json.loads((root/"data/raw/nfl/nflverse/snapshots"/sid/"SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    assets=asset_index(manifest)

    phase1_sid=(root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT").read_text(encoding="utf-8").strip()
    if phase1_sid != sid: raise ValueError(f"Phase1/raw snapshot mismatch: {phase1_sid} != {sid}")
    reg_games=set()
    with (root/"data/normalized/nfl/phase1"/sid/"game_identity.csv").open("r",encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            if str(r.get("game_type") or "").upper()=="REG" and int(r.get("season") or 0) in set(seasons):
                reg_games.add(str(r["game_id"]))

    observed=[]
    for season in seasons:
        p=root / assets[("play_by_play",season)]["blobPath"]
        pf=pq.ParquetFile(p)
        names=set(pf.schema_arrow.names)
        required={"game_id","season","week","posteam","qb_dropback","passer_player_id"}
        if not required.issubset(names): raise ValueError(f"{p.name} missing starter-validation PBP fields: {sorted(required-names)}")
        cols=list(required)
        for c in ("no_play","qb_kneel","play_type","play_id"):
            if c in names: cols.append(c)
        rows=pf.read(columns=cols).to_pylist()
        by=defaultdict(list)
        for idx,r in enumerate(rows):
            gid=str(r.get("game_id") or "")
            if gid not in reg_games or not bool1(r.get("qb_dropback")): continue
            play_type=str(r.get("play_type") or "").lower()
            if bool1(r.get("no_play")) or play_type=="no_play": continue
            if bool1(r.get("qb_kneel")) or play_type=="qb_kneel": continue
            qid=str(r.get("passer_player_id") or "").strip()
            team_raw=str(r.get("posteam") or "").strip().upper()
            if not qid or not team_raw: continue
            team=contract.normalize_team_abbr(team_raw)
            order=float(r.get("play_id") or idx)
            by[(gid,team,int(r["season"]),int(r["week"]))].append((order,qid))
        for (gid,team,ss,wk),vals in by.items():
            vals.sort(key=lambda x:x[0])
            first=vals[0][1]
            counts=defaultdict(int)
            for _,qid in vals: counts[qid]+=1
            primary=sorted(counts.items(),key=lambda kv:(-kv[1],kv[0]))[0][0]
            observed.append({"game_id":gid,"team":team,"season":ss,"week":wk,"first_qb":first,"primary_qb":primary,"dropbacks":len(vals)})
        print(f"PASS observed QB labels {season} · team-games {sum(1 for x in observed if x['season']==season):,}")

    results=[]
    for o in observed:
        rows=depth_by.get((o["season"],o["week"],o["team"]),[])
        qb1=[r for r in rows if int(r.get("depth_rank") or 0)==1 and str(r.get("gsis_id") or "")]
        chosen=str(qb1[0]["gsis_id"]) if len(qb1)==1 else ""
        results.append({**o,"depth_rows":len(rows),"qb1_count":len(qb1),"depth_qb1":chosen,
                        "match_first": bool(chosen and chosen==o["first_qb"]),
                        "match_primary": bool(chosen and chosen==o["primary_qb"])})

    def summarize(rows):
        n=len(rows); any_depth=sum(r["depth_rows"]>0 for r in rows); singleton=sum(r["qb1_count"]==1 for r in rows)
        first=sum(r["match_first"] for r in rows); primary=sum(r["match_primary"] for r in rows)
        return {"teamGames":n,"anyDepthRows":any_depth,"singletonQb1":singleton,
                "depthCoveragePct":100*any_depth/n if n else None,
                "singletonQb1CoveragePct":100*singleton/n if n else None,
                "firstDropbackMatchPct":100*first/singleton if singleton else None,
                "primaryDropbackMatchPct":100*primary/singleton if singleton else None,
                "multipleQb1":sum(r["qb1_count"]>1 for r in rows),"missingQb1":sum(r["qb1_count"]==0 for r in rows)}
    overall=summarize(results)
    by_season={str(s):summarize([r for r in results if r["season"]==s]) for s in seasons}
    first=overall["firstDropbackMatchPct"] or 0.0
    coverage=overall["singletonQb1CoveragePct"] or 0.0
    if coverage>=95 and first>=95:
        gate="HISTORICAL_QB1_PROXY_STRONGLY_SUPPORTED"
    elif coverage>=90 and first>=90:
        gate="HISTORICAL_QB1_PROXY_USABLE_WITH_REVIEW"
    else:
        gate="HISTORICAL_QB1_PROXY_NOT_READY"

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out_dir=root/"data/models/nfl/qb_state_012"/run_id
    out_dir.mkdir(parents=True,exist_ok=False)
    report={"version":"0.1.2","runId":run_id,"createdAt":datetime.now(timezone.utc).isoformat(),
            "sourcePbpSnapshotId":sid,"sourceDepthDirectory":str(depth_dir.relative_to(root)),
            "developmentSeasons":list(seasons),"sealedHoldoutSeason":2025,"holdoutOpened":False,
            "marketDependency":False,"oddsPapiRequests":0,"frozenOmegaMutation":False,
            "validationUseOnly":"same-game PBP is used only as a retrospective starter label; it is forbidden from pregame feature construction",
            "legacyTimingCaveat":"pre-2025 depth data is week-level and lacks exact publication timestamps",
            "overall":overall,"bySeason":by_season,"gate":gate}
    jp=out_dir/"NFL_QB_DEPTH_STARTER_SEMANTICS_AUDIT.json"
    jp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("\nNFL QB STATE 0.1.2 — LEGACY DEPTH-CHART STARTER SEMANTICS AUDIT")
    print(f"Source PBP snapshot: {sid}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print(f"Observed team-games: {overall['teamGames']:,}")
    print(f"Any depth rows: {overall['depthCoveragePct']:.2f}%")
    print(f"Exactly one GSIS QB1: {overall['singletonQb1CoveragePct']:.2f}%")
    print(f"QB1 vs first attributed dropback QB: {overall['firstDropbackMatchPct']:.2f}%")
    print(f"QB1 vs primary-dropback QB: {overall['primaryDropbackMatchPct']:.2f}%")
    print(f"Multiple QB1 rows: {overall['multipleQb1']:,} · missing QB1: {overall['missingQb1']:,}")
    print("Season diagnostics")
    for s in seasons:
        x=by_season[str(s)]
        print(f"  {s}: singleton {x['singletonQb1CoveragePct']:.2f}% · first-QB match {x['firstDropbackMatchPct']:.2f}% · primary match {x['primaryDropbackMatchPct']:.2f}%")
    print(f"Gate: {gate}")
    print("Interpretation guard: current-game PBP is validation label only, never a pregame starter source.")
    print(f"JSON: {jp}")
    ptr=root/"data/models/nfl/CURRENT_QB_STATE_012"
    tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(str(out_dir.relative_to(root))+"\n",encoding="utf-8"); os.replace(tmp,ptr)
    print("PASS QB depth semantics audit · no model fit · frozen OMEGA untouched")
    return 0

if __name__=="__main__": raise SystemExit(main())

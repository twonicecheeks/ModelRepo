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
    text=text.strip()
    if "-" in text:
        a,b=(int(x) for x in text.split("-",1))
        if a>b: raise ValueError("season range must be ascending")
        return list(range(a,b+1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def pct(n,d):
    return None if not d else 100.0*float(n)/float(d)


def mean(vals):
    xs=[float(x) for x in vals if x is not None]
    return None if not xs else sum(xs)/len(xs)


def asset_index(manifest):
    return {(str(a.get("source") or ""),a.get("season")):dict(a) for a in manifest.get("assets",[])}


def main() -> int:
    ap=argparse.ArgumentParser(description="Build NFL QB State 0.1.5 semantic-correct observed-starter targets")
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons",default="2016-2024")
    args=ap.parse_args()

    root=Path(args.root).expanduser().resolve()
    model_dir=root/"packages/models/nfl/game"
    provider_dir=root/"packages/providers/nflverse/src"
    sys.path.insert(0,str(model_dir)); sys.path.insert(0,str(provider_dir))
    import qb_target_semantics_015 as q
    import contract

    seasons=q.assert_development_only(parse_seasons(args.seasons)); season_set=set(seasons)
    raw_ptr=root/"data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    phase_ptr=root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"
    if not raw_ptr.exists() or not phase_ptr.exists(): raise FileNotFoundError("current raw/Phase1 snapshot pointer missing")
    sid=raw_ptr.read_text(encoding="utf-8").strip()
    if phase_ptr.read_text(encoding="utf-8").strip()!=sid: raise ValueError("Phase1/raw snapshot mismatch")
    manifest=json.loads((root/"data/raw/nfl/nflverse/snapshots"/sid/"SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    assets=asset_index(manifest)
    phase1=root/"data/normalized/nfl/phase1"/sid

    game_meta={}; expected_team_games=0
    with (phase1/"game_identity.csv").open("r",encoding="utf-8",newline="") as f:
        for r in csv.DictReader(f):
            season=int(r.get("season") or 0)
            if season not in season_set or str(r.get("game_type") or "").upper()!="REG": continue
            gid=str(r["game_id"])
            game_meta[gid]={"season":season,"week":int(r.get("week") or 0)}
            expected_team_games+=2

    all_targets=[]; schema_by_season={}
    for season in seasons:
        asset=assets.get(("play_by_play",season))
        if not asset: raise ValueError(f"raw snapshot missing play_by_play {season}")
        path=root/asset["blobPath"]
        pf=pq.ParquetFile(path); names=set(pf.schema_arrow.names)
        missing=[c for c in q.REQUIRED_PBP_FIELDS if c not in names]
        if missing: raise ValueError(f"{path.name} missing QB 0.1.5 fields: {', '.join(missing)}")
        cols=list(q.REQUIRED_PBP_FIELDS)+[c for c in q.OPTIONAL_PBP_FIELDS if c in names]
        rows=pf.read(columns=cols).to_pylist()
        grouped=defaultdict(list)
        for r in rows:
            gid=str(r.get("game_id") or "")
            if gid not in game_meta: continue
            team_raw=str(r.get("posteam") or "").strip().upper()
            if not team_raw: continue
            rr=dict(r); rr["posteam"]=contract.normalize_team_abbr(team_raw)
            grouped[(gid,rr["posteam"])].append(rr)
        sr=[]
        for _,grows in grouped.items():
            x=q.aggregate_team_game(grows)
            if x is not None: sr.append(x)
        sr.sort(key=lambda r:(r["week"],r["game_id"],r["team"])); all_targets.extend(sr)
        schema_by_season[str(season)]={"selectedFields":cols,"targetRows":len(sr)}
        print(f"PASS QB semantic targets {season} · team-games {len(sr):,}")

    all_targets.sort(key=lambda r:(r["season"],r["week"],r["game_id"],r["team"]))
    n=len(all_targets)
    residual_rows=sum(int(r["structural_dropback_residual"])!=0 for r in all_targets)
    other=sum(int(r["structural_dropback_other"]) for r in all_targets)
    conflict=sum(int(r["structural_dropback_conflict"]) for r in all_targets)
    max_abs=max((abs(int(r["structural_dropback_residual"])) for r in all_targets),default=0)
    sacks=sum(int(r["structural_sacks"]) for r in all_targets)
    sacks_raw_pass=sum(int(r["raw_sacks_with_pass_attempt_indicator"]) for r in all_targets)
    comps=sum(int(r["settlement_completions"]) for r in all_targets)
    dcomps=sum(int(r["decomposable_completions"]) for r in all_targets)
    exact_dcomp=sum(int(r["exact_decomp_completions"]) for r in all_targets)
    decomp_resid=sum(float(r["completion_yards_decomp_residual"]) for r in all_targets)
    starter_primary=sum(int(r["start_equals_primary"]) for r in all_targets)
    low_share=sum(r["starter_dropback_share"] is not None and float(r["starter_dropback_share"])<0.80 for r in all_targets)
    spikes=sum(int(r["settlement_spike_attempts"]) for r in all_targets)
    two_pt=sum(int(r["two_point_pass_plays_excluded"]) for r in all_targets)
    kneels=sum(int(r["settlement_kneels"]) for r in all_targets)

    structural_exact_pct=pct(n-residual_rows,n) or 0.0
    semantic_gate=(
        "SEMANTICS_READY_FOR_QB_MODELING"
        if structural_exact_pct>=99.9 and conflict==0 and (pct(sacks_raw_pass,sacks) or 0.0)>=99.0
        else "SEMANTICS_REVIEW_REQUIRED"
    )

    by_season={}
    for season in seasons:
        sr=[r for r in all_targets if int(r["season"])==season]
        by_season[str(season)]={
            "rows":len(sr),
            "structuralExactPct":pct(sum(int(r["structural_dropback_residual"])==0 for r in sr),len(sr)),
            "meanStructuralDropbacks":mean(r["starter_structural_dropbacks"] for r in sr),
            "meanSettlementAttempts":mean(r["settlement_pass_attempts"] for r in sr),
            "meanPassingYards":mean(r["passing_yards"] for r in sr),
        }

    audit={
        "version":q.VERSION,"lineage":q.LINEAGE,"createdAt":datetime.now(timezone.utc).isoformat(),
        "sourceSnapshotId":sid,"developmentSeasons":list(seasons),"sealedHoldoutSeason":2025,
        "holdoutOpened":False,"prospectiveSeason":2026,"prospectiveRead":False,
        "marketDependency":False,"oddsPapiRequests":0,"frozenOmegaMutation":False,"modelFitPerformed":False,
        "historicalTargetIdentityPolicy":"observed first attributed structural-dropback QB; retrospective label only",
        "pregameIdentityPolicy":"QB State 0.1.3 STRICT resolver or verified starter; unresolved cases quarantine",
        "sourceSemantics":"nflfastR/nflverse pass_attempt includes sacks; qb_dropback excludes spikes/kneels and includes pass plays/scrambles",
        "expectedRegularSeasonTeamGames":expected_team_games,"targetRows":n,"targetCoveragePct":pct(n,expected_team_games),
        "startEqualsPrimaryPct":pct(starter_primary,n),"starterDropbackShareBelow80Pct":pct(low_share,n),
        "structuralDropbackDecomposition":{
            "identity":"starter_structural_dropbacks = throws + sacks + scrambles; OTHER/CONFLICT are audited residual classes",
            "exactRows":n-residual_rows,"exactPct":structural_exact_pct,"residualRows":residual_rows,
            "otherDropbacks":other,"conflictDropbacks":conflict,"maxAbsoluteResidual":max_abs,
        },
        "rawPassAttemptSemantics":{"structuralSacks":sacks,"sacksAlsoFlaggedPassAttempt":sacks_raw_pass,"pct":pct(sacks_raw_pass,sacks)},
        "settlementBoundary":{"spikePassAttemptsIncluded":spikes,"twoPointPassPlaysExcluded":two_pt,"qbKneelsIncludedInRushing":kneels},
        "passingYardDecomposition":{
            "completions":comps,"decomposableCompletions":dcomps,"coveragePct":pct(dcomps,comps),
            "exactDecomposableCompletions":exact_dcomp,"exactPct":pct(exact_dcomp,dcomps),
            "aggregateResidualYards":decomp_resid,
        },
        "targetDistributions":{
            "structuralDropbacks":q.quantiles(r["starter_structural_dropbacks"] for r in all_targets),
            "structuralThrows":q.quantiles(r["structural_throw_attempts"] for r in all_targets),
            "settlementPassAttempts":q.quantiles(r["settlement_pass_attempts"] for r in all_targets),
            "settlementCompletions":q.quantiles(r["settlement_completions"] for r in all_targets),
            "passingYards":q.quantiles(r["passing_yards"] for r in all_targets),
            "sacks":q.quantiles(r["structural_sacks"] for r in all_targets),
            "scrambles":q.quantiles(r["structural_scrambles"] for r in all_targets),
            "settlementQbRushYards":q.quantiles(r["settlement_qb_rush_yards"] for r in all_targets),
        },
        "bySeason":by_season,"schemaBySeason":schema_by_season,"gate":semantic_gate,
    }

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out_dir=root/"data/normalized/nfl/qb_targets_015"/run_id
    out_dir.mkdir(parents=True,exist_ok=False)
    tp=out_dir/"NFL_QB_OBSERVED_START_TARGETS.jsonl"
    with tp.open("w",encoding="utf-8") as f:
        for row in all_targets: f.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
    apath=out_dir/"NFL_QB_TARGET_SEMANTICS_AUDIT.json"
    apath.write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    ptr=root/"data/normalized/nfl/CURRENT_NFL_QB_TARGETS_015"; ptr.parent.mkdir(parents=True,exist_ok=True)
    tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(str(out_dir.relative_to(root))+"\n",encoding="utf-8"); os.replace(tmp,ptr)

    print("\nNFL QB STATE 0.1.5 — SEMANTIC-CORRECT TARGET / SETTLEMENT AUDIT")
    print(f"Source snapshot: {sid}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print(f"Regular-season team-games: {expected_team_games:,}")
    print(f"Target rows: {n:,} ({audit['targetCoveragePct']:.2f}%)")
    print(f"Observed starter remains primary QB: {audit['startEqualsPrimaryPct']:.2f}%")
    print(f"Starter structural dropback share <80%: {audit['starterDropbackShareBelow80Pct']:.2f}%")
    print("\nNFLVERSE SEMANTICS CHECK")
    rp=audit["rawPassAttemptSemantics"]
    print(f"  sacks also flagged pass_attempt: {rp['pct']:.2f}% ({rp['sacksAlsoFlaggedPassAttempt']:,}/{rp['structuralSacks']:,})")
    sd=audit["structuralDropbackDecomposition"]
    print(f"  structural DB = throw + sack + scramble: exact {sd['exactPct']:.2f}% · OTHER {sd['otherDropbacks']:,} · CONFLICT {sd['conflictDropbacks']:,} · max abs residual {sd['maxAbsoluteResidual']}")
    sb=audit["settlementBoundary"]
    print(f"  settlement boundary: spikes included {sb['spikePassAttemptsIncluded']:,} · 2PT pass plays excluded {sb['twoPointPassPlaysExcluded']:,} · QB kneels in rushing {sb['qbKneelsIncludedInRushing']:,}")
    yd=audit["passingYardDecomposition"]
    print(f"  air+YAC coverage {yd['coveragePct']:.2f}% · exact {yd['exactPct']:.2f}% · aggregate residual {yd['aggregateResidualYards']:.1f} yd")
    td=audit["targetDistributions"]
    print("\nTARGET DISTRIBUTION MEDIANS")
    print(f"  structural dropbacks {td['structuralDropbacks']['0.5']:.1f} · structural throws {td['structuralThrows']['0.5']:.1f} · settlement attempts {td['settlementPassAttempts']['0.5']:.1f}")
    print(f"  completions {td['settlementCompletions']['0.5']:.1f} · passing yards {td['passingYards']['0.5']:.1f} · sacks {td['sacks']['0.5']:.1f} · scrambles {td['scrambles']['0.5']:.1f}")
    print(f"Gate: {semantic_gate}")
    print("MODEL-FIT BOUNDARY: no coefficients fit; resolver correctness not used to select historical rows.")
    print(f"Targets: {tp}")
    print(f"Audit: {apath}")
    print("PASS QB State 0.1.5 semantic target foundation · 2025 sealed · frozen OMEGA untouched")
    return 0

if __name__=="__main__": raise SystemExit(main())

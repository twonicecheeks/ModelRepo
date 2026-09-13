#!/usr/bin/env python3
"""OMEGA 0.23.1 — rebuild cumulative season evaluation index from immutable freezes.

Read-only over frozen evaluation bundles and score runs. All NFL calendar slots are
first-class: Thursday, Sunday, Monday, Wednesday, international, and holiday games.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import argparse, csv, hashlib, json, os

SCHEMA="OMEGA_PROSPECTIVE_SEASON_INDEX_0.23.1"
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def read_csv(path: Path):
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def write_csv(path: Path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n"); w.writeheader(); w.writerows(rows)
def union_fields(rows,preferred):
    fields=list(preferred)
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    return fields

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); ap.add_argument("--season",type=int,default=2026); a=ap.parse_args(); root=Path(a.root).resolve()
    eval_root=root/"data/prospective/nfl/omega/evaluation_0230"; score_root=root/"data/results/nfl/omega/evaluation_0230"
    bundles=[]; forecast_rows=[]; decision_rows=[]
    if eval_root.exists():
        for edir in sorted(p for p in eval_root.iterdir() if p.is_dir() and not p.name.startswith('.')):
            mp=edir/"OMEGA_0.23_EVALUATION_MANIFEST.json"; fp=edir/"OMEGA_0.23_FORECAST_INDEX.csv"; dp=edir/"OMEGA_0.23_DECISION_LEDGER.csv"
            if not mp.exists() or not fp.exists():continue
            meta=json.loads(mp.read_text(encoding="utf-8")); fr=read_csv(fp)
            if not fr or int(fr[0].get("season") or 0)!=a.season:continue
            games=sorted({r.get("game_id","") for r in fr if r.get("game_id")}); packaged=meta.get("packagedAt") or meta.get("frozenAt") or ""
            timing=meta.get("sourceTiming",{})
            bundles.append({"evaluation_id":edir.name,"packaged_at":packaged,"forecast_captured_max":timing.get("forecastCapturedMax","") ,"market_captured_max":timing.get("marketCapturedMax","") ,"forecast_rows":len(fr),"games":len(games),"forecast_sha256":sha(fp),"decision_rows":0})
            for r in fr:
                x=dict(r); x["evaluation_id"]=edir.name; x["packaged_at"]=packaged; forecast_rows.append(x)
            if dp.exists():
                dr=read_csv(dp); bundles[-1]["decision_rows"]=len(dr)
                for r in dr:
                    x=dict(r); x["evaluation_id"]=edir.name; x["packaged_at"]=packaged; decision_rows.append(x)
    latest_scores={}
    if score_root.exists():
        for epath in sorted(p for p in score_root.iterdir() if p.is_dir()):
            runs=sorted([p for p in epath.iterdir() if p.is_dir() and not p.name.startswith('.')])
            best=None
            for rdir in runs:
                rp=rdir/"OMEGA_0.23_SCORE_REPORT.json"
                if rp.exists():best=(rdir,json.loads(rp.read_text(encoding="utf-8")))
            if best:latest_scores[epath.name]=best
    scored_players=[]; scored_thresholds=[]; scored_decisions=[]; score_summaries=[]
    for eid,(rdir,meta) in sorted(latest_scores.items()):
        pp=rdir/"OMEGA_0.23_PLAYER_SCORED.csv"; tp=rdir/"OMEGA_0.23_THRESHOLD_SCORED.csv"; dp=rdir/"OMEGA_0.23_DECISIONS_SCORED.csv"
        if pp.exists():
            for r in read_csv(pp):
                if int(r.get("season") or 0)==a.season:
                    x=dict(r); x["evaluation_id"]=eid; x["score_id"]=rdir.name; scored_players.append(x)
        if tp.exists():
            for r in read_csv(tp):
                if int(r.get("season") or 0)==a.season:
                    x=dict(r); x["evaluation_id"]=eid; x["score_id"]=rdir.name; scored_thresholds.append(x)
        if dp.exists():
            for r in read_csv(dp):
                x=dict(r); x["evaluation_id"]=eid; x["score_id"]=rdir.name; scored_decisions.append(x)
        score_summaries.append({"evaluation_id":eid,"score_id":rdir.name,"status":meta.get("status",""),"scored_at":meta.get("scoredAt",""),"graded_forecast_rows":meta.get("coverage",{}).get("gradedForecastRows",0),"graded_threshold_rows":meta.get("coverage",{}).get("gradedThresholdRows",0),"decision_rows":meta.get("coverage",{}).get("decisionRows",0)})
    out=root/"data/results/nfl/omega/season_index_0230"/str(a.season); out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"OMEGA_0.23_SEASON_EVALUATIONS.csv",bundles,["evaluation_id","packaged_at","forecast_captured_max","market_captured_max","forecast_rows","games","forecast_sha256","decision_rows"])
    write_csv(out/"OMEGA_0.23_SEASON_FORECASTS.csv",forecast_rows,union_fields(forecast_rows,["evaluation_id","packaged_at","game_id","season","week","kickoff_utc","team","opponent","player_id","player_name","predicted_xtc"]))
    write_csv(out/"OMEGA_0.23_SEASON_DECISIONS.csv",decision_rows,union_fields(decision_rows,["evaluation_id","packaged_at","game_id","player_id","player_name","team","opponent","side","line","book","price_american","model_probability","expected_roi"]))
    write_csv(out/"OMEGA_0.23_SEASON_PLAYER_SCORES.csv",scored_players,union_fields(scored_players,["evaluation_id","score_id","game_id","season","week","kickoff_utc","team","opponent","player_id","player_name","predicted_xtc","actual_xtc","grade_status"]))
    write_csv(out/"OMEGA_0.23_SEASON_THRESHOLD_SCORES.csv",scored_thresholds,union_fields(scored_thresholds,["evaluation_id","score_id","game_id","season","week","team","opponent","player_id","player_name","line","side","model_probability","actual_event","brier_score","log_loss","grade_status"]))
    write_csv(out/"OMEGA_0.23_SEASON_DECISION_SCORES.csv",scored_decisions,union_fields(scored_decisions,["evaluation_id","score_id","game_id","player_id","player_name","team","opponent","side","line","book","price_american","actual_xtc","result","realized_roi_1u","grade_status"]))
    write_csv(out/"OMEGA_0.23_SEASON_SCORE_RUNS.csv",score_summaries,["evaluation_id","score_id","status","scored_at","graded_forecast_rows","graded_threshold_rows","decision_rows"])
    graded_prob=[r for r in scored_thresholds if r.get("grade_status")=="GRADED" and r.get("brier_score") not in ("",None)]
    report={"schemaVersion":SCHEMA,"generatedAt":now(),"season":a.season,"evaluationBundles":len(bundles),"forecastRows":len(forecast_rows),"decisionRows":len(decision_rows),"latestScoreRuns":len(score_summaries),"gradedPlayerRows":sum(r.get("grade_status")=="GRADED" for r in scored_players),"gradedThresholdRows":len(graded_prob),"gradedDecisionRows":sum(r.get("grade_status")=="GRADED" for r in scored_decisions),"meanThresholdBrier":(sum(float(r["brier_score"]) for r in graded_prob)/len(graded_prob)) if graded_prob else None,"design":"All calendar slots are first-class. No Sunday-only assumption; grouping is by immutable evaluation_id, game_id, kickoff_utc, season, and week.","integrity":{"sourceBundlesModified":False,"sourceScoresModified":False,"omegaModelModified":False}}
    rp=out/"OMEGA_0.23_SEASON_INDEX_REPORT.json"; rp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); (out/"OMEGA_0.23_SEASON_INDEX_REPORT.sha256").write_text(sha(rp)+"\n",encoding="utf-8")
    ptr=root/"data/results/nfl/omega/CURRENT_OMEGA_SEASON_INDEX"; ptr.parent.mkdir(parents=True,exist_ok=True); tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(str(a.season)+"\n",encoding="utf-8"); os.replace(tmp,ptr)
    print("OMEGA 0.23.1 — SEASON-WIDE EVALUATION INDEX")
    print(f"PASS season {a.season} · freezes {len(bundles)} · forecasts {len(forecast_rows)} · decisions {len(decision_rows)}")
    print(f"PASS latest score runs {len(score_summaries)} · graded player rows {report['gradedPlayerRows']} · graded probability rows {report['gradedThresholdRows']} · graded decisions {report['gradedDecisionRows']}")
    print("PASS Thursday/Sunday/Monday/Wednesday/international/holiday games treated identically")
    print(f"REPORT: {rp}")
    return 0
if __name__=="__main__": raise SystemExit(main())

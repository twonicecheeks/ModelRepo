#!/usr/bin/env python3
"""OMEGA 0.35.1 — cumulative overall + defensive-position result scorecard.

Read-only over the season-wide OMEGA evaluation index. The report deliberately
separates three questions:

1) T+A point-forecast accuracy (MAE/RMSE/bias),
2) probability calibration across all half-yard thresholds (Brier/log loss),
3) actual/shadow market-decision performance (W-L-P, units, ROI, calibration).

Forecast/calibration rows use the latest frozen pregame evaluation per player-game
so repeated refreshes do not overweight a player. Decision rows deduplicate by
stable decision_id when present.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse
import csv
import json
import math
import os


VERSION="0.35.1"
SCHEMA="OMEGA_POSITION_RESULTS_SCORECARD_0.35.1"


def read_csv(path: Path) -> list[dict[str,str]]:
    if not path.exists():
        return []
    with path.open(newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields or ["status"],extrasaction="ignore",lineterminator="\n")
        w.writeheader()
        if rows:w.writerows(rows)


def num(v):
    try:
        if v in (None,""):return None
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None


def safe_logloss(p,y):
    p=max(1e-12,min(1-1e-12,float(p)))
    return -(float(y)*math.log(p)+(1-float(y))*math.log(1-p))


def pos_label(v) -> str:
    x=str(v or "").strip().upper()
    return x or "UNKNOWN"


def evaluation_times(rows:list[dict]) -> dict[str,str]:
    out={}
    for r in rows:
        eid=str(r.get("evaluation_id") or "")
        if not eid:continue
        out[eid]=str(r.get("packaged_at") or r.get("frozen_at") or "")
    return out


def latest_player_rows(rows:list[dict], eval_time:dict[str,str]) -> tuple[list[dict],dict[tuple[str,str],str]]:
    best={}
    for r in rows:
        if str(r.get("grade_status") or "")!="GRADED":continue
        gid=str(r.get("game_id") or "");pid=str(r.get("player_id") or "")
        if not gid or not pid:continue
        eid=str(r.get("evaluation_id") or "")
        key=(gid,pid)
        stamp=(eval_time.get(eid,""),eid)
        prior=best.get(key)
        if prior is None or stamp>(prior[0],prior[1]):
            best[key]=(stamp[0],stamp[1],dict(r))
    chosen=[v[2] for v in best.values()]
    latest_eid={k:v[1] for k,v in best.items()}
    return chosen,latest_eid


def latest_threshold_rows(rows:list[dict], latest_eid:dict[tuple[str,str],str]) -> list[dict]:
    out=[]
    for r in rows:
        if str(r.get("grade_status") or "")!="GRADED":continue
        key=(str(r.get("game_id") or ""),str(r.get("player_id") or ""))
        if key in latest_eid and str(r.get("evaluation_id") or "")==latest_eid[key]:
            out.append(dict(r))
    return out


def dedupe_decisions(rows:list[dict]) -> list[dict]:
    best={}
    for i,r in enumerate(rows):
        if str(r.get("grade_status") or "")!="GRADED":continue
        did=str(r.get("decision_id") or "").strip()
        if did:
            key=("ID",did)
        else:
            key=("COMPOSITE",
                 str(r.get("game_id") or ""),str(r.get("player_id") or ""),
                 str(r.get("book") or ""),str(r.get("side") or ""),str(r.get("line") or ""),
                 str(r.get("price_american") or ""),str(r.get("market_captured_at") or ""))
        stamp=(str(r.get("score_id") or ""),i)
        prior=best.get(key)
        if prior is None or stamp>(prior[0],prior[1]):
            best[key]=(stamp[0],stamp[1],dict(r))
    return [v[2] for v in best.values()]


def position_map(player_rows:list[dict]) -> dict[tuple[str,str],str]:
    return {
        (str(r.get("game_id") or ""),str(r.get("player_id") or "")):pos_label(r.get("position_group"))
        for r in player_rows
    }


def with_positions(rows:list[dict], pmap:dict[tuple[str,str],str]) -> list[dict]:
    out=[]
    for r in rows:
        x=dict(r)
        key=(str(x.get("game_id") or ""),str(x.get("player_id") or ""))
        x["position_group"]=pos_label(x.get("position_group") or pmap.get(key))
        out.append(x)
    return out


def forecast_metrics(rows:list[dict]) -> dict:
    z=[]
    for r in rows:
        a=num(r.get("actual_xtc"));p=num(r.get("predicted_xtc"))
        if a is not None and p is not None:z.append((a,p))
    if not z:return {"n":0}
    err=[p-a for a,p in z]
    return {
        "n":len(z),
        "mae":fmean(abs(e) for e in err),
        "rmse":math.sqrt(fmean(e*e for e in err)),
        "biasPredMinusActual":fmean(err),
        "actualMean":fmean(a for a,_ in z),
        "predictedMean":fmean(p for _,p in z),
    }


def probability_metrics(rows:list[dict]) -> dict:
    z=[]
    for r in rows:
        p=num(r.get("model_probability"));y=num(r.get("actual_event"))
        if p is not None and y is not None:z.append((p,y))
    if not z:return {"n":0}
    return {
        "n":len(z),
        "brier":fmean((p-y)**2 for p,y in z),
        "logLoss":fmean(safe_logloss(p,y) for p,y in z),
        "meanPredictedProbability":fmean(p for p,_ in z),
        "eventRate":fmean(y for _,y in z),
    }


def decision_metrics(rows:list[dict]) -> dict:
    z=[r for r in rows if str(r.get("grade_status") or "")=="GRADED"]
    if not z:return {"n":0,"sampleStatus":"NO_GRADED_DECISIONS"}
    wins=sum(str(r.get("result") or "")=="WIN" for r in z)
    losses=sum(str(r.get("result") or "")=="LOSS" for r in z)
    pushes=sum(str(r.get("result") or "")=="PUSH" for r in z)
    resolved=wins+losses
    roi=[num(r.get("realized_roi_1u")) for r in z];roi=[x for x in roi if x is not None]
    ev=[num(r.get("expected_roi")) for r in z];ev=[x for x in ev if x is not None]
    cal=[]
    for r in z:
        if str(r.get("result") or "")=="PUSH":continue
        p=num(r.get("model_probability"))
        if p is None:continue
        y=1.0 if str(r.get("result") or "")=="WIN" else 0.0
        cal.append((p,y))
    return {
        "n":len(z),
        "wins":wins,"losses":losses,"pushes":pushes,
        "hitRateExPush":wins/resolved if resolved else None,
        "unitsAt1uEach":sum(roi) if roi else None,
        "roi":fmean(roi) if roi else None,
        "meanExpectedRoi":fmean(ev) if ev else None,
        "meanModelProbability":fmean(p for p,_ in cal) if cal else None,
        "eventRate":fmean(y for _,y in cal) if cal else None,
        "brier":fmean((p-y)**2 for p,y in cal) if cal else None,
        "logLoss":fmean(safe_logloss(p,y) for p,y in cal) if cal else None,
        "sampleStatus":"ADEQUATE_FOR_MONITORING" if resolved>=50 else ("EARLY_SAMPLE" if resolved>=20 else "VERY_SMALL_SAMPLE"),
    }


def grouped(rows:list[dict], fn) -> dict[str,dict]:
    g=defaultdict(list)
    for r in rows:g[pos_label(r.get("position_group"))].append(r)
    return {k:fn(v) for k,v in sorted(g.items())}


def flatten_rows(forecast_by,prob_by,decision_by):
    cats=sorted(set(forecast_by)|set(prob_by)|set(decision_by))
    out=[]
    for pos in cats:
        f=forecast_by.get(pos,{"n":0});p=prob_by.get(pos,{"n":0});d=decision_by.get(pos,{"n":0})
        out.append({
            "position_group":pos,
            "forecast_n":f.get("n",0),
            "forecast_mae":f.get("mae"),
            "forecast_rmse":f.get("rmse"),
            "forecast_bias_pred_minus_actual":f.get("biasPredMinusActual"),
            "probability_n":p.get("n",0),
            "probability_brier":p.get("brier"),
            "probability_log_loss":p.get("logLoss"),
            "decision_n":d.get("n",0),
            "wins":d.get("wins"),"losses":d.get("losses"),"pushes":d.get("pushes"),
            "hit_rate_ex_push":d.get("hitRateExPush"),
            "units_at_1u_each":d.get("unitsAt1uEach"),
            "roi":d.get("roi"),
            "mean_expected_roi":d.get("meanExpectedRoi"),
            "decision_brier":d.get("brier"),
            "decision_log_loss":d.get("logLoss"),
            "sample_status":d.get("sampleStatus"),
        })
    return out


def fmt(v,d=3):
    return "NA" if v is None else f"{float(v):.{d}f}"
def pct(v):
    return "NA" if v is None else f"{100*float(v):.1f}%"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--season",type=int,default=2026)
    a=ap.parse_args();root=Path(a.root).expanduser().resolve()
    idx=root/"data/results/nfl/omega/season_index_0230"/str(a.season)
    if not idx.exists():
        raise FileNotFoundError(f"season index missing: {idx}; rebuild OMEGA season index first")

    evals=read_csv(idx/"OMEGA_0.23_SEASON_EVALUATIONS.csv")
    players=read_csv(idx/"OMEGA_0.23_SEASON_PLAYER_SCORES.csv")
    thresholds=read_csv(idx/"OMEGA_0.23_SEASON_THRESHOLD_SCORES.csv")
    decisions=read_csv(idx/"OMEGA_0.23_SEASON_DECISION_SCORES.csv")

    et=evaluation_times(evals)
    latest_players,latest_eid=latest_player_rows(players,et)
    latest_thresholds=latest_threshold_rows(thresholds,latest_eid)
    pmap=position_map(latest_players)
    latest_thresholds=with_positions(latest_thresholds,pmap)
    decisions=with_positions(dedupe_decisions(decisions),pmap)

    overall={
        "forecast":forecast_metrics(latest_players),
        "probability":probability_metrics(latest_thresholds),
        "decisions":decision_metrics(decisions),
    }
    by_forecast=grouped(latest_players,forecast_metrics)
    by_prob=grouped(latest_thresholds,probability_metrics)
    by_dec=grouped(decisions,decision_metrics)
    flat=flatten_rows(by_forecast,by_prob,by_dec)

    out=root/"data/results/nfl/omega/position_results_0351"/str(a.season)
    out.mkdir(parents=True,exist_ok=True)
    generated=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
    report={
        "schemaVersion":SCHEMA,"version":VERSION,"generatedAt":generated,"season":a.season,
        "dedupe":{
            "forecastAndProbability":"latest frozen evaluation per game_id + player_id",
            "decisions":"stable decision_id when present; otherwise market composite key",
        },
        "coverage":{
            "sourceEvaluationRows":len(evals),"sourcePlayerScoreRows":len(players),
            "latestUniquePlayerGameForecasts":len(latest_players),
            "latestThresholdRows":len(latest_thresholds),
            "dedupedDecisionRows":len(decisions),
        },
        "overall":overall,
        "byPosition":{
            pos:{
                "forecast":by_forecast.get(pos,{"n":0}),
                "probability":by_prob.get(pos,{"n":0}),
                "decisions":by_dec.get(pos,{"n":0}),
            } for pos in sorted(set(by_forecast)|set(by_prob)|set(by_dec))
        },
        "interpretationGuard":"Compare positions only with sample size/calibration in view. ROI alone is noisy; forecast error and Brier/log loss are included to separate model quality from price/result variance.",
        "integrity":{"sourceScoresModified":False,"omegaModelModified":False,"modelRefitPerformed":False},
    }
    (out/"OMEGA_0.35.1_POSITION_RESULTS_REPORT.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    write_csv(out/"OMEGA_0.35.1_POSITION_RESULTS_SUMMARY.csv",flat)

    o=overall;dm=o["decisions"];fm=o["forecast"];pm=o["probability"]
    lines=[
        "OMEGA 0.35.1 — CUMULATIVE RESULTS BY DEFENSIVE POSITION",
        "",
        f"Season: {a.season}",
        f"Unique latest player-game forecasts: {len(latest_players)}",
        f"Threshold probability rows: {len(latest_thresholds)}",
        f"Deduped market decisions: {len(decisions)}",
        "",
        "OVERALL",
        f"  Count forecast: n {fm.get('n',0)} · MAE {fmt(fm.get('mae'))} · RMSE {fmt(fm.get('rmse'))} · bias {fmt(fm.get('biasPredMinusActual'))}",
        f"  Probability: n {pm.get('n',0)} · Brier {fmt(pm.get('brier'),4)} · logloss {fmt(pm.get('logLoss'),4)} · mean p {pct(pm.get('meanPredictedProbability'))} · event {pct(pm.get('eventRate'))}",
        f"  Decisions: n {dm.get('n',0)} · W-L-P {dm.get('wins',0)}-{dm.get('losses',0)}-{dm.get('pushes',0)} · hit {pct(dm.get('hitRateExPush'))} · units {fmt(dm.get('unitsAt1uEach'))} · ROI {pct(dm.get('roi'))} · Brier {fmt(dm.get('brier'),4)} · {dm.get('sampleStatus','')}",
        "",
        "BY POSITION",
    ]
    for pos in sorted(report["byPosition"]):
        r=report["byPosition"][pos];f=r["forecast"];p=r["probability"];d=r["decisions"]
        lines += [
            "",
            f"  {pos}",
            f"    Count forecast: n {f.get('n',0)} · MAE {fmt(f.get('mae'))} · RMSE {fmt(f.get('rmse'))} · bias {fmt(f.get('biasPredMinusActual'))}",
            f"    Probability: n {p.get('n',0)} · Brier {fmt(p.get('brier'),4)} · logloss {fmt(p.get('logLoss'),4)} · mean p {pct(p.get('meanPredictedProbability'))} · event {pct(p.get('eventRate'))}",
            f"    Decisions: n {d.get('n',0)} · W-L-P {d.get('wins',0)}-{d.get('losses',0)}-{d.get('pushes',0)} · hit {pct(d.get('hitRateExPush'))} · units {fmt(d.get('unitsAt1uEach'))} · ROI {pct(d.get('roi'))} · Brier {fmt(d.get('brier'),4)} · {d.get('sampleStatus','')}",
        ]
    lines += [
        "",
        "READING THE REPORT",
        "  MAE/RMSE: lower is better for tackle-count projection.",
        "  Bias: positive = OMEGA predicts too many tackles; negative = too few.",
        "  Brier/log loss: lower is better probability calibration.",
        "  ROI/hit rate: useful, but noisier than calibration at small n.",
        "  Position comparisons should not be trusted from tiny samples.",
        "",
        f"JSON: {out/'OMEGA_0.35.1_POSITION_RESULTS_REPORT.json'}",
        f"CSV: {out/'OMEGA_0.35.1_POSITION_RESULTS_SUMMARY.csv'}",
    ]
    txt=out/"OMEGA_0.35.1_POSITION_RESULTS_REPORT.txt"
    txt.write_text("\n".join(lines)+"\n",encoding="utf-8")
    ptr=root/"data/results/nfl/omega/CURRENT_OMEGA_POSITION_RESULTS_0351"
    ptr.parent.mkdir(parents=True,exist_ok=True);tmp=ptr.with_name("."+ptr.name+".tmp")
    tmp.write_text(str(a.season)+"\n",encoding="utf-8");os.replace(tmp,ptr)
    print(txt.read_text(encoding="utf-8"))
    print("PASS read-only cumulative position scorecard · OMEGA mutation NO · refit NO")
    return 0

if __name__=="__main__":raise SystemExit(main())

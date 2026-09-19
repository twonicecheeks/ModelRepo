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


def load_market_calibration_0350(root: Path, season: int) -> list[dict]:
    """Load newest immutable 0.35 calibration row per market identity."""
    base=root/"data/results/nfl/omega_market_calibration_0350"
    best={}
    if not base.exists():
        return []
    for game_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        try:
            game_season=int(str(game_dir.name).split("_",1)[0])
        except Exception:
            game_season=season
        if game_season!=season:
            continue
        for run_dir in sorted(p for p in game_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            sp=run_dir/"OMEGA_0.35_MARKET_CALIBRATION_SCORED.csv"
            if not sp.exists():
                continue
            for i,r in enumerate(read_csv(sp)):
                x=dict(r)
                x["_calibration_run_id"]=run_dir.name
                x["_calibration_game_id"]=game_dir.name
                key=(
                    str(x.get("game_id") or game_dir.name),
                    str(x.get("player_id") or ""),
                    str(x.get("book") or ""),
                    str(x.get("line") or ""),
                    str(x.get("control_best_side") or ""),
                    str(x.get("control_selected_price_american") or x.get("over_odds_american") or x.get("under_odds_american") or ""),
                )
                stamp=(run_dir.name,i)
                prior=best.get(key)
                if prior is None or stamp>(prior[0],prior[1]):
                    best[key]=(stamp[0],stamp[1],x)
    return [v[2] for v in best.values()]


def market035_metrics(rows:list[dict]) -> dict:
    z=[r for r in rows if r.get("control_selected_hit") not in (None,"")]
    if not z:return {"n":0,"sampleStatus":"NO_GRADED_ROWS"}
    wins=sum(int(float(r.get("control_selected_hit") or 0))==1 for r in z)
    losses=sum(int(float(r.get("control_selected_hit") or 0))==0 for r in z)
    roi=[num(r.get("control_realized_roi")) for r in z];roi=[x for x in roi if x is not None]
    cal=[]
    for r in z:
        p=num(r.get("control_selected_probability"))
        if p is None:continue
        y=float(r.get("control_selected_hit"))
        cal.append((p,y))
    resolved=wins+losses
    return {
        "n":len(z),"wins":wins,"losses":losses,"pushes":0,
        "hitRateExPush":wins/resolved if resolved else None,
        "unitsAt1uEach":sum(roi) if roi else None,
        "roi":fmean(roi) if roi else None,
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


def grouped_position_side(rows:list[dict], fn, side_key:str) -> dict[str,dict]:
    g=defaultdict(list)
    for r in rows:
        pos=pos_label(r.get("position_group"))
        side=str(r.get(side_key) or "").strip().upper() or "UNKNOWN"
        g[f"{pos}|{side}"].append(r)
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
    market035=load_market_calibration_0350(root,a.season)
    market035=with_positions(market035,pmap)
    market035_clean=[r for r in market035 if str(r.get("clean_role_state") or "").lower() in {"true","1"} and str(r.get("executable_quote") or "").lower() in {"true","1"} and str(r.get("quarantined_or_reference") or "").lower() not in {"true","1"}]

    overall={
        "forecast":forecast_metrics(latest_players),
        "probability":probability_metrics(latest_thresholds),
        "decisions":decision_metrics(decisions),
        "currentGenerationMarket035":market035_metrics(market035),
        "currentGenerationCleanMarket035":market035_metrics(market035_clean),
    }
    by_forecast=grouped(latest_players,forecast_metrics)
    by_prob=grouped(latest_thresholds,probability_metrics)
    by_dec=grouped(decisions,decision_metrics)
    by_m035=grouped(market035,market035_metrics)
    by_m035_clean=grouped(market035_clean,market035_metrics)
    by_pos_side_dec=grouped_position_side(decisions,decision_metrics,"side")
    by_pos_side_m035=grouped_position_side(market035,market035_metrics,"control_best_side")
    by_pos_side_m035_clean=grouped_position_side(market035_clean,market035_metrics,"control_best_side")
    flat=flatten_rows(by_forecast,by_prob,by_dec)
    for row in flat:
        pos=row["position_group"]
        m=by_m035.get(pos,{"n":0});mc=by_m035_clean.get(pos,{"n":0})
        row.update({
            "market035_n":m.get("n",0),"market035_wins":m.get("wins"),"market035_losses":m.get("losses"),
            "market035_hit_rate":m.get("hitRateExPush"),"market035_units":m.get("unitsAt1uEach"),
            "market035_roi":m.get("roi"),"market035_brier":m.get("brier"),"market035_sample_status":m.get("sampleStatus"),
            "market035_clean_n":mc.get("n",0),"market035_clean_wins":mc.get("wins"),"market035_clean_losses":mc.get("losses"),
            "market035_clean_hit_rate":mc.get("hitRateExPush"),"market035_clean_units":mc.get("unitsAt1uEach"),
            "market035_clean_roi":mc.get("roi"),"market035_clean_brier":mc.get("brier"),"market035_clean_sample_status":mc.get("sampleStatus"),
        })
    extra_positions=sorted((set(by_m035)|set(by_m035_clean))-{r["position_group"] for r in flat})
    for pos in extra_positions:
        m=by_m035.get(pos,{"n":0});mc=by_m035_clean.get(pos,{"n":0})
        flat.append({"position_group":pos,"forecast_n":0,"probability_n":0,"decision_n":0,
                     "market035_n":m.get("n",0),"market035_wins":m.get("wins"),"market035_losses":m.get("losses"),
                     "market035_hit_rate":m.get("hitRateExPush"),"market035_units":m.get("unitsAt1uEach"),
                     "market035_roi":m.get("roi"),"market035_brier":m.get("brier"),"market035_sample_status":m.get("sampleStatus"),
                     "market035_clean_n":mc.get("n",0),"market035_clean_wins":mc.get("wins"),"market035_clean_losses":mc.get("losses"),
                     "market035_clean_hit_rate":mc.get("hitRateExPush"),"market035_clean_units":mc.get("unitsAt1uEach"),
                     "market035_clean_roi":mc.get("roi"),"market035_clean_brier":mc.get("brier"),"market035_clean_sample_status":mc.get("sampleStatus")})

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
            "currentGenerationMarket035Rows":len(market035),
            "currentGenerationCleanMarket035Rows":len(market035_clean),
        },
        "overall":overall,
        "byPosition":{
            pos:{
                "forecast":by_forecast.get(pos,{"n":0}),
                "probability":by_prob.get(pos,{"n":0}),
                "decisions":by_dec.get(pos,{"n":0}),
                "currentGenerationMarket035":by_m035.get(pos,{"n":0}),
                "currentGenerationCleanMarket035":by_m035_clean.get(pos,{"n":0}),
            } for pos in sorted(set(by_forecast)|set(by_prob)|set(by_dec)|set(by_m035)|set(by_m035_clean))
        },
        "byPositionSide":{
            "legacyProspectiveDecisions":by_pos_side_dec,
            "currentGenerationMarket035":by_pos_side_m035,
            "currentGenerationCleanMarket035":by_pos_side_m035_clean,
        },
        "interpretationGuard":"Compare positions only with sample size/calibration in view. ROI alone is noisy; forecast error and Brier/log loss are included to separate model quality from price/result variance.",
        "integrity":{"sourceScoresModified":False,"omegaModelModified":False,"modelRefitPerformed":False},
    }
    (out/"OMEGA_0.35.1_POSITION_RESULTS_REPORT.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    write_csv(out/"OMEGA_0.35.1_POSITION_RESULTS_SUMMARY.csv",flat)
    side_rows=[]
    side_keys=sorted(set(by_pos_side_dec)|set(by_pos_side_m035)|set(by_pos_side_m035_clean))
    for key in side_keys:
        pos,side=key.split("|",1)
        d=by_pos_side_dec.get(key,{"n":0});m=by_pos_side_m035.get(key,{"n":0});mc=by_pos_side_m035_clean.get(key,{"n":0})
        side_rows.append({
            "position_group":pos,"side":side,
            "legacy_n":d.get("n",0),"legacy_wins":d.get("wins"),"legacy_losses":d.get("losses"),"legacy_pushes":d.get("pushes"),
            "legacy_hit_rate":d.get("hitRateExPush"),"legacy_units":d.get("unitsAt1uEach"),"legacy_roi":d.get("roi"),"legacy_brier":d.get("brier"),
            "market035_n":m.get("n",0),"market035_wins":m.get("wins"),"market035_losses":m.get("losses"),
            "market035_hit_rate":m.get("hitRateExPush"),"market035_units":m.get("unitsAt1uEach"),"market035_roi":m.get("roi"),"market035_brier":m.get("brier"),
            "market035_clean_n":mc.get("n",0),"market035_clean_wins":mc.get("wins"),"market035_clean_losses":mc.get("losses"),
            "market035_clean_hit_rate":mc.get("hitRateExPush"),"market035_clean_units":mc.get("unitsAt1uEach"),"market035_clean_roi":mc.get("roi"),"market035_clean_brier":mc.get("brier"),
        })
    write_csv(out/"OMEGA_0.35.1_POSITION_SIDE_RESULTS_SUMMARY.csv",side_rows)

    o=overall;dm=o["decisions"];fm=o["forecast"];pm=o["probability"];m35=o["currentGenerationMarket035"];m35c=o["currentGenerationCleanMarket035"]
    lines=[
        "OMEGA 0.35.1 — CUMULATIVE RESULTS BY DEFENSIVE POSITION",
        "",
        f"Season: {a.season}",
        f"Unique latest player-game forecasts: {len(latest_players)}",
        f"Threshold probability rows: {len(latest_thresholds)}",
        f"Deduped legacy/prospective decisions: {len(decisions)}",
        f"Current-generation 0.35 graded market rows: {len(market035)} · clean subset {len(market035_clean)}",
        "",
        "OVERALL",
        f"  Count forecast: n {fm.get('n',0)} · MAE {fmt(fm.get('mae'))} · RMSE {fmt(fm.get('rmse'))} · bias {fmt(fm.get('biasPredMinusActual'))}",
        f"  Probability: n {pm.get('n',0)} · Brier {fmt(pm.get('brier'),4)} · logloss {fmt(pm.get('logLoss'),4)} · mean p {pct(pm.get('meanPredictedProbability'))} · event {pct(pm.get('eventRate'))}",
        f"  Legacy/prospective decisions: n {dm.get('n',0)} · W-L-P {dm.get('wins',0)}-{dm.get('losses',0)}-{dm.get('pushes',0)} · hit {pct(dm.get('hitRateExPush'))} · units {fmt(dm.get('unitsAt1uEach'))} · ROI {pct(dm.get('roi'))} · Brier {fmt(dm.get('brier'),4)} · {dm.get('sampleStatus','')}",
        f"  Current 0.35 all graded rows: n {m35.get('n',0)} · W-L {m35.get('wins',0)}-{m35.get('losses',0)} · hit {pct(m35.get('hitRateExPush'))} · units {fmt(m35.get('unitsAt1uEach'))} · ROI {pct(m35.get('roi'))} · Brier {fmt(m35.get('brier'),4)} · {m35.get('sampleStatus','')}",
        f"  Current 0.35 clean role/executable: n {m35c.get('n',0)} · W-L {m35c.get('wins',0)}-{m35c.get('losses',0)} · hit {pct(m35c.get('hitRateExPush'))} · units {fmt(m35c.get('unitsAt1uEach'))} · ROI {pct(m35c.get('roi'))} · Brier {fmt(m35c.get('brier'),4)} · {m35c.get('sampleStatus','')}",
        "",
        "BY POSITION",
    ]
    for pos in sorted(report["byPosition"]):
        r=report["byPosition"][pos];f=r["forecast"];p=r["probability"];d=r["decisions"];m=r["currentGenerationMarket035"];mc=r["currentGenerationCleanMarket035"]
        lines += [
            "",
            f"  {pos}",
            f"    Count forecast: n {f.get('n',0)} · MAE {fmt(f.get('mae'))} · RMSE {fmt(f.get('rmse'))} · bias {fmt(f.get('biasPredMinusActual'))}",
            f"    Probability: n {p.get('n',0)} · Brier {fmt(p.get('brier'),4)} · logloss {fmt(p.get('logLoss'),4)} · mean p {pct(p.get('meanPredictedProbability'))} · event {pct(p.get('eventRate'))}",
            f"    Legacy/prospective decisions: n {d.get('n',0)} · W-L-P {d.get('wins',0)}-{d.get('losses',0)}-{d.get('pushes',0)} · hit {pct(d.get('hitRateExPush'))} · units {fmt(d.get('unitsAt1uEach'))} · ROI {pct(d.get('roi'))} · Brier {fmt(d.get('brier'),4)} · {d.get('sampleStatus','')}",
            f"    Current 0.35 all: n {m.get('n',0)} · W-L {m.get('wins',0)}-{m.get('losses',0)} · hit {pct(m.get('hitRateExPush'))} · units {fmt(m.get('unitsAt1uEach'))} · ROI {pct(m.get('roi'))} · Brier {fmt(m.get('brier'),4)} · {m.get('sampleStatus','')}",
            f"    Current 0.35 clean: n {mc.get('n',0)} · W-L {mc.get('wins',0)}-{mc.get('losses',0)} · hit {pct(mc.get('hitRateExPush'))} · units {fmt(mc.get('unitsAt1uEach'))} · ROI {pct(mc.get('roi'))} · Brier {fmt(mc.get('brier'),4)} · {mc.get('sampleStatus','')}",
        ]
    lines += [
        "",
        "POSITION × SIDE",
    ]
    for key in sorted(set(by_pos_side_dec)|set(by_pos_side_m035)|set(by_pos_side_m035_clean)):
        pos,side=key.split("|",1);d=by_pos_side_dec.get(key,{"n":0});m=by_pos_side_m035.get(key,{"n":0});mc=by_pos_side_m035_clean.get(key,{"n":0})
        lines += [
            f"  {pos} {side}",
            f"    legacy: n {d.get('n',0)} · W-L-P {d.get('wins',0)}-{d.get('losses',0)}-{d.get('pushes',0)} · hit {pct(d.get('hitRateExPush'))} · ROI {pct(d.get('roi'))}",
            f"    current 0.35 all: n {m.get('n',0)} · W-L {m.get('wins',0)}-{m.get('losses',0)} · hit {pct(m.get('hitRateExPush'))} · ROI {pct(m.get('roi'))} · Brier {fmt(m.get('brier'),4)}",
            f"    current 0.35 clean: n {mc.get('n',0)} · W-L {mc.get('wins',0)}-{mc.get('losses',0)} · hit {pct(mc.get('hitRateExPush'))} · ROI {pct(mc.get('roi'))} · Brier {fmt(mc.get('brier'),4)}",
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
        f"SIDE CSV: {out/'OMEGA_0.35.1_POSITION_SIDE_RESULTS_SUMMARY.csv'}",
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

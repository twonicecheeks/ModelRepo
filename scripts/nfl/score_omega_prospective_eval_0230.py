#!/usr/bin/env python3
"""OMEGA 0.23 — score a frozen prospective evaluation bundle against realized T+A.

Downstream evaluation only. OMEGA model artifacts remain read-only. Each score run
is immutable; partial runs are allowed, and later runs supersede them by pointer.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse, csv, hashlib, json, math, os, re, shutil, unicodedata

SCHEMA="OMEGA_PROSPECTIVE_EVALUATION_SCORE_0.23.0"
TEAM_GROUPS={
 'CARDINALS':['ARI','ARIZONA','ARIZONACARDINALS'], 'FALCONS':['ATL','ATLANTA','ATLANTAFALCONS'],
 'RAVENS':['BAL','BALTIMORE','BALTIMORERAVENS'], 'BILLS':['BUF','BUFFALO','BUFFALOBILLS'],
 'PANTHERS':['CAR','CAROLINA','CAROLINAPANTHERS'], 'BEARS':['CHI','CHICAGO','CHICAGOBEARS'],
 'BENGALS':['CIN','CINCINNATI','CINCINNATIBENGALS'], 'BROWNS':['CLE','CLEVELAND','CLEVELANDBROWNS'],
 'COWBOYS':['DAL','DALLAS','DALLASCOWBOYS'], 'BRONCOS':['DEN','DENVER','DENVERBRONCOS'],
 'LIONS':['DET','DETROIT','DETROITLIONS'], 'PACKERS':['GB','GNB','GREENBAY','GREENBAYPACKERS'],
 'TEXANS':['HOU','HOUSTON','HOUSTONTEXANS'], 'COLTS':['IND','INDIANAPOLIS','INDIANAPOLISCOLTS'],
 'JAGUARS':['JAX','JAC','JACKSONVILLE','JACKSONVILLEJAGUARS'], 'CHIEFS':['KC','KAN','KANSASCITY','KANSASCITYCHIEFS'],
 'RAIDERS':['LV','LVR','LASVEGAS','LASVEGASRAIDERS','OAK'], 'CHARGERS':['LAC','LOSANGELESCHARGERS','LACHARGERS','SD'],
 'RAMS':['LA','LAR','LOSANGELESRAMS','LARAMS','STL'], 'DOLPHINS':['MIA','MIAMI','MIAMIDOLPHINS'],
 'VIKINGS':['MIN','MINNESOTA','MINNESOTAVIKINGS'], 'PATRIOTS':['NE','NWE','NEWENGLAND','NEWENGLANDPATRIOTS'],
 'SAINTS':['NO','NOR','NEWORLEANS','NEWORLEANSSAINTS'], 'GIANTS':['NYG','NEWYORKGIANTS','NYGIANTS'],
 'JETS':['NYJ','NEWYORKJETS','NYJETS'], 'EAGLES':['PHI','PHILADELPHIA','PHILADELPHIAEAGLES'],
 'STEELERS':['PIT','PITTSBURGH','PITTSBURGHSTEELERS'], 'SEAHAWKS':['SEA','SEATTLE','SEATTLESEAHAWKS'],
 '49ERS':['SF','SFO','SANFRANCISCO','SANFRANCISCO49ERS','49ERS'], 'BUCCANEERS':['TB','TAM','TAMPABAY','TAMPABAYBUCCANEERS','BUCS'],
 'TITANS':['TEN','TENNESSEE','TENNESSEETITANS'], 'COMMANDERS':['WAS','WSH','WASHINGTON','WASHINGTONCOMMANDERS','WASHINGTONFOOTBALLTEAM'],
}
TEAM_ALIAS={}
for canon, vals in TEAM_GROUPS.items():
    for v in vals: TEAM_ALIAS[re.sub(r'[^A-Z0-9]','',v.upper())]=canon

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(path: Path):
    h=hashlib.sha256();
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def read_csv(path: Path):
    with path.open(newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))
def write_csv(path: Path, rows):
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    if not fields: fields=["status"]
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n"); w.writeheader();
        if rows: w.writerows(rows)
    return fields
def ascii_fold(s): return unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode("ascii")
def canon_name(s): return re.sub(r"[^A-Z0-9]","",ascii_fold(s).upper().replace(" JR","").replace(" SR",""))
def canon_team(s):
    x=re.sub(r"[^A-Z0-9]","",ascii_fold(s).upper()); return TEAM_ALIAS.get(x,x)
def num(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None
def american_profit(a): a=float(a); return 100.0/abs(a) if a<0 else a/100.0
def realized_roi(side,line,actual,price):
    win=(actual>line) if side=="OVER" else (actual<line); return american_profit(price) if win else -1.0

def locate_source(root: Path, manifest_arg: str):
    if manifest_arg: manifest=Path(manifest_arg).expanduser().resolve()
    else:
        ptr=root/"data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
        if not ptr.exists(): raise SystemExit("FAIL no CURRENT_RAW_SNAPSHOT; capture a fresh nflverse snapshot first")
        manifest=root/"data/raw/nfl/nflverse/snapshots"/ptr.read_text().strip()/"SOURCE_MANIFEST.json"
    if not manifest.exists(): raise SystemExit(f"FAIL source manifest missing: {manifest}")
    meta=json.loads(manifest.read_text(encoding="utf-8")); assets=meta.get("assets",[])
    pbp=next((x for x in assets if x.get("source")=="play_by_play" and int(x.get("season") or 0)==2026),None)
    sched=next((x for x in assets if x.get("source")=="schedules"),None)
    if not pbp: raise SystemExit("FAIL source manifest has no 2026 play_by_play asset")
    pbp_path=root/str(pbp.get("blobPath") or "")
    if not pbp_path.exists() or sha(pbp_path)!=pbp.get("sha256"): raise SystemExit("FAIL 2026 PBP blob/hash mismatch")
    sched_path=root/str(sched.get("blobPath") or "") if sched else None
    if sched_path and (not sched_path.exists() or sha(sched_path)!=sched.get("sha256")): raise SystemExit("FAIL schedules blob/hash mismatch")
    return manifest,meta,pbp,pbp_path,sched_path

def completed_games_from_schedule(path: Path|None, target_games:set[str]):
    if not path: return set()
    out=set()
    for r in read_csv(path):
        gid=str(r.get("game_id") or "")
        if gid not in target_games: continue
        result=str(r.get("result") or "").strip(); hs=str(r.get("home_score") or "").strip(); aws=str(r.get("away_score") or "").strip()
        if result or (hs!="" and aws!=""): out.add(gid)
    return out

def reconstruct_actuals(root: Path,pbp_path: Path,target_games:set[str]):
    import pyarrow.parquet as pq, sys
    sys.path[:0]=[str(root/"packages/models/nfl/omega"),str(root/"packages/providers/nflverse/src")]
    import tackle_events as te, contract
    pf=pq.ParquetFile(pbp_path); names=set(pf.schema_arrow.names)
    required={"game_id","play_id","season","week","posteam","defteam"}; missing=required-names
    if missing: raise SystemExit(f"FAIL PBP missing required columns: {sorted(missing)}")
    if not (set(te.TACKLE_ID_COLUMNS)&names): raise SystemExit("FAIL PBP has no tackle identity columns")
    cols=list(required)
    optional=("play_type","no_play","play_deleted","special_teams_play","qtr","down","ydstogo","yardline_100","game_seconds_remaining","score_differential","score_differential_post","yards_gained","air_yards","yards_after_catch","run_location","run_gap","pass_location","pass_length","shotgun","no_huddle","qb_scramble","sack","complete_pass","interception","fumble","fumble_lost","rush_attempt","rush","pass_attempt","qb_dropback")
    for c in optional+tuple(te.TACKLE_ID_COLUMNS)+tuple(te.TACKLE_NAME_COLUMNS)+tuple(te.TACKLE_TEAM_COLUMNS):
        if c in names and c not in cols: cols.append(c)
    raw=pf.read(columns=cols).to_pylist(); actual=defaultdict(int); seen=set(); pbp_rows=0; standard=0
    for r in raw:
        gid=str(r.get("game_id") or "")
        if gid not in target_games: continue
        seen.add(gid); pbp_rows+=1
        if r.get("posteam"): r["posteam"]=contract.normalize_team_abbr(str(r["posteam"]))
        if r.get("defteam"): r["defteam"]=contract.normalize_team_abbr(str(r["defteam"]))
        for e in te.extract_credit_events(r):
            if int(e.get("is_standard_def_scrimmage_credit") or 0)!=1: continue
            pid=str(e.get("player_id") or "").strip()
            if not pid: raise SystemExit(f"FAIL standard tackle credit missing player_id in {gid}")
            unit=int(e.get("combined_credit_unit") or 1)
            if unit<=0: raise SystemExit("FAIL non-positive tackle credit unit")
            actual[(gid,pid)]+=unit; standard+=unit
    return dict(actual),seen,{"pbpRowsTargetGames":pbp_rows,"standardCreditUnits":standard}

def player_metrics(rows):
    graded=[r for r in rows if r.get("grade_status")=="GRADED"]
    if not graded: return {"n":0}
    ys=[float(r["actual_xtc"]) for r in graded]; ps=[float(r["predicted_xtc"]) for r in graded]
    return {"n":len(graded),"actualMean":fmean(ys),"predictedMean":fmean(ps),"mae":fmean(abs(y-p) for y,p in zip(ys,ps)),"rmse":math.sqrt(fmean((y-p)**2 for y,p in zip(ys,ps))),"biasPredMinusActual":fmean(p-y for y,p in zip(ys,ps))}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); ap.add_argument("--evaluation-id",default=""); ap.add_argument("--source-manifest",default=""); a=ap.parse_args(); root=Path(a.root).resolve()
    if a.evaluation_id: eid=a.evaluation_id
    else:
        ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_PROSPECTIVE_EVALUATION"
        if not ptr.exists(): raise SystemExit("FAIL no current OMEGA prospective evaluation")
        eid=ptr.read_text().strip()
    edir=root/"data/prospective/nfl/omega/evaluation_0230"/eid; manifest_path=edir/"OMEGA_0.23_EVALUATION_MANIFEST.json"; manifest_sidecar=edir/"OMEGA_0.23_EVALUATION_MANIFEST.sha256"; forecast_path=edir/"OMEGA_0.23_FORECAST_INDEX.csv"
    if not manifest_path.exists() or not forecast_path.exists() or not manifest_sidecar.exists(): raise SystemExit("FAIL evaluation bundle incomplete")
    if sha(manifest_path)!=manifest_sidecar.read_text().strip(): raise SystemExit("FAIL evaluation manifest hash mismatch")
    emeta=json.loads(manifest_path.read_text(encoding="utf-8"))
    if emeta.get("evaluationId")!=eid: raise SystemExit("FAIL evaluation id mismatch")
    if sha(forecast_path)!=emeta.get("forecast",{}).get("forecastIndexSha256"): raise SystemExit("FAIL forecast index hash mismatch")
    forecasts=read_csv(forecast_path); target_games={r["game_id"] for r in forecasts}
    source_manifest,smeta,pbp_asset,pbp_path,sched_path=locate_source(root,a.source_manifest)
    actual,seen_games,source_audit=reconstruct_actuals(root,pbp_path,target_games)
    complete=completed_games_from_schedule(sched_path,target_games)
    if not complete: raise SystemExit("FAIL no completed target games detected in schedules asset; refusing to grade in-progress games")
    complete &= seen_games
    scored=[]; actual_by_name_team={}
    for r in forecasts:
        x=dict(r); gid=r["game_id"]; pid=r["player_id"]
        if gid in complete:
            av=int(actual.get((gid,pid),0)); pred=float(r.get("predicted_xtc") or 0); x["grade_status"]="GRADED"; x["actual_xtc"]=av; x["residual_actual_minus_pred"]=av-pred; x["abs_error"]=abs(av-pred); x["squared_error"]=(av-pred)**2; actual_by_name_team[(canon_name(r.get("player_name")),canon_team(r.get("team")))]=(gid,pid,av)
        else:
            x["grade_status"]="PENDING_GAME"; x["actual_xtc"]=""; x["residual_actual_minus_pred"]=""; x["abs_error"]=""; x["squared_error"]=""
        scored.append(x)
    market_scored=[]; market_path=edir/"OMEGA_0.23_MARKET_COMPARISON.csv"
    if market_path.exists():
        for r in read_csv(market_path):
            x=dict(r); gid=str(r.get("game_id_model") or ""); pid=str(r.get("player_id") or "")
            if gid not in complete: x["grade_status"]="PENDING_GAME"; market_scored.append(x); continue
            av=int(actual.get((gid,pid),0)); line=float(r["line"]); ao=1 if av>line else 0; po=float(r["model_p_over"]); pu=float(r["model_p_under"]); x["grade_status"]="GRADED"; x["actual_xtc"]=av; x["actual_over"]=ao; x["actual_under"]=1-ao; x["brier_over"]=(po-ao)**2; x["brier_under"]=(pu-(1-ao))**2; eps=1e-12; x["logloss_over"]=-(ao*math.log(max(eps,po))+(1-ao)*math.log(max(eps,1-po)))
            if num(r.get("over_price")) is not None: x["over_realized_roi_1u"]=realized_roi("OVER",line,av,float(r["over_price"])); x["over_result"]="WIN" if av>line else "LOSS"
            if num(r.get("under_price")) is not None: x["under_realized_roi_1u"]=realized_roi("UNDER",line,av,float(r["under_price"])); x["under_result"]="WIN" if av<line else "LOSS"
            if num(r.get("one_sided_price")) is not None and str(r.get("one_sided_side") or "").upper() in {"OVER","UNDER"}:
                s=str(r["one_sided_side"]).upper(); pr=float(r["one_sided_price"]); x["one_sided_realized_roi_1u"]=realized_roi(s,line,av,pr); x["one_sided_result"]="WIN" if ((s=="OVER" and av>line) or (s=="UNDER" and av<line)) else "LOSS"
            market_scored.append(x)
    decision_scored=[]; decision_path=edir/"OMEGA_0.23_DECISION_LEDGER.csv"
    if decision_path.exists():
        for r in read_csv(decision_path):
            x=dict(r); key=(canon_name(r.get("player_name")),canon_team(r.get("team"))); hit=actual_by_name_team.get(key)
            if hit is None: x["grade_status"]="PENDING_OR_UNMATCHED"
            else:
                gid,pid,av=hit; line=float(r["line"]); side=str(r["side"]).upper(); price=float(r["price_american"]); x["game_id"]=gid; x["player_id"]=pid; x["grade_status"]="GRADED"; x["actual_xtc"]=av; win=(av>line) if side=="OVER" else (av<line); x["result"]="WIN" if win else "LOSS"; x["realized_roi_1u"]=american_profit(price) if win else -1.0; p=float(r["model_probability"]); y=1 if win else 0; x["brier_score"]=(p-y)**2; x["probability_error_outcome_minus_model"]=y-p
            decision_scored.append(x)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); source_sha=str(pbp_asset.get("sha256") or ""); sid=f"{stamp}_{source_sha[:8]}"; base=root/"data/results/nfl/omega/evaluation_0230"/eid; final=base/sid; staging=base/("."+sid+".staging"); base.mkdir(parents=True,exist_ok=True)
    if final.exists() or staging.exists(): raise SystemExit("FAIL duplicate score run")
    staging.mkdir(parents=True,exist_ok=False)
    try:
        ppath=staging/"OMEGA_0.23_PLAYER_SCORED.csv"; write_csv(ppath,scored); mpath=staging/"OMEGA_0.23_MARKET_SCORED.csv"; write_csv(mpath,market_scored); dpath=staging/"OMEGA_0.23_DECISIONS_SCORED.csv"; write_csv(dpath,decision_scored)
        graded_dec=[r for r in decision_scored if r.get("grade_status")=="GRADED"]; decision_summary={"n":len(graded_dec)}
        if graded_dec:
            rois=[float(r["realized_roi_1u"]) for r in graded_dec]; decision_summary.update({"wins":sum(r.get("result")=="WIN" for r in graded_dec),"losses":sum(r.get("result")=="LOSS" for r in graded_dec),"hitRate":sum(r.get("result")=="WIN" for r in graded_dec)/len(graded_dec),"realizedUnitsAt1uEach":sum(rois),"realizedROI":fmean(rois),"meanExpectedROI":fmean(float(r["expected_roi"]) for r in graded_dec),"meanBrierScore":fmean(float(r["brier_score"]) for r in graded_dec)})
        graded_market=[r for r in market_scored if r.get("grade_status")=="GRADED" and r.get("brier_over") not in ("",None)]; market_summary={"n":len(graded_market)}
        if graded_market: market_summary.update({"meanBrierOver":fmean(float(r["brier_over"]) for r in graded_market),"meanLogLossOver":fmean(float(r["logloss_over"]) for r in graded_market)})
        report={"schemaVersion":SCHEMA,"scoreId":sid,"evaluationId":eid,"scoredAt":now(),"status":"COMPLETE" if complete==target_games else "PARTIAL","integrity":{"omegaModelModified":False,"frozenForecastReadOnly":True,"marketSnapshotReadOnly":True,"modelRefitOn2026Results":False,"oddsPapiPlayerPropRequests":0},"source":{"manifest":str(source_manifest),"snapshotId":smeta.get("snapshotId"),"pbpSha256":source_sha,"completedTargetGames":sorted(complete),"pendingTargetGames":sorted(target_games-complete),**source_audit},"coverage":{"forecastRows":len(scored),"gradedForecastRows":sum(r["grade_status"]=="GRADED" for r in scored),"pendingForecastRows":sum(r["grade_status"]!="GRADED" for r in scored),"marketRows":len(market_scored),"decisionRows":len(decision_scored)},"playerForecastMetrics":player_metrics(scored),"marketProbabilityMetrics":market_summary,"decisionMetrics":decision_summary,"gradingTarget":"standard defensive-scrimmage combined tackle credits reconstructed with OMEGA tackle_events semantics"}
        rpath=staging/"OMEGA_0.23_SCORE_REPORT.json"; rpath.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); hashes={p.name:sha(p) for p in (ppath,mpath,dpath,rpath)}; (staging/"OMEGA_0.23_SCORE_HASHES.json").write_text(json.dumps(hashes,indent=2)+"\n",encoding="utf-8"); os.replace(staging,final); ptr=root/"data/results/nfl/omega/CURRENT_OMEGA_PROSPECTIVE_SCORE"; ptr.parent.mkdir(parents=True,exist_ok=True); tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(f"{eid}/{sid}\n",encoding="utf-8"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise
    print("OMEGA 0.23 — PROSPECTIVE PREDICTION VS REALITY SCORE"); print(f"PASS evaluation {eid}"); print(f"PASS completed games {len(complete)}/{len(target_games)} · status {report['status']}"); pm=report["playerForecastMetrics"]
    if pm.get("n"): print(f"PASS player rows {pm['n']} · MAE {pm['mae']:.3f} · RMSE {pm['rmse']:.3f} · bias {pm['biasPredMinusActual']:+.3f}")
    dm=report["decisionMetrics"]
    if dm.get("n"): print(f"PASS decisions {dm['n']} · W-L {dm['wins']}-{dm['losses']} · units {dm['realizedUnitsAt1uEach']:+.3f} · ROI {dm['realizedROI']:+.1%}")
    print("PASS OMEGA writes 0 · refits 0 · OddsPapi player-prop requests 0"); print(f"REPORT: {final/'OMEGA_0.23_SCORE_REPORT.json'}"); return 0

if __name__=="__main__": raise SystemExit(main())

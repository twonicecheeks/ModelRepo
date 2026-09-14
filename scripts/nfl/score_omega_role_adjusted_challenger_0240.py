#!/usr/bin/env python3
"""Score an immutable OMEGA 0.24 role-adjusted challenger against realized T+A.

Reuses the exact OMEGA 0.23 prospective scoring outcome reconstruction so the target
is identical: standard defensive-scrimmage combined tackle credits. The challenger
and source OMEGA ledger remain read-only; no fitting or tuning occurs here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse, csv, hashlib, importlib.util, json, math, os, shutil

SCHEMA="OMEGA_ROLE_ADJUSTED_CHALLENGER_SCORE_0.24.0"

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(p: Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def rcsv(p: Path):
    with p.open(newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))
def wcsv(p: Path,rows):
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n"); w.writeheader(); w.writerows(rows)
def metrics(rows,pred):
    ys=[float(r["actual_xtc"]) for r in rows]; ps=[float(r[pred]) for r in rows]
    return {"n":len(rows),"actualMean":fmean(ys),"predictedMean":fmean(ps),"mae":fmean(abs(y-p) for y,p in zip(ys,ps)),"rmse":math.sqrt(fmean((y-p)**2 for y,p in zip(ys,ps))),"biasPredMinusActual":fmean(p-y for y,p in zip(ys,ps))}
def load_score_lib(root: Path):
    path=root/"scripts/nfl/score_omega_prospective_eval_0230.py"
    if not path.exists(): raise SystemExit("FAIL OMEGA 0.23 scorer missing")
    spec=importlib.util.spec_from_file_location("omega_score023",path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); ap.add_argument("--challenger-id",default=""); ap.add_argument("--source-manifest",default=""); a=ap.parse_args(); root=Path(a.root).resolve()
    cid=a.challenger_id
    if not cid:
        ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_ROLE_ADJUSTED_CHALLENGER"
        if not ptr.exists(): raise SystemExit("FAIL no current role-adjusted challenger")
        cid=ptr.read_text(encoding="utf-8").strip()
    cdir=root/"data/prospective/nfl/omega_role_adjusted_challenger_0240"/cid
    cp=cdir/"OMEGA_0.24_ROLE_ADJUSTED_CHALLENGER.csv"; mp=cdir/"OMEGA_0.24_ROLE_ADJUSTED_MANIFEST.json"; mh=cdir/"OMEGA_0.24_ROLE_ADJUSTED_MANIFEST.sha256"
    if not cp.exists() or not mp.exists() or not mh.exists(): raise SystemExit("FAIL challenger bundle incomplete")
    if sha(mp)!=mh.read_text(encoding="utf-8").strip(): raise SystemExit("FAIL challenger manifest hash mismatch")
    meta=json.loads(mp.read_text(encoding="utf-8")); rows=rcsv(cp); gid=str(meta.get("gameId") or "")
    if not gid or not rows: raise SystemExit("FAIL challenger game/rows missing")
    if sha(cp)!=meta.get("challengerCsvSha256"): raise SystemExit("FAIL challenger CSV hash mismatch")

    # Verify source OMEGA immutable ledger and get original threshold probabilities.
    lid=str(meta.get("sourceOmegaLedgerId") or ""); lp=root/"data/prospective/nfl/omega/tackle_probability_016"/lid/"OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv"
    if not lp.exists() or sha(lp)!=meta.get("sourceOmegaLedgerSha256"): raise SystemExit("FAIL source OMEGA ledger/hash mismatch")
    original={(r["game_id"],r["player_id"]):r for r in rcsv(lp)}

    lib=load_score_lib(root)
    source_manifest,smeta,pbp_asset,pbp_path,sched_path=lib.locate_source(root,a.source_manifest)
    complete=lib.completed_games_from_schedule(sched_path,{gid})
    if gid not in complete: raise SystemExit(f"FAIL {gid} not marked complete in current schedules asset; refusing live/incomplete grading")
    actual,seen,source_audit=lib.reconstruct_actuals(root,pbp_path,{gid})
    if gid not in seen: raise SystemExit("FAIL completed target game absent from 2026 PBP")

    scored=[]; brier_o=[]; brier_c=[]
    for r in rows:
        key=(r["game_id"],r["player_id"]); base=original.get(key)
        if base is None: raise SystemExit(f"FAIL source OMEGA row missing {key}")
        y=int(actual.get(key,0)); x=dict(r); om=float(r["original_predicted_xtc"]); cm=float(r["corrected_predicted_xtc"])
        x.update({"actual_xtc":y,"original_residual_actual_minus_pred":y-om,"corrected_residual_actual_minus_pred":y-cm,"original_abs_error":abs(y-om),"corrected_abs_error":abs(y-cm),"original_squared_error":(y-om)**2,"corrected_squared_error":(y-cm)**2})
        ob=[]; cb=[]
        for line in [z+0.5 for z in range(15)]:
            tag=str(line).replace(".","_"); outcome=1.0 if y>line else 0.0; po=float(base[f"p_over_{tag}"]); pc=float(r[f"p_over_{tag}"])
            ob.append((po-outcome)**2); cb.append((pc-outcome)**2)
        x["original_threshold_brier_mean"]=fmean(ob); x["corrected_threshold_brier_mean"]=fmean(cb); brier_o.extend(ob); brier_c.extend(cb); scored.append(x)

    orig=metrics(scored,"original_predicted_xtc"); corr=metrics(scored,"corrected_predicted_xtc")
    report={"schemaVersion":SCHEMA,"challengerId":cid,"scoredAt":now(),"gameId":gid,"status":"SCORED_IMMUTABLE","integrity":{"omegaModelModified":False,"challengerModified":False,"modelRefitOnResult":False,"marketFieldsRead":0,"oddsPapiPlayerPropRequests":0},"source":{"nflverseSnapshotId":smeta.get("snapshotId"),"pbpSha256":pbp_asset.get("sha256"),**source_audit},"coverage":{"players":len(scored),"thresholdPredictionsEach":15,"thresholdPredictionsTotal":15*len(scored)},"originalOmegaMetrics":orig,"roleAdjustedMetrics":corr,"improvement":{"mae":orig["mae"]-corr["mae"],"rmse":orig["rmse"]-corr["rmse"],"thresholdBrier":fmean(brier_o)-fmean(brier_c)},"thresholdBrier":{"original":fmean(brier_o),"roleAdjusted":fmean(brier_c)},"interpretationRule":"Positive improvement means role-adjusted challenger performed better on this frozen pregame comparison. This single game is diagnostic only, not sufficient for promotion."}
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); sid=f"{stamp}_{str(pbp_asset.get('sha256') or '')[:8]}"; base=root/"data/results/nfl/omega_role_adjusted_challenger_0240"/cid; final=base/sid; st=base/("."+sid+".staging"); base.mkdir(parents=True,exist_ok=True)
    if final.exists() or st.exists(): raise SystemExit("FAIL duplicate challenger score run")
    st.mkdir(parents=True,exist_ok=False)
    try:
        sp=st/"OMEGA_0.24_ROLE_ADJUSTED_SCORED.csv"; wcsv(sp,scored); rp=st/"OMEGA_0.24_ROLE_ADJUSTED_SCORE_REPORT.json"; rp.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); hashes={sp.name:sha(sp),rp.name:sha(rp)}; (st/"OMEGA_0.24_ROLE_ADJUSTED_SCORE_HASHES.json").write_text(json.dumps(hashes,indent=2)+"\n",encoding="utf-8"); os.replace(st,final)
        ptr=root/"data/results/nfl/omega/CURRENT_OMEGA_ROLE_ADJUSTED_SCORE"; ptr.parent.mkdir(parents=True,exist_ok=True); tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(f"{cid}/{sid}\n",encoding="utf-8"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(st,ignore_errors=True); raise
    print("OMEGA 0.24 — ROLE-ADJUSTED CHALLENGER SCORE")
    print(f"PASS game {gid} · players {len(scored)} · threshold probabilities {15*len(scored)}")
    print(f"ORIGINAL: MAE {orig['mae']:.3f} · RMSE {orig['rmse']:.3f} · Brier {fmean(brier_o):.4f}")
    print(f"ADJUSTED: MAE {corr['mae']:.3f} · RMSE {corr['rmse']:.3f} · Brier {fmean(brier_c):.4f}")
    print(f"IMPROVEMENT: MAE {report['improvement']['mae']:+.3f} · RMSE {report['improvement']['rmse']:+.3f} · Brier {report['improvement']['thresholdBrier']:+.4f}")
    print("PASS refits 0 · market fields read 0 · OMEGA writes 0")
    print(f"REPORT: {final/'OMEGA_0.24_ROLE_ADJUSTED_SCORE_REPORT.json'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

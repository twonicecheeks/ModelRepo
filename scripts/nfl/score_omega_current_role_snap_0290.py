#!/usr/bin/env python3
"""Score frozen OMEGA 0.2.8 DEN-KC current-role snap/count distributions.

Uses the exact OMEGA 0.23 PBP tackle reconstruction for realized T+A.  When an
immutable 2026 nflverse snap-count capture is available, also grades the conditional
snap-share forecast distribution. No fitting, market data, or model mutation occurs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse, csv, hashlib, importlib.util, json, math, os, shutil, sys

SCHEMA="OMEGA_CURRENT_ROLE_SNAP_SCORE_0.29.0"


def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(p: Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def rcsv(p: Path):
    with p.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def wcsv(p: Path,rows):
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields or ["status"],extrasaction="ignore",lineterminator="\n");w.writeheader();w.writerows(rows)
def num(v,d=0.0):
    try:
        if v in (None,""):return d
        x=float(v);return x if math.isfinite(x) else d
    except:return d
def normalize_pct(v):
    if v in (None,""):return None
    try:x=float(v)
    except:return None
    if not math.isfinite(x) or x<0:return None
    if x>1.5:x/=100.0
    return max(0.0,min(1.0,x)) if x<=1.05 else None
def metrics(rows,actual,pred):
    z=[r for r in rows if r.get(actual) not in (None,"") and r.get(pred) not in (None,"")]
    if not z:return {"n":0}
    y=[float(r[actual]) for r in z];p=[float(r[pred]) for r in z]
    return {"n":len(z),"actualMean":fmean(y),"predictedMean":fmean(p),"mae":fmean(abs(a-b) for a,b in zip(y,p)),"rmse":math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),"biasPredMinusActual":fmean(b-a for a,b in zip(y,p))}
def safe_logloss(p,y):
    p=max(1e-12,min(1-1e-12,float(p)));return -(y*math.log(p)+(1-y)*math.log(1-p))
def load_score_lib(root):
    p=root/"scripts/nfl/score_omega_prospective_eval_0230.py";spec=importlib.util.spec_from_file_location("omega_score023_029",p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def resolve_results_manifest(root,arg):
    if arg:return Path(arg).expanduser().resolve()
    ptr=root/"data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST"
    if not ptr.exists():raise SystemExit("FAIL no dedicated 2026 results manifest; refresh results first")
    v=ptr.read_text().strip();return Path(v) if v.startswith("/") else root/v
def resolve_snap_manifest(root,arg):
    if arg:return Path(arg).expanduser().resolve()
    ptr=root/"data/raw/nfl/omega/CURRENT_OMEGA_2026_SNAP_COUNTS"
    if not ptr.exists():return None
    sid=ptr.read_text().strip();return root/"data/raw/nfl/omega/snap_count_results_0290"/sid/"SNAP_COUNTS_RESULTS_MANIFEST.json"
def load_snap_actuals(root,snap_manifest,source_meta,gid):
    if snap_manifest is None or not snap_manifest.exists():return {},{"status":"UNAVAILABLE"}
    import pyarrow.parquet as pq
    sm=json.loads(snap_manifest.read_text()); sp=snap_manifest.parent/"snap_counts_2026.parquet"
    if not sp.exists() or sha(sp)!=sm.get("sha256"):raise SystemExit("FAIL snap-count file/hash mismatch")
    if not sm.get("targetGamePresent") and sm.get("targetGameId")==gid:return {},{"status":"TARGET_GAME_NOT_PRESENT","snapshotId":sm.get("snapshotId")}
    players=next((x for x in source_meta.get("assets",[]) if x.get("source")=="players"),None)
    if not players:raise SystemExit("FAIL results source lacks players identity asset")
    pp=root/str(players.get("blobPath") or "")
    if not pp.exists() or sha(pp)!=players.get("sha256"):raise SystemExit("FAIL players asset/hash mismatch")
    pf=pq.ParquetFile(pp); names=set(pf.schema_arrow.names); pfrcol="pfr_id" if "pfr_id" in names else ("pfr_player_id" if "pfr_player_id" in names else "")
    if not pfrcol or "gsis_id" not in names:raise SystemExit("FAIL players asset lacks GSIS/PFR bridge")
    pmap={str(r.get(pfrcol) or "").strip():str(r.get("gsis_id") or "").strip() for r in pf.read(columns=["gsis_id",pfrcol]).to_pylist() if r.get(pfrcol) and r.get("gsis_id")}
    sf=pq.ParquetFile(sp); cols=["game_id","pfr_player_id","team","defense_snaps","defense_pct"]; rows=sf.read(columns=cols).to_pylist()
    out={}; target=0; bridged=0
    for r in rows:
        if str(r.get("game_id") or "")!=gid:continue
        target+=1; pfr=str(r.get("pfr_player_id") or "").strip(); gsis=pmap.get(pfr,"")
        if not gsis:continue
        bridged+=1; pct=normalize_pct(r.get("defense_pct")); snaps=num(r.get("defense_snaps"),0.0)
        out[gsis]={"actual_snap_share":pct,"actual_defense_snaps":snaps,"pfr_player_id":pfr}
    return out,{"status":"AVAILABLE","snapshotId":sm.get("snapshotId"),"sha256":sm.get("sha256"),"targetRows":target,"bridgedRows":bridged}
def load_role_calibrator(root,artifact_id):
    sys.path[:0]=[str(root/"packages/models/nfl/omega")]
    import current_role_snap_distribution_challenger as cr
    import snap_share_distribution_challenger as sd
    d=root/"data/models/nfl/omega_tackle_027_current_role_snap_distribution"/artifact_id;p=d/"omega_role_distribution_oof.csv"
    if not p.exists():raise SystemExit("FAIL 0.2.7 role distribution OOF artifact missing")
    obs=[]
    for r in rcsv(p):
        c=num(r.get("role_center"));a=num(r.get("actual_snap_share"));obs.append(cr.RoleResidualObservation(row=r,center=c,actual=a,residual=a-c))
    return cr.RoleResidualCalibrator(obs,min_pool=cr.MIN_POOL),cr,sd

def role_row_from_freeze(r):
    rank=int(num(r.get("current_depth_rank")));prev=int(num(r.get("previous_2025_depth_rank")))
    return {"position_group":r.get("position_group",""),"prior_games":r.get("prior_games",0),"week":1,"team":r.get("team",""),"depth_present":1 if rank>0 else 0,"depth_rank":rank,"depth_position":r.get("current_depth_position",""),"prev_depth_rank":prev,"prev_depth_team":r.get("previous_2025_depth_team",""),"prev_depth_present":1 if prev>0 else 0,"promoted_to_rank1":1 if rank==1 and prev>=2 else 0,"demoted_from_rank1":1 if prev==1 and rank>=2 else 0,"rank_improvement":max(0,prev-rank) if rank and prev else 0,"rank_demotion":max(0,rank-prev) if rank and prev else 0,"team_changed":1 if r.get("previous_2025_depth_team") and r.get("previous_2025_depth_team")!=r.get("team") else 0,"last4_snap_share_std":r.get("last4_2025_snap_share_std",0)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL");ap.add_argument("--freeze-id",default="");ap.add_argument("--source-manifest",default="");ap.add_argument("--snap-manifest",default="")
    a=ap.parse_args();root=Path(a.root).expanduser().resolve();fid=a.freeze_id
    if not fid:
        ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_CURRENT_ROLE_SNAP_FREEZE"
        if not ptr.exists():raise SystemExit("FAIL no current 0.2.8 snap freeze")
        fid=ptr.read_text().strip()
    fdir=root/"data/prospective/nfl/omega_current_role_snap_0280"/fid;fp=fdir/"OMEGA_0.2.8_2026_CURRENT_ROLE_SNAP_DISTRIBUTION.csv";mp=fdir/"OMEGA_0.2.8_2026_CURRENT_ROLE_SNAP_MANIFEST.json";hp=fdir/"OMEGA_OUTPUT_HASHES.json"
    for p in (fp,mp,hp):
        if not p.exists():raise SystemExit(f"FAIL 0.2.8 freeze bundle missing {p}")
    hashes=json.loads(hp.read_text());
    if sha(fp)!=hashes.get(fp.name) or sha(mp)!=hashes.get(mp.name):raise SystemExit("FAIL 0.2.8 freeze hash mismatch")
    fm=json.loads(mp.read_text());rows=rcsv(fp);gid=str(fm.get("gameId") or "")
    if not gid or not rows:raise SystemExit("FAIL freeze game/rows missing")
    lib=load_score_lib(root);source_path=resolve_results_manifest(root,a.source_manifest);source_manifest,smeta,pbp_asset,pbp_path,sched_path=lib.locate_source(root,str(source_path))
    if gid not in lib.completed_games_from_schedule(sched_path,{gid}):raise SystemExit(f"FAIL {gid} not complete in results schedules")
    actual,seen,pbp_audit=lib.reconstruct_actuals(root,pbp_path,{gid})
    if gid not in seen:raise SystemExit(f"FAIL {gid} absent from results PBP")
    snap_manifest=resolve_snap_manifest(root,a.snap_manifest);snap_actual,snap_audit=load_snap_actuals(root,snap_manifest,smeta,gid)
    ledger=root/str(fm.get("sourceH012Ledger") or "")
    if not ledger.exists() or sha(ledger)!=fm.get("sourceH012LedgerSha256"):raise SystemExit("FAIL source H012 ledger/hash mismatch")
    orig={(r.get("game_id"),r.get("player_id")):r for r in rcsv(ledger)}
    cal,cr,sd=load_role_calibrator(root,str(fm.get("roleModelArtifactId") or ""))

    scored=[];bo=[];bm=[];ll_o=[];ll_m=[];snap_crps=[];snap_brier=[];pit=[];cov50=[];cov80=[];cov90=[];pool_mismatch=0
    for r in rows:
        pid=r["player_id"];key=(gid,pid);base=orig.get(key)
        if base is None:raise SystemExit(f"FAIL original ledger row missing {key}")
        y=int(actual.get(key,0));x=dict(r);x["actual_xtc"]=y
        for fld in ("original_xtc","role_point_xtc","snap_mixture_xtc_mean"):
            p=num(r.get(fld));x[fld+"_residual_actual_minus_pred"]=y-p;x[fld+"_abs_error"]=abs(y-p)
        ob=[];mb=[]
        for whole in range(15):
            line=whole+.5;tag=str(line).replace(".","_");event=1.0 if y>line else 0.0;po=num(base.get("p_over_"+tag));pmix=num(r.get("mix_p_over_"+tag));ob.append((po-event)**2);mb.append((pmix-event)**2);bo.append((po-event)**2);bm.append((pmix-event)**2);ll_o.append(safe_logloss(po,event));ll_m.append(safe_logloss(pmix,event))
        x["original_threshold_brier_mean"]=fmean(ob);x["mixture_threshold_brier_mean"]=fmean(mb)
        sa=snap_actual.get(pid)
        if sa and sa.get("actual_snap_share") is not None:
            s=float(sa["actual_snap_share"]);sn=float(sa["actual_defense_snaps"]);x.update({"actual_snap_share":s,"actual_defense_snaps":sn,"snap_grade_status":"GRADED_PLAYED" if sn>0 else "NO_DEFENSIVE_SNAP"})
            if sn>0:
                rr=role_row_from_freeze(r);center=num(r.get("role_point_snap_share"));pool,res=cal.select_pool(rr,center);pool_name="|".join(pool)
                if pool_name!=str(r.get("snap_pool_key") or ""):pool_mismatch+=1
                samples=[cr.clip01(center+float(v)) for v in res];c=sd.empirical_crps(samples,s);pv=sd.mid_pit(samples,s);snap_crps.append(c);pit.append(pv)
                probs=[1-num(r.get("p_snap_low")),num(r.get("p_snap_starter"))+num(r.get("p_snap_every_down")),num(r.get("p_snap_every_down"))];events=[1.0 if s>=.35 else 0.0,1.0 if s>=.65 else 0.0,1.0 if s>=.85 else 0.0];sb=fmean((p-e)**2 for p,e in zip(probs,events));snap_brier.append(sb)
                c50=int(num(r.get("snap_q25"))<=s<=num(r.get("snap_q75")));c80=int(num(r.get("snap_q10"))<=s<=num(r.get("snap_q90")));c90=int(num(r.get("snap_q05"))<=s<=num(r.get("snap_q95")));cov50.append(c50);cov80.append(c80);cov90.append(c90);x.update({"snap_distribution_crps":c,"snap_distribution_pit":pv,"snap_threshold_brier_mean":sb,"snap_covered_50":c50,"snap_covered_80":c80,"snap_covered_90":c90,"reconstructed_snap_pool_key":pool_name})
        else:x.update({"actual_snap_share":"","actual_defense_snaps":"","snap_grade_status":"MISSING_SNAP_COUNT"})
        scored.append(x)
    if pool_mismatch:raise SystemExit(f"FAIL frozen snap-pool reconstruction mismatch rows={pool_mismatch}")
    om=metrics(scored,"actual_xtc","original_xtc");rp=metrics(scored,"actual_xtc","role_point_xtc");mm=metrics(scored,"actual_xtc","snap_mixture_xtc_mean")
    played=[r for r in scored if r.get("snap_grade_status")=="GRADED_PLAYED"];hs=metrics(played,"actual_snap_share","h012_snap_share");rs=metrics(played,"actual_snap_share","role_point_snap_share");ds=metrics(played,"actual_snap_share","snap_distribution_mean")
    report={"schemaVersion":SCHEMA,"freezeId":fid,"gameId":gid,"scoredAt":now(),"status":"SCORED_IMMUTABLE","integrity":{"frozenOmegaModified":False,"freezeModified":False,"modelRefitOnResult":False,"marketFieldsRead":0,"oddsPapiRequests":0},"source":{"nflverseSnapshotId":smeta.get("snapshotId"),"pbpSha256":pbp_asset.get("sha256"),**pbp_audit,"snapCounts":snap_audit},"coverage":{"forecastPlayers":len(scored),"tackleThresholdForecasts":15*len(scored),"snapRowsMatched":sum(r.get("snap_grade_status")!="MISSING_SNAP_COUNT" for r in scored),"snapConditionalPlayedRows":len(played),"noDefensiveSnapRows":sum(r.get("snap_grade_status")=="NO_DEFENSIVE_SNAP" for r in scored)},"tackleCount":{"originalH012":om,"rolePoint":rp,"snapMixtureMean":mm,"thresholdBrier":{"original":fmean(bo),"snapMixture":fmean(bm),"improvement":fmean(bo)-fmean(bm)},"thresholdLogLoss":{"original":fmean(ll_o),"snapMixture":fmean(ll_m),"improvement":fmean(ll_o)-fmean(ll_m)}},"snapShareConditionalOnPlaying":{"h012Point":hs,"rolePoint":rs,"distributionMean":ds,"distributionCRPS":fmean(snap_crps) if snap_crps else None,"roleThresholdBrier":fmean(snap_brier) if snap_brier else None,"pitMean":fmean(pit) if pit else None,"intervalCoverage":{"50":fmean(cov50) if cov50 else None,"80":fmean(cov80) if cov80 else None,"90":fmean(cov90) if cov90 else None}},"interpretationRule":"Positive Brier/log-loss improvement means the frozen 0.2.8 snap-mixture probabilities beat original frozen H012 probabilities on this game. Snap-share metrics are conditional on recording at least one defensive snap, matching the 0.2.7 target. Single-game results are diagnostic only."}
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ");sid=f"{stamp}_{str(pbp_asset.get('sha256') or '')[:8]}";baseout=root/"data/results/nfl/omega_current_role_snap_0290"/fid;final=baseout/sid;st=baseout/("."+sid+".staging");baseout.mkdir(parents=True,exist_ok=True)
    if final.exists() or st.exists():raise SystemExit("FAIL duplicate 0.29 score run")
    st.mkdir(parents=True,exist_ok=False)
    try:
        sp=st/"OMEGA_0.29_CURRENT_ROLE_SNAP_SCORED.csv";wcsv(sp,scored);rpfile=st/"OMEGA_0.29_CURRENT_ROLE_SNAP_SCORE_REPORT.json";rpfile.write_text(json.dumps(report,indent=2)+"\n");(st/"OMEGA_0.29_SCORE_HASHES.json").write_text(json.dumps({sp.name:sha(sp),rpfile.name:sha(rpfile)},indent=2)+"\n");os.replace(st,final)
        ptr=root/"data/results/nfl/omega/CURRENT_OMEGA_CURRENT_ROLE_SNAP_SCORE";ptr.parent.mkdir(parents=True,exist_ok=True);tmp=ptr.with_name("."+ptr.name+".tmp");tmp.write_text(f"{fid}/{sid}\n");os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(st,ignore_errors=True);raise
    print("OMEGA 0.29 — CURRENT-ROLE SNAP/COUNT POSTGAME SCORE")
    print(f"PASS game {gid} · players {len(scored)} · tackle thresholds {15*len(scored)}")
    print(f"T+A ORIGINAL H012: MAE {om['mae']:.3f} · RMSE {om['rmse']:.3f} · Brier {fmean(bo):.4f}")
    print(f"T+A SNAP MIXTURE:  MAE {mm['mae']:.3f} · RMSE {mm['rmse']:.3f} · Brier {fmean(bm):.4f}")
    print(f"T+A IMPROVEMENT:   MAE {om['mae']-mm['mae']:+.3f} · RMSE {om['rmse']-mm['rmse']:+.3f} · Brier {fmean(bo)-fmean(bm):+.4f}")
    if played:
        print(f"SNAP SHARE played n {len(played)}: H012 MAE {hs['mae']:.4f} -> role {rs['mae']:.4f} -> dist-mean {ds['mae']:.4f}")
        print(f"SNAP DIST: CRPS {fmean(snap_crps):.4f} · threshold Brier {fmean(snap_brier):.4f} · coverage 50/80/90 {fmean(cov50):.1%}/{fmean(cov80):.1%}/{fmean(cov90):.1%}")
    else:print("SNAP SHARE: current snap-count capture did not provide played target rows; T+A grading still complete")
    print("PASS refits 0 · market fields read 0 · OMEGA writes 0")
    print(f"REPORT: {final/'OMEGA_0.29_CURRENT_ROLE_SNAP_SCORE_REPORT.json'}")
    return 0

if __name__=="__main__":raise SystemExit(main())

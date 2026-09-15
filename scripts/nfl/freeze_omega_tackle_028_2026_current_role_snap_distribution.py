#!/usr/bin/env python3
"""Freeze prospective OMEGA 0.2.8 current-role snap-share distributions for a 2026 game.

Research challenger only. Frozen OMEGA is read-only. This script combines an
already-immutable H012 prospective ledger with a fresh pregame role/depth capture,
the validated OMEGA 0.2.7 role-correction model, and its pre-2024 role-aware
residual calibration. It then propagates the full snap-share distribution through
the frozen NB_ROLE tackle-count family as a mixture.

No sportsbook/market fields and no 2026 outcomes are read. The fitted role model is
never refit here. 2025 snap/depth information is admitted only as strictly-prior
state for a 2026 forecast, never as development or validation data.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, shutil, subprocess, sys, tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_2026_CURRENT_ROLE_SNAP_DISTRIBUTION_PROSPECTIVE_0.2.8"
VERSION = "0.2.8"
DEPTH_2025_URL = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet"
REQ_LEDGER_FIELDS = {"game_id","team","player_id","player_name","position_group","prior_games","predicted_snap_share","predicted_xtc","predicted_xto","distribution_family","p_over_0_5"}


def nowdt() -> datetime:
    return datetime.now(timezone.utc)

def now() -> str:
    return nowdt().isoformat(timespec="seconds").replace("+00:00","Z")

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def rcsv(path: Path) -> list[dict[str,str]]:
    with path.open(newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))

def wcsv(path: Path, rows: Sequence[dict[str,Any]]) -> None:
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n"); w.writeheader(); w.writerows(rows)

def num(v: Any, d: float=0.0) -> float:
    try:
        if v in (None,""): return d
        x=float(v); return x if math.isfinite(x) else d
    except (TypeError,ValueError): return d

def truthy(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1","true","yes","y","t"}

def normteam(v: Any) -> str:
    x=str(v or "").strip().upper()
    return {"JAX":"JAC","LAR":"LA","STL":"LA","SD":"LAC","OAK":"LV"}.get(x,x)

def parse_ts(v: Any) -> datetime:
    x=str(v or "").strip().replace("Z","+00:00")
    d=datetime.fromisoformat(x)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def percentile(xs: Sequence[float], q: float) -> float:
    z=sorted(float(x) for x in xs)
    if not z: return 0.0
    p=max(0.0,min(1.0,float(q)))*(len(z)-1); lo=int(math.floor(p)); hi=int(math.ceil(p))
    if lo==hi: return z[lo]
    w=p-lo; return z[lo]*(1-w)+z[hi]*w

def std0(xs: Sequence[float]) -> float:
    if len(xs)<2: return 0.0
    m=fmean(xs); return math.sqrt(fmean((x-m)**2 for x in xs))


def find_h012_ledger(root: Path, game_id: str) -> tuple[Path,list[dict[str,str]]]:
    """Find the newest immutable OMEGA 0.16-style ledger containing game_id.

    Prefer prospective NFL trees. Validate by required forecast columns rather than
    a brittle filename convention.
    """
    bases=[root/"data/prospective/nfl",root/"data"]
    seen=set(); candidates=[]
    for base in bases:
        if not base.exists(): continue
        pattern="*.csv" if base.name=="data" else "*.csv"
        it=base.rglob(pattern)
        for p in it:
            rp=str(p.resolve())
            if rp in seen: continue
            seen.add(rp)
            # Fallback data-wide scan is limited to OMEGA-named paths.
            if base.name=="data" and "omega" not in rp.lower(): continue
            try:
                with p.open(newline="",encoding="utf-8-sig") as f:
                    dr=csv.DictReader(f); fields=set(dr.fieldnames or [])
                    if not REQ_LEDGER_FIELDS.issubset(fields): continue
                    rows=[]
                    for r in dr:
                        if str(r.get("game_id") or "")==game_id: rows.append(r)
                    if rows: candidates.append((p.stat().st_mtime,p,rows))
            except Exception:
                continue
        if candidates: break
    if not candidates: raise SystemExit(f"FAIL no OMEGA prospective probability ledger found for {game_id}")
    candidates.sort(key=lambda x:(x[0],str(x[1])))
    _,p,rows=candidates[-1]
    if any(str(r.get("distribution_family"))!="NB_ROLE" for r in rows):
        raise SystemExit("FAIL source ledger distribution family drift")
    return p,rows


def load_role_artifact(root: Path, cr):
    ptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_CURRENT_ROLE_SNAP_DISTRIBUTION_CHALLENGER"
    if not ptr.exists(): raise SystemExit(f"FAIL 0.2.7 pointer missing: {ptr}")
    oid=ptr.read_text().strip(); d=root/"data/models/nfl/omega_tackle_027_current_role_snap_distribution"/oid
    mp=d/"omega_current_role_model.json"; op=d/"omega_role_distribution_oof.csv"; ap=d/"OMEGA_0.2.7_CURRENT_ROLE_SNAP_DISTRIBUTION_AUDIT.json"
    for p in (mp,op,ap):
        if not p.exists(): raise SystemExit(f"FAIL 0.2.7 artifact missing: {p}")
    audit=json.loads(ap.read_text())
    if audit.get("verdict")!="H012R_CURRENT_ROLE_DISTRIBUTION_STRONG_PASS":
        raise SystemExit(f"FAIL 0.2.7 not strong-pass: {audit.get('verdict')}")
    integ=audit.get("integrity",{})
    if integ.get("omega2025RowsRead")!=0 or integ.get("depthChart2025RowsRead")!=0 or integ.get("marketFieldsRead")!=0:
        raise SystemExit("FAIL 0.2.7 development integrity drift")
    m=json.loads(mp.read_text())["roleModel"]
    model=cr.RoleCorrectionModel(
        means=[float(x) for x in m["means"]],
        scales=[float(x) for x in m["scales"]],
        intercept=float(m["intercept"]),
        coefficients=[float(x) for x in m["coefficients"]],
        l2=float(m["l2"]),
    )
    obs=[]
    for r in rcsv(op):
        c=num(r.get("role_center")); a=num(r.get("actual_snap_share"))
        obs.append(cr.RoleResidualObservation(row=dict(r),center=c,actual=a,residual=a-c))
    cal=cr.RoleResidualCalibrator(obs,min_pool=cr.MIN_POOL)
    return oid,d,model,cal,audit


def current_role_rows(root: Path, game_id: str):
    ptr=root/"data/raw/nfl/omega/CURRENT_OMEGA_TACKLE_2026_PREGAME_SOURCE"
    if not ptr.exists(): raise SystemExit("FAIL current 2026 pregame-source pointer missing")
    sid=ptr.read_text().strip(); d=root/"data/raw/nfl/omega/prospective_2026_pregame"/sid
    manifest=json.loads((d/"PREGAME_SOURCE_MANIFEST.json").read_text())
    rows=[r for r in rcsv(d/"normalized_pregame_state.csv") if str(r.get("game_id") or "")==game_id]
    if not rows: raise SystemExit(f"FAIL fresh pregame source {sid} has no {game_id}; capture may be post-kickoff")
    if manifest.get("marketFieldsRead",0)!=0 or manifest.get("oddsPapiRequests",0)!=0:
        raise SystemExit("FAIL pregame source market contamination")
    return sid,d,manifest,rows


def download_2025_depth(root: Path) -> tuple[Path,str]:
    """Admit 2025 depth only as strictly-prior 2026 state; never refit 0.2.7."""
    base=root/"data/raw/nfl/omega/prospective_prior_state_2026"
    base.mkdir(parents=True,exist_ok=True)
    # Reuse any previously hash-addressed immutable 2025 asset.
    existing=sorted(base.glob("*/depth_charts_2025.parquet"))
    if existing:
        p=existing[-1]; return p,sha(p)
    curl=shutil.which("curl")
    if not curl: raise SystemExit("FAIL system curl unavailable for 2025 prior-depth admission")
    with tempfile.TemporaryDirectory(prefix="omega_depth25_") as td:
        tmp=Path(td)/"depth_charts_2025.parquet"
        cmd=[curl,"--fail","--location","--silent","--show-error","--connect-timeout","20","--max-time","120","--retry","2","--retry-delay","1","--output",str(tmp),DEPTH_2025_URL]
        r=subprocess.run(cmd,text=True,capture_output=True)
        if r.returncode!=0 or not tmp.exists() or tmp.stat().st_size==0:
            raise SystemExit("FAIL 2025 depth prior download: "+(r.stderr or r.stdout or "empty asset").strip())
        digest=sha(tmp); final=base/digest[:12]; final.mkdir(parents=True,exist_ok=False)
        out=final/"depth_charts_2025.parquet"; shutil.copy2(tmp,out)
        (final/"SOURCE.json").write_text(json.dumps({"purpose":"strictly-prior role state for 2026 prospective forecast only","url":DEPTH_2025_URL,"sha256":digest,"roleModelRefit":False,"development2025RowsRead":0,"capturedAt":now()},indent=2)+"\n")
        return out,digest


def previous_depth_2025(path: Path) -> tuple[dict[str,dict[str,Any]],int]:
    import pyarrow.parquet as pq
    pf=pq.ParquetFile(path); names=set(pf.schema_arrow.names)
    cols=[x for x in ("season","week","game_type","club_code","team","gsis_id","depth_position","depth_team","formation") if x in names]
    best={}; n=0
    for r in pf.read(columns=cols).to_pylist():
        if int(num(r.get("season"),2025))!=2025: continue
        if str(r.get("game_type") or "REG").strip().upper() not in {"REG",""}: continue
        if str(r.get("formation") or "").strip().upper() not in {"DEFENSE","DEF"}: continue
        pid=str(r.get("gsis_id") or "").strip(); team=normteam(r.get("club_code") or r.get("team")); week=int(num(r.get("week"))); rank=int(num(r.get("depth_team")))
        if not pid or not team or week<=0 or rank<=0: continue
        n+=1; z={"week":week,"team":team,"depth_rank":rank,"depth_position":str(r.get("depth_position") or "").strip()}
        old=best.get(pid)
        if old is None or (week,-rank)>(old["week"],-old["depth_rank"]): best[pid]=z
    return best,n


def snap_std_2025(root: Path) -> tuple[dict[str,float],dict[str,int],str|None]:
    """Reconstruct last-4 2025 defensive snap-share volatility for role features."""
    try:
        fptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"; sid=fptr.read_text().strip()
        source_manifest=json.loads((root/"data/raw/nfl/nflverse/snapshots"/sid/"SOURCE_MANIFEST.json").read_text())
        assets={(x.get("source"),x.get("season")):x for x in source_manifest.get("assets",[])}
        pa=assets.get(("players",None));
        if not pa: return {},{},None
        import pyarrow.parquet as pq
        players=pq.ParquetFile(root/pa["blobPath"]).read(columns=[x for x in ("gsis_id","pfr_id") if x in pq.ParquetFile(root/pa["blobPath"]).schema_arrow.names]).to_pylist()
        p2g={str(r.get("pfr_id") or "").strip():str(r.get("gsis_id") or "").strip() for r in players if r.get("pfr_id") and r.get("gsis_id")}
        cand=[]
        base=root/"data/raw/nfl/nflverse/phase2f_holdout/snapshots"
        for mp in base.glob("*/SOURCE_MANIFEST.json"):
            try:
                m=json.loads(mp.read_text()); a=m.get("asset",{}); p=root/a.get("blobPath","")
                if m.get("sourcePhase1SnapshotId")==sid and int(m.get("season") or 0)==2025 and p.exists() and sha(p)==a.get("sha256"): cand.append((str(m.get("createdAt") or ""),p,a.get("sha256")))
            except Exception: pass
        if not cand: return {},{},None
        _,sp,sdigest=sorted(cand)[-1]
        pf=pq.ParquetFile(sp); names=set(pf.schema_arrow.names)
        cols=[x for x in ("game_id","season","game_type","week","pfr_player_id","defense_snaps","defense_pct") if x in names]
        hist=defaultdict(list)
        for r in pf.read(columns=cols).to_pylist():
            if int(num(r.get("season")))!=2025 or str(r.get("game_type") or "REG").upper() not in {"REG",""}: continue
            pfr=str(r.get("pfr_player_id") or "").strip(); pid=p2g.get(pfr,"")
            if not pid or num(r.get("defense_snaps"))<=0: continue
            pct=num(r.get("defense_pct"),-1.0)
            if pct>1.5: pct/=100.0
            if not (0<=pct<=1.05): continue
            hist[pid].append((int(num(r.get("week"))),str(r.get("game_id") or ""),max(0.0,min(1.0,pct))))
        out={}; counts={}
        for pid,z in hist.items():
            vals=[x[2] for x in sorted(z)[-4:]]; out[pid]=std0(vals); counts[pid]=len(z)
        return out,counts,sdigest
    except Exception:
        return {},{},None


def load_nb_params(root: Path):
    sid=(root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN").read_text().strip()
    p=root/"data/models/nfl/omega_tackle_016_probability_frozen"/sid/"OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json"
    j=json.loads(p.read_text())
    if j.get("distributionFamily")!="NB_ROLE": raise SystemExit("FAIL frozen NB_ROLE spec drift")
    return sid,j["distributionParamsFitThrough2024"],p


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); ap.add_argument("--game-id",required=True)
    a=ap.parse_args(); root=Path(a.root).resolve(); game_id=a.game_id
    sys.path.insert(0,str(root/"packages/models/nfl/omega"))
    import current_role_snap_distribution_challenger as cr
    import tackle_count_distribution as dist

    started=nowdt()
    role_oid,role_dir,model,cal,role_audit=load_role_artifact(root,cr)
    source_sid,source_dir,source_manifest,state=current_role_rows(root,game_id)
    ledger_path,ledger=find_h012_ledger(root,game_id)
    lmap={(normteam(r.get("team")),str(r.get("player_id") or "")):r for r in ledger}
    smap={(normteam(r.get("team")),str(r.get("player_id") or "")):r for r in state}
    if not lmap: raise SystemExit("FAIL empty target ledger")
    kickoff_values={str(r.get("kickoff_utc") or "") for r in ledger if r.get("kickoff_utc")}
    if len(kickoff_values)!=1: raise SystemExit(f"FAIL ambiguous kickoff values: {kickoff_values}")
    kickoff=parse_ts(next(iter(kickoff_values)))
    source_capture=parse_ts(source_manifest["capturedAt"])
    if source_capture>=kickoff: raise SystemExit("FAIL current role source captured at/after kickoff; prospective freeze prohibited")

    depth25_path,depth25_sha=download_2025_depth(root); prev25,depth25_rows=previous_depth_2025(depth25_path)
    sstd,snap25_counts,snap25_sha=snap_std_2025(root)
    frozen_sid,nb_params,nb_spec_path=load_nb_params(root)

    outrows=[]; missing_state=[]
    for key,b in sorted(lmap.items(),key=lambda kv:(kv[0][0],-num(kv[1].get("predicted_snap_share")),kv[1].get("player_name",""))):
        team,pid=key; s=smap.get(key)
        if s is None:
            missing_state.append(key); continue
        if str(s.get("roster_status") or "")!="ACTIVE_ROSTER" or str(s.get("game_status") or "") in {"OUT","INACTIVE"} or str(s.get("research_ready") or "")!="TRUE":
            continue
        h=num(b.get("predicted_snap_share")); orig_xtc=num(b.get("predicted_xtc")); rank=int(num(s.get("depth_rank")))
        prev=prev25.get(pid,{})
        row=dict(b)
        row.update({
            "depth_present":1 if rank>0 else 0,
            "depth_rank":rank,
            "depth_position":str(s.get("depth_position") or ""),
            "prev_depth_rank":int(prev.get("depth_rank") or 0),
            "prev_depth_team":str(prev.get("team") or ""),
            "prev_depth_position":str(prev.get("depth_position") or ""),
            "last4_snap_share_std":float(sstd.get(pid,0.0)),
            "current_game_status":str(s.get("game_status") or ""),
            "current_injury_designation":str(s.get("injury_designation") or ""),
            "current_listed_starter":str(s.get("listed_starter") or ""),
            "current_depth_role":str(s.get("depth_role") or ""),
        })
        prev_rank=int(row["prev_depth_rank"]); row["prev_depth_present"]=1 if prev_rank>0 else 0
        row["promoted_to_rank1"]=1 if rank==1 and prev_rank>=2 else 0
        row["demoted_from_rank1"]=1 if prev_rank==1 and rank>=2 else 0
        row["rank_improvement"]=max(0,prev_rank-rank) if rank and prev_rank else 0
        row["rank_demotion"]=max(0,rank-prev_rank) if rank and prev_rank else 0
        center=model.predict(row,h)
        summary=cal.summarize(row,center)
        pool_key,residuals=cal.select_pool(row,center)
        snap_samples=[cr.clip01(center+float(r)) for r in residuals]
        if h>1e-9:
            mu_samples=[orig_xtc*x/h for x in snap_samples]
            point_xtc=orig_xtc*center/h
        else:
            mu_samples=[orig_xtc for _ in snap_samples]; point_xtc=orig_xtc
        mix_mean=fmean(mu_samples) if mu_samples else point_xtc
        trust="ROLE_ALIGNED"
        if rank==1 and h<.65: trust="STARTER_CONFLICT"
        elif rank>=2 and h>=.65: trust="REVIEW_BACKUP_CONFLICT"
        elif rank<=0: trust="NO_DEPTH_FALLBACK_H012"
        z={
            "game_id":game_id,"kickoff_utc":kickoff.astimezone(timezone.utc).isoformat().replace("+00:00","Z"),"team":team,"opponent":b.get("opponent",""),
            "player_id":pid,"player_name":b.get("player_name",""),"position":b.get("position",""),"position_group":b.get("position_group",""),"prior_games":b.get("prior_games",""),
            "h012_snap_share":h,"current_depth_rank":rank,"current_depth_position":row["depth_position"],"previous_2025_depth_rank":prev_rank,"previous_2025_depth_team":row["prev_depth_team"],
            "role_state":trust,"current_listed_starter":row["current_listed_starter"],"current_depth_role":row["current_depth_role"],"current_game_status":row["current_game_status"],"current_injury_designation":row["current_injury_designation"],
            "last4_2025_snap_share_std":row["last4_snap_share_std"],"2025_snap_games_reconstructed":snap25_counts.get(pid,0),
            "role_point_snap_share":center,"role_correction":center-h,"snap_distribution_mean":summary["distribution_mean"],"snap_distribution_median":summary["distribution_median"],
            "snap_q05":summary["q05"],"snap_q10":summary["q10"],"snap_q25":summary["q25"],"snap_q75":summary["q75"],"snap_q90":summary["q90"],"snap_q95":summary["q95"],
            "p_snap_low":summary["p_low"],"p_snap_rotational":summary["p_rotational"],"p_snap_starter":summary["p_starter"],"p_snap_every_down":summary["p_every_down"],"snap_pool_key":summary["pool_key"],"snap_pool_n":summary["pool_n"],
            "original_xtc":orig_xtc,"role_point_xtc":point_xtc,"snap_mixture_xtc_mean":mix_mean,
        }
        # Integrate frozen NB_ROLE count probabilities across exposure uncertainty.
        for line in [x+.5 for x in range(15)]:
            probs=[]
            for ss,mu in zip(snap_samples,mu_samples):
                tier=dist.role_tier(ss)
                probs.append(dist.over_probability(line,max(0.0,mu),"NB_ROLE",nb_params,tier))
            po=fmean(probs) if probs else dist.over_probability(line,max(0.0,point_xtc),"NB_ROLE",nb_params,dist.role_tier(center))
            pu=1.0-po; tag=str(line).replace(".","_")
            z[f"mix_p_over_{tag}"]=po; z[f"mix_p_under_{tag}"]=pu; z[f"mix_fair_over_{tag}"]=dist.fair_american(po); z[f"mix_fair_under_{tag}"]=dist.fair_american(pu)
        outrows.append(z)

    if not outrows: raise SystemExit("FAIL no eligible current-role rows emitted")
    # Fresh role capture must cover most of the original target universe; do not silently grade a partial source.
    coverage=len(outrows)/len(lmap)
    if coverage<0.70: raise SystemExit(f"FAIL current role join/eligibility coverage too low: {coverage:.1%}")

    stamp=started.strftime("%Y%m%dT%H%M%SZ"); seed=f"{game_id}|{source_sid}|{sha(ledger_path)}|{role_oid}".encode(); fid=f"{stamp}_{hashlib.sha256(seed).hexdigest()[:8]}"
    base=root/"data/prospective/nfl/omega_current_role_snap_0280"; final=base/fid; st=base/("."+fid+".staging")
    if final.exists(): raise SystemExit(f"FAIL immutable freeze exists: {final}")
    st.mkdir(parents=True,exist_ok=False)
    try:
        csvp=st/"OMEGA_0.2.8_2026_CURRENT_ROLE_SNAP_DISTRIBUTION.csv"; wcsv(csvp,outrows)
        packaged=nowdt(); manifest={
            "schemaVersion":SCHEMA,"freezeId":fid,"startedAt":started.isoformat().replace("+00:00","Z"),"packagedAt":packaged.isoformat().replace("+00:00","Z"),"gameId":game_id,
            "kickoffUtc":kickoff.astimezone(timezone.utc).isoformat().replace("+00:00","Z"),"sourceRoleCaptureId":source_sid,"sourceRoleCapturedAt":source_manifest["capturedAt"],"sourceRoleManifestSha256":sha(source_dir/"PREGAME_SOURCE_MANIFEST.json"),
            "sourceH012Ledger":str(ledger_path.relative_to(root)),"sourceH012LedgerSha256":sha(ledger_path),"roleModelArtifactId":role_oid,"roleModelAuditVerdict":role_audit.get("verdict"),
            "frozenProbabilitySpec":str(nb_spec_path.relative_to(root)),"frozenProbabilitySourceSnapshot":frozen_sid,"prospective2025DepthSha256":depth25_sha,"prospective2025DepthRowsRead":depth25_rows,"prospective2025SnapAssetSha256":snap25_sha,
            "rows":len(outrows),"sourceH012Rows":len(lmap),"joinEligibilityCoverage":coverage,"missingCurrentRoleStateRows":[{"team":t,"player_id":p} for t,p in missing_state],
            "integrity":{"frozenOmegaModified":False,"roleModelRefit":False,"tackleRateChanged":False,"teamOpportunityChanged":False,"2026OutcomesRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,"development2025RowsRead":0,"prospectivePrior2025StateOnly":True,"roleSourceCapturedBeforeKickoff":source_capture<kickoff,"packagedAfterKickoff":packaged>=kickoff},
            "method":{"snapLocation":"validated 0.2.7 H012 + current-role residual correction","snapUncertainty":"validated 0.2.7 role-aware empirical residual distribution","countPropagation":"mixture of frozen NB_ROLE distributions across empirical snap-share samples","backupConflictPolicy":"prediction retained; downstream betting trust REVIEW only"},
        }
        mp=st/"OMEGA_0.2.8_2026_CURRENT_ROLE_SNAP_MANIFEST.json"; mp.write_text(json.dumps(manifest,indent=2)+"\n")
        hp=st/"OMEGA_OUTPUT_HASHES.json"; hp.write_text(json.dumps({csvp.name:sha(csvp),mp.name:sha(mp)},indent=2)+"\n")
        os.replace(st,final); ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_CURRENT_ROLE_SNAP_FREEZE"; ptr.parent.mkdir(parents=True,exist_ok=True); tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(fid+"\n"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(st,ignore_errors=True); raise

    print("OMEGA 0.2.8 — 2026 CURRENT-ROLE SNAP DISTRIBUTION FREEZE")
    print(f"PASS freeze {fid} · game {game_id} · rows {len(outrows)} · join/eligible coverage {coverage:.1%}")
    print(f"PASS role source {source_sid} captured {source_manifest['capturedAt']} before kickoff {manifest['kickoffUtc']}")
    print(f"PASS H012 ledger SHA {manifest['sourceH012LedgerSha256']} · read-only")
    print(f"PASS role model {role_oid} · refit NO · 2026 outcomes 0 · market fields 0 · OMEGA writes 0")
    print(f"PASS full snap distribution propagated through frozen NB_ROLE mixture")
    print("TOP ROLE SHIFTS:")
    for r in sorted(outrows,key=lambda z:abs(num(z.get("role_correction"))),reverse=True)[:12]:
        print(f"  {r['team']} {r['player_name']}: H012 {100*num(r['h012_snap_share']):.1f}% -> role {100*num(r['role_point_snap_share']):.1f}% · 80% [{100*num(r['snap_q10']):.1f},{100*num(r['snap_q90']):.1f}] · {r['role_state']} · xTC {num(r['original_xtc']):.2f}->{num(r['snap_mixture_xtc_mean']):.2f}")
    print(f"MANIFEST: {final/'OMEGA_0.2.8_2026_CURRENT_ROLE_SNAP_MANIFEST.json'}")
    print(f"CSV: {final/'OMEGA_0.2.8_2026_CURRENT_ROLE_SNAP_DISTRIBUTION.csv'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

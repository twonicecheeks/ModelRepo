#!/usr/bin/env python3
"""Generate immutable 2025 blind predictions from the already frozen Phase 2F spec.

This command may read 2025 nflverse input data, but it does not use 2025 targets for
fitting, model selection, feature selection, hyperparameters, or scoring. One 2025
snap-count asset may be acquired from nflverse; OddsPapi/market requests are 0.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import argparse,csv,hashlib,json,os,shutil,sys,tempfile

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()
def readcsv(p):
    with Path(p).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def writecsv(p,rows):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)
def parquet_rows(path,required,optional=()):
    import pyarrow.parquet as pq
    pf=pq.ParquetFile(path);names=set(pf.schema_arrow.names);missing=[c for c in required if c not in names]
    if missing:raise ValueError(f"{Path(path).name} missing required parquet column(s): {', '.join(missing)}")
    cols=list(required)+[c for c in optional if c in names and c not in required]
    return pf.read(columns=cols).to_pylist(),names

def game_key(row):return int(float(row["season"])),int(float(row["week"])),str(row["game_id"])

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL");a=ap.parse_args();root=Path(a.root).expanduser().resolve()
    sys.path[:0]=[str(root/"packages/models/nfl/game"),str(root/"packages/providers/nflverse/src")]
    import research_model as rm, phase2c_context as pc, phase2c_model as pm, phase2d_hardening as hd, phase2f_holdout as p2f
    import contract,snapshot
    sid=(root/"data/models/nfl/CURRENT_PHASE2F_FROZEN").read_text().strip(); frozen=root/"data/models/nfl/frozen_phase2f"/sid
    spec_path=frozen/"NFL_PHASE2F_FROZEN_SPEC.json"; hash_path=frozen/"NFL_PHASE2F_FROZEN_SPEC.sha256"
    if hash_path.read_text().strip()!=sha(spec_path):raise SystemExit("FAIL frozen spec hash")
    spec=json.loads(spec_path.read_text())
    if spec["safeVariant"]!=p2f.SAFE_VARIANT or float(spec["safeL2"])!=p2f.SAFE_L2 or spec["stageWeights"]!=p2f.STAGE_WEIGHTS:raise SystemExit("FAIL frozen spec/constants drift")
    out=root/"data/models/nfl/phase2f_blind_2025"/sid
    if out.exists():
        pred=out/"PHASE2F_2025_BLIND_PREDICTIONS.csv"; hp=out/"PHASE2F_2025_BLIND_PREDICTIONS.sha256"
        if pred.exists() and hp.exists() and hp.read_text().strip()==sha(pred):
            (root/"data/models/nfl/CURRENT_PHASE2F_BLIND").write_text(sid+"\n");print(f"PASS existing immutable 2025 blind predictions verified: {out}");return 0
        raise SystemExit(f"FAIL existing blind output incomplete: {out}")

    p1=root/"data/normalized/nfl/phase1"/sid; c2=root/"data/normalized/nfl/phase2c_context"/sid; s2=root/"data/normalized/nfl/phase2d_safe_context"/sid
    manifest=snapshot.load_manifest(root/"data/raw/nfl/nflverse/snapshots"/sid/"SOURCE_MANIFEST.json",root=root)
    assets={(x["source"],x.get("season")):x for x in manifest["assets"]}
    games=[r for r in readcsv(p1/"game_identity.csv") if int(r["season"])<=2025]
    base_all=readcsv(p1/"pregame_features.csv"); dev_base=[r for r in base_all if int(r["season"])<=2024]; hold_base=[r for r in base_all if int(r["season"])==2025 and str(r.get("game_type") or "")=="REG"]
    if not hold_base:raise SystemExit("FAIL no 2025 REG pregame feature rows")

    # Acquire/reuse exactly one 2025 snap-count asset, isolated from development.
    src_root=root/"data/raw/nfl/nflverse/phase2f_holdout/snapshots";src_root.mkdir(parents=True,exist_ok=True); hs=None
    for mp in sorted(src_root.glob("*/SOURCE_MANIFEST.json"),reverse=True):
        try:
            d=json.loads(mp.read_text()); aa=d.get("asset",{}); bp=root/aa.get("blobPath","")
            if d.get("sourcePhase1SnapshotId")==sid and int(d.get("season",0))==2025 and bp.exists() and snapshot.sha256_file(bp)==aa.get("sha256"): hs=d; break
        except Exception:pass
    network_requests=0
    if hs is None:
        network_requests=1; ctx_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+sid[-8:]; st=src_root/("."+ctx_id+".staging"); final=src_root/ctx_id; st.mkdir(parents=True,exist_ok=False)
        try:
            url=contract.source_specs()["snap_counts"].url_for_season(2025); fd,name=tempfile.mkstemp(prefix="model_nfl_phase2f_",suffix=".part",dir=str(st));os.close(fd);tmp=Path(name)
            meta=snapshot._download_http(url,tmp);digest=snapshot.sha256_file(tmp);blob=snapshot._store_blob(root,tmp,digest)
            aa={"source":"snap_counts","season":2025,"url":url,"sha256":digest,"bytes":blob.stat().st_size,"blobPath":str(blob.relative_to(root)),"fetchedAt":now(),"etag":meta.get("etag"),"lastModified":meta.get("lastModified"),"contentType":meta.get("contentType")}
            hs={"schemaVersion":"NFL_PHASE2F_HOLDOUT_INPUT_1.0","contextSnapshotId":ctx_id,"sourcePhase1SnapshotId":sid,"createdAt":now(),"season":2025,"purpose":"STRICT_LAG_INPUTS_ONLY","marketDependency":False,"oddsPapiRequests":0,"asset":aa}
            (st/"SOURCE_MANIFEST.json").write_text(json.dumps(hs,indent=2)+"\n");os.replace(st,final)
        except Exception:shutil.rmtree(st,ignore_errors=True);raise

    # Build 2025 observed QB history, then lag it. Current/future games are excluded by target key.
    pbp_req=("game_id","season","week","posteam","qb_dropback","epa","cpoe","sack","yards_gained","interception","passer_player_id");pbp_opt=("qb_epa","passer_player_name","no_play","qb_kneel","play_type")
    rr,names=parquet_rows(root/assets[("play_by_play",2025)]["blobPath"],pbp_req,pbp_opt)
    for r in rr:
        pt=str(r.get("play_type") or "").strip().lower()
        if "no_play" not in names:r["no_play"]=1 if pt=="no_play" else 0
        if "qb_kneel" not in names:r["qb_kneel"]=1 if pt=="qb_kneel" else 0
        if r.get("posteam"):r["posteam"]=contract.normalize_team_abbr(r["posteam"])
    qb_hist=readcsv(c2/"qb_game_history.csv")+pc.extract_observed_qb_game_metrics(rr)

    # Reuse 2015-2024 snap assets, append 2025 holdout input asset.
    dev_snap_manifest=None
    for mp in sorted((root/"data/raw/nfl/nflverse/phase2c_context/snapshots").glob("*/SOURCE_MANIFEST.json"),reverse=True):
        try:
            d=json.loads(mp.read_text())
            if d.get("sourcePhase1SnapshotId")==sid and d.get("holdoutRead") is False:dev_snap_manifest=d;break
        except Exception:pass
    if dev_snap_manifest is None:raise SystemExit("FAIL Phase2C snap manifest missing")
    snap_assets=list(dev_snap_manifest["assets"])+[hs["asset"]];snap_rows=[];cols=("game_id","season","game_type","week","pfr_player_id","position","team","opponent","offense_snaps","defense_snaps")
    for aa in snap_assets:
        sr,_=parquet_rows(root/aa["blobPath"],cols)
        for r in sr:
            if r.get("team"):r["team"]=contract.normalize_team_abbr(r["team"])
            if r.get("opponent"):r["opponent"]=contract.normalize_team_abbr(r["opponent"])
        snap_rows.extend(sr)

    # Use the already tested strict-lag builders with the holdout boundary moved one year forward.
    old=hd.HOLDOUT_SEASON;hd.HOLDOUT_SEASON=2026
    try:
        qbctx=hd.build_strict_lag_qb_context(games,qb_hist); snctx=hd.build_strict_lag_snap_context(games,snap_rows)
    finally:hd.HOLDOUT_SEASON=old
    qmap={r["game_id"]:r for r in qbctx if int(r["season"])==2025}; smap={r["game_id"]:r for r in snctx if int(r["season"])==2025}
    hold=[]
    order={r["game_id"]:game_key(r) for r in games}
    for b in hold_base:
        gid=b["game_id"]; r=dict(b)
        if gid not in qmap or gid not in smap:raise SystemExit(f"FAIL missing strict context for 2025 game {gid}")
        for src in (qmap[gid],smap[gid]):
            for k,v in src.items():
                if k not in {"game_id","season","week","home_team","away_team"}:r[k]=v
        target=order[gid]
        for side in ("home","away"):
            for fld in (f"{side}_lag_continuity_from_game_id",f"{side}_lag_continuity_to_game_id"):
                pg=str(r.get(fld) or "")
                if pg and (pg not in order or not (order[pg] < target)):raise SystemExit(f"FAIL temporal snap provenance {gid} {fld}={pg}")
        hold.append(r)
    hold.sort(key=game_key)

    # Development labels are 2016-2024 only. 2025 is not admitted to fitting.
    labels={}
    with (p1/"game_targets.csv").open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            season=int(str(r["game_id"])[:4])
            if season>2024:continue
            if r.get("home_win") in ("0","0.0","1","1.0"):labels[r["game_id"]]=int(float(r["home_win"]))
    safe_dev=readcsv(s2/"phase2d_safe_features.csv"); ex=rm.examples_from_rows(safe_dev,labels,allowed_seasons=set(p2f.TRAIN_SEASONS),game_type="REG")
    if len(ex)<2000:raise SystemExit(f"FAIL training sample too small: {len(ex)}")
    safe_by={r["game_id"]:r for r in safe_dev};base_names=rm.expanded_feature_names(); all_names=hd.combined_strict_names(base_names,include_qb=True,include_snap=True)
    idx=[i for i,n in enumerate(all_names) if p2f.selected_feature_keep(n)]; names=tuple(all_names[i] for i in idx)
    base_x={e.game_id:tuple(e.x) for e in ex};safe_x={e.game_id:hd.combined_strict_vector(e.x,safe_by[e.game_id],base_names,include_qb=True,include_snap=True) for e in ex}
    model_base=pm.fit_fast_logit([base_x[e.game_id] for e in ex],[e.y for e in ex],base_names,l2=p2f.BASE_L2)
    model_safe=pm.fit_fast_logit([tuple(safe_x[e.game_id][i] for i in idx) for e in ex],[e.y for e in ex],names,l2=p2f.SAFE_L2)

    preds=[]
    for r in hold:
        xb=tuple(rm.vectorize_feature_row(r)); xc=hd.combined_strict_vector(xb,r,base_names,include_qb=True,include_snap=True); xf=tuple(xc[i] for i in idx)
        pb=model_base.predict(xb); ps=model_safe.predict(xf); week=int(r["week"]); pp=p2f.blend_probability(pb,ps,week)
        preds.append({"game_id":r["game_id"],"season":2025,"week":week,"home_team":r["home_team"],"away_team":r["away_team"],"stage":p2f.season_stage(week),"context_weight":p2f.STAGE_WEIGHTS[p2f.season_stage(week)],"p_benchmark":f"{pb:.12f}","p_context_safe":f"{ps:.12f}","p_primary":f"{pp:.12f}"})
    if len(preds)<250:raise SystemExit(f"FAIL expected full 2025 REG slate, got {len(preds)}")
    stage=out.parent/("."+sid+".blind.staging");stage.mkdir(parents=True,exist_ok=False)
    try:
        writecsv(stage/"PHASE2F_2025_BLIND_PREDICTIONS.csv",preds); ph=sha(stage/"PHASE2F_2025_BLIND_PREDICTIONS.csv");(stage/"PHASE2F_2025_BLIND_PREDICTIONS.sha256").write_text(ph+"\n")
        audit={"generatedAt":now(),"sourceSnapshotId":sid,"frozenSpecSha256":sha(spec_path),"holdoutSeason":2025,"predictionRows":len(preds),"trainingSeasons":list(p2f.TRAIN_SEASONS),"trainingGames":len(ex),"holdoutLabelsAdmitted":0,"holdoutScored":False,"marketFieldsAllowed":False,"oddsPapiRequests":0,"nflverseRequests":network_requests,"holdoutSnapAssetSha256":hs["asset"]["sha256"],"strictLagTemporalAudit":"PASS","targetWeekRosterRowsRead":0,"predictionSha256":ph}
        (stage/"PHASE2F_BLIND_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n")
        md=["# MODEL NFL 2.9.0 Phase 2F — 2025 Blind Prediction Audit","","**Predictions are frozen before 2025 labels are scored.**","",f"- Source snapshot: `{sid}`",f"- Prediction rows: **{len(preds)}**",f"- Training games: **{len(ex)}** · seasons 2016–2024 REG only","- 2025 labels admitted to fitting/scoring: **0**","- Target-week roster rows read: **0**","- Strict-lag temporal audit: **PASS**",f"- nflverse requests this run: **{network_requests}** (2025 snap counts only when not cached)","- OddsPapi requests: **0**","- Market fields: **DISALLOWED**",f"- Prediction SHA256: `{ph}`",""]
        (stage/"PHASE2F_BLIND_AUDIT.md").write_text("\n".join(md));os.replace(stage,out);(root/"data/models/nfl/CURRENT_PHASE2F_BLIND").write_text(sid+"\n")
    except Exception:shutil.rmtree(stage,ignore_errors=True);raise
    print("MODEL NFL 2.9.0 PHASE 2F — 2025 BLIND PREDICTIONS")
    print(f"PASS frozen spec verified: {sha(spec_path)}")
    print(f"PASS train 2016-2024 REG only: {len(ex)} games")
    print(f"PASS 2025 blind predictions: {len(preds)}")
    print("PASS 2025 labels scored: NO · market fields DISALLOWED · OddsPapi 0")
    print(f"PASS strict-lag provenance · target-week roster rows 0 · nflverse requests {network_requests}")
    print(f"PREDICTION SHA256: {ph}")
    print(f"AUDIT: {out/'PHASE2F_BLIND_AUDIT.md'}")
    return 0
if __name__=="__main__":raise SystemExit(main())

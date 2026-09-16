#!/usr/bin/env python3
"""Acquire immutable 2026 nflverse snap counts for OMEGA postgame grading.

Evaluation-only utility. It does not fit or mutate any model and does not advance the
generic nflverse snapshot pointer. Data source is the documented nflverse snap_counts
release, captured with verified TLS and hashed before admission.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse, hashlib, json, os, shutil, ssl, urllib.request

URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2026.parquet"
SCHEMA = "OMEGA_2026_SNAP_COUNTS_RESULTS_0.29.0"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def atomic_text(path: Path,text: str):
    path.parent.mkdir(parents=True,exist_ok=True)
    t=path.with_name("."+path.name+".tmp"); t.write_text(text,encoding="utf-8"); os.replace(t,path)


def download(url: str,target: Path):
    import certifi
    ctx=ssl.create_default_context(cafile=certifi.where())
    req=urllib.request.Request(url,headers={"User-Agent":"MODEL-OMEGA/0.29 postgame grading","Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=180,context=ctx) as resp, target.open("wb") as out:
        shutil.copyfileobj(resp,out,length=1024*1024)
        return {"etag":resp.headers.get("ETag"),"lastModified":resp.headers.get("Last-Modified"),"finalUrl":resp.geturl()}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); ap.add_argument("--game-id",default="2026_01_DEN_KC")
    a=ap.parse_args(); root=Path(a.root).expanduser().resolve(); gid=a.game_id.strip()
    import pyarrow.parquet as pq
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base=root/"data/raw/nfl/omega/snap_count_results_0290"; st=base/("."+stamp+".staging"); st.mkdir(parents=True,exist_ok=False)
    try:
        p=st/"snap_counts_2026.parquet"; meta=download(URL,p)
        if not p.exists() or p.stat().st_size<=0: raise RuntimeError("empty snap-count download")
        digest=sha(p); pf=pq.ParquetFile(p); names=set(pf.schema_arrow.names)
        required={"game_id","season","week","pfr_player_id","team","opponent","defense_snaps","defense_pct"}; miss=required-names
        if miss: raise RuntimeError(f"snap-count schema missing {sorted(miss)}")
        table=pq.read_table(p,columns=["game_id","season","week","pfr_player_id","team","opponent","defense_snaps","defense_pct"],filters=[("season","=",2026)])
        rows=table.to_pylist(); target=[r for r in rows if str(r.get("game_id") or "")==gid]
        sid=f"{stamp}_{digest[:8]}"; final=base/sid
        manifest={"schemaVersion":SCHEMA,"snapshotId":sid,"createdAt":now(),"season":2026,"source":"nflverse_snap_counts","url":URL,"finalUrl":meta.get("finalUrl"),"etag":meta.get("etag"),"lastModified":meta.get("lastModified"),"sha256":digest,"bytes":p.stat().st_size,"rows2026":len(rows),"targetGameId":gid,"targetGameRows":len(target),"targetGamePresent":bool(target),"marketFieldsRead":0,"oddsPapiRequests":0,"modelFits":0,"modelWrites":0}
        (st/"SNAP_COUNTS_RESULTS_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        if final.exists(): raise RuntimeError(f"immutable snap-count snapshot exists: {final}")
        os.replace(st,final)
        atomic_text(root/"data/raw/nfl/omega/CURRENT_OMEGA_2026_SNAP_COUNTS",sid+"\n")
    except Exception:
        shutil.rmtree(st,ignore_errors=True); raise
    print("OMEGA 0.29 — ISOLATED 2026 SNAP-COUNT RESULTS CAPTURE")
    print(f"PASS immutable snapshot {sid} · 2026 rows {len(rows)}")
    print(f"TARGET {gid}: rows {len(target)} · present {'YES' if target else 'NO'}")
    print(f"PASS SHA256 {digest} · market fields 0 · model fits/writes 0")
    print(f"MANIFEST: {final/'SNAP_COUNTS_RESULTS_MANIFEST.json'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

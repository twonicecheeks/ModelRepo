#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import uuid

VERSION = "0.7.2"
LINEAGE = "mlb-reg-post-k-assembly-v0.7.2-2026-09-19"

def load_jsonl(path: Path) -> list[dict]:
    rows=[]
    with path.open("r", encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise ValueError(f"{path}:{n}: {exc}") from exc
    return rows

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def resolve(root: Path, pointer_rel: str, leaf: str) -> Path:
    p=root/pointer_rel
    if not p.exists():
        raise FileNotFoundError(p)
    out=root/p.read_text(encoding="utf-8").strip()/leaf
    if not out.exists():
        raise FileNotFoundError(out)
    return out

def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_name("."+path.name+".tmp")
    tmp.write_text(text.rstrip()+"\n", encoding="utf-8")
    os.replace(tmp,path)

def main() -> int:
    ap=argparse.ArgumentParser(description="Assemble REG-vs-POST K xK ledger")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args=ap.parse_args()
    root=Path(args.root).expanduser().resolve()

    post=resolve(root,"data/models/mlb/CURRENT_POSTSEASON_REPLAY_050","MLB_POSTSEASON_HISTORY_PROXY_LEDGER.jsonl")
    reg=resolve(root,"data/models/mlb/CURRENT_REGULAR_CONTROL_K_071","MLB_REGULAR_CONTROL_K_LEDGER.jsonl")

    post_rows=[r for r in load_jsonl(post) if str(r.get("market_type","")).upper()=="K"]
    reg_rows=[r for r in load_jsonl(reg) if str(r.get("market_type","")).upper()=="K"]
    if not post_rows or not reg_rows:
        raise ValueError("both REG and POST K rows are required")
    if any(str(r.get("season_type","")).upper()!="POST" for r in post_rows):
        raise ValueError("postseason ledger contains non-POST K row")
    if any(str(r.get("season_type","")).upper()!="REG" for r in reg_rows):
        raise ValueError("regular control ledger contains non-REG K row")

    rows=reg_rows+post_rows
    rows.sort(key=lambda r:(int(r["season"]),str(r.get("game_date","")),str(r.get("game_id","")),str(r.get("pitcher",""))))

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    out_dir=root/"data/models/mlb/reg_post_k_072"/run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    out=out_dir/"MLB_REG_POST_K_XK_LEDGER.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, separators=(",",":"))+"\n")

    manifest={
        "version":VERSION,
        "lineage":LINEAGE,
        "created_at":datetime.now(timezone.utc).isoformat(),
        "run_id":run_id,
        "regular_ledger":str(reg),
        "regular_sha256":sha256_file(reg),
        "regular_rows":len(reg_rows),
        "postseason_ledger":str(post),
        "postseason_sha256":sha256_file(post),
        "postseason_rows":len(post_rows),
        "combined_rows":len(rows),
        "output":str(out),
        "output_sha256":sha256_file(out),
        "evaluation_mode":"XK_ONLY",
        "historical_k_market":"NOT_ACQUIRED",
        "production_model_mutation":False,
        "model_refit_performed":False,
        "oddsPapi_requests":0,
    }
    mp=out_dir/"REG_POST_K_ASSEMBLY_MANIFEST.json"
    mp.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    atomic_pointer(root/"data/models/mlb/CURRENT_REG_POST_K_072",str(out_dir.relative_to(root)))

    print()
    print(f"MLB REG-vs-POST K ASSEMBLY {VERSION}")
    print(f"REG rows: {len(reg_rows):,} · POST rows: {len(post_rows):,} · combined: {len(rows):,}")
    print("Historical K market: NOT ACQUIRED · OddsPapi: 0")
    print(f"Ledger: {out}")
    print(f"Manifest: {mp}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

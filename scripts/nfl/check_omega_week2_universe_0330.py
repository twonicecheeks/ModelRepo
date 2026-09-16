#!/usr/bin/env python3
"""OMEGA 0.33 fail-closed full Week 2 universe gate.

The legacy pregame capture intentionally emits only future games. For a full Week 2
prospective freeze that behavior must not silently allow a partial slate after the
first Week 2 kickoff. This gate compares the captured target-game IDs with the full
2026 Week 2 REG schedule from the dedicated results snapshot and requires equality.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import json

SEASON = 2026
WEEK = 2


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def rcsv(path: Path):
    with path.open(newline="",encoding="utf-8-sig") as f: return list(csv.DictReader(f))


def parse_ts(v):
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def read_rows(path: Path):
    if path.suffix.lower()==".csv": return rcsv(path)
    if path.suffix.lower()==".parquet":
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    raise SystemExit(f"FAIL unsupported schedule asset: {path}")


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    a=ap.parse_args(); root=Path(a.root).expanduser().resolve()

    sptr=root/"data/raw/nfl/omega/CURRENT_OMEGA_TACKLE_2026_PREGAME_SOURCE"
    if not sptr.exists(): raise SystemExit("FAIL Week 2 pregame-source pointer missing")
    sid=sptr.read_text(encoding="utf-8").strip(); sdir=root/"data/raw/nfl/omega/prospective_2026_pregame"/sid
    mp=sdir/"PREGAME_SOURCE_MANIFEST.json"; gp=sdir/"target_games.csv"
    if not mp.exists() or not gp.exists(): raise SystemExit("FAIL Week 2 pregame source incomplete")
    sm=json.loads(mp.read_text(encoding="utf-8"))
    if int(sm.get("season") or 0)!=SEASON or int(sm.get("targetWeek") or 0)!=WEEK:
        raise SystemExit("FAIL current pregame source is not 2026 Week 2")
    captured=rcsv(gp); captured_ids={str(r.get("game_id") or "") for r in captured if r.get("game_id")}
    if not captured_ids: raise SystemExit("FAIL captured Week 2 game universe empty")

    rptr=root/"data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST"
    if not rptr.exists(): raise SystemExit("FAIL dedicated 2026 results pointer missing")
    rv=rptr.read_text(encoding="utf-8").strip(); rmp=Path(rv) if rv.startswith("/") else root/rv
    if not rmp.exists(): raise SystemExit(f"FAIL results manifest missing: {rmp}")
    rm=json.loads(rmp.read_text(encoding="utf-8")); sched=[x for x in rm.get("assets",[]) if x.get("source")=="schedules"]
    if len(sched)!=1: raise SystemExit(f"FAIL expected one schedules asset; found {len(sched)}")
    sa=sched[0]; sched_path=root/str(sa.get("blobPath") or "")
    if not sched_path.exists() or (sa.get("sha256") and sha(sched_path)!=sa.get("sha256")):
        raise SystemExit("FAIL schedules asset/hash mismatch")
    full=[]
    for r in read_rows(sched_path):
        if int(float(r.get("season") or 0))!=SEASON or int(float(r.get("week") or 0))!=WEEK: continue
        gt=str(r.get("game_type") or r.get("season_type") or "REG").strip().upper()
        if gt not in {"REG",""}: continue
        gid=str(r.get("game_id") or "").strip()
        if gid: full.append(r)
    full_ids={str(r["game_id"]) for r in full}
    if len(full_ids)<10: raise SystemExit(f"FAIL suspicious full Week 2 schedule: {len(full_ids)} games")
    if captured_ids!=full_ids:
        raise SystemExit(f"FAIL Week 2 capture is not the full slate; missing={sorted(full_ids-captured_ids)} extra={sorted(captured_ids-full_ids)}. Do not freeze a partial Week 2 slate.")

    kicks=[parse_ts(r["kickoff_utc"]) for r in captured if r.get("kickoff_utc")]
    if len(kicks)!=len(captured): raise SystemExit("FAIL captured Week 2 kickoff coverage incomplete")
    source_time=parse_ts(sm.get("capturedAt")); earliest=min(kicks)
    if source_time>=earliest: raise SystemExit("FAIL Week 2 source captured at/after earliest kickoff")

    print("OMEGA 0.33 — FULL WEEK 2 UNIVERSE GATE")
    print(f"PASS captured games {len(captured_ids)} == full scheduled REG games {len(full_ids)}")
    print(f"PASS source {sid} captured {sm.get('capturedAt')} before earliest kickoff {earliest.astimezone(timezone.utc).isoformat().replace('+00:00','Z')}")
    print("PASS partial-slate freeze prohibited")
    return 0


if __name__=="__main__": raise SystemExit(main())

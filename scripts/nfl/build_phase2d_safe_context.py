#!/usr/bin/env python3
"""Build strict-lag Phase 2D QB/snap context from already downloaded data; network 0."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import argparse, csv, json, os, shutil, sys


def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
def readcsv(path):
    with Path(path).open(newline="", encoding="utf-8") as f: return list(csv.DictReader(f))
def writecsv(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=fields, lineterminator="\n"); w.writeheader()
        for r in rows: w.writerow({k:"" if r.get(k) is None else r.get(k) for k in fields})

def parquet_rows(path, required):
    import pyarrow.parquet as pq
    pf=pq.ParquetFile(path); names=set(pf.schema_arrow.names); missing=[c for c in required if c not in names]
    if missing: raise ValueError(f"{Path(path).name} missing required parquet column(s): {', '.join(missing)}")
    return pf.read(columns=list(required)).to_pylist()


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL"); a=ap.parse_args()
    root=Path(a.root).expanduser().resolve(); sys.path.insert(0, str(root/"packages/models/nfl/game")); sys.path.insert(0, str(root/"packages/providers/nflverse/src"))
    import phase2d_hardening as hd
    import contract

    p1ptr=root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"; cptr=root/"data/normalized/nfl/CURRENT_PHASE2C_CONTEXT"
    if not p1ptr.exists() or not cptr.exists(): raise SystemExit("FAIL Phase1/Phase2C pointers missing")
    sid=p1ptr.read_text().strip()
    if cptr.read_text().strip()!=sid: raise SystemExit("FAIL Phase2C context snapshot mismatch")

    # Crash-safe/idempotent recovery: if the immutable safe-context directory already
    # exists, verify its integrity and restore the CURRENT pointer instead of refusing
    # to overwrite. This handles interruption after os.replace(out) but before pointer write.
    out=root/"data/normalized/nfl/phase2d_safe_context"/sid
    if out.exists():
        audit_path=out/"PHASE2D_SAFE_CONTEXT_AUDIT.json"
        features_path=out/"phase2d_safe_features.csv"
        if not audit_path.exists() or not features_path.exists() or features_path.stat().st_size<=0:
            raise SystemExit(f"FAIL existing immutable Phase2D safe context is incomplete: {out}")
        audit=json.loads(audit_path.read_text())
        checks=(
            audit.get("sourceSnapshotId")==sid,
            int(audit.get("holdoutRowsRead",-1))==0,
            int(audit.get("targetWeekRosterRowsRead",-1))==0,
            audit.get("marketFieldsAllowed") is False,
            int(audit.get("oddsPapiRequests",-1))==0,
            audit.get("sourceTimingGate")=="RESOLVED_FOR_STRICT_LAG_CHALLENGER_ONLY",
        )
        if not all(checks):
            raise SystemExit(f"FAIL existing immutable Phase2D safe context failed recovery audit: {out}")
        ptr=root/"data/normalized/nfl/CURRENT_PHASE2D_SAFE_CONTEXT"
        tmp=ptr.with_name(".CURRENT_PHASE2D_SAFE_CONTEXT.tmp")
        tmp.write_text(sid+"\n"); os.replace(tmp,ptr)
        print("MODEL NFL 2.9.0 PHASE 2D.2 — STRICT-LAG CONTEXT RECOVERY")
        print(f"PASS verified immutable safe context: {out}")
        print("PASS restored CURRENT_PHASE2D_SAFE_CONTEXT pointer")
        print("PASS target-week roster rows read: 0 · 2025 holdout rows read: 0 · network 0")
        print(f"REPORT: {out/'PHASE2D_SAFE_CONTEXT_AUDIT.md'}")
        return 0

    p1=root/"data/normalized/nfl/phase1"/sid; cdir=root/"data/normalized/nfl/phase2c_context"/sid
    base=[r for r in readcsv(p1/"pregame_features.csv") if int(r["season"])<=2024]
    games=[r for r in readcsv(p1/"game_identity.csv") if int(r["season"])<=2024]
    qb_hist=readcsv(cdir/"qb_game_history.csv")
    if any(int(float(r["season"]))>=2025 for r in qb_hist):
        # Phase2C history may physically contain 2025 only if contract is broken; fail closed.
        raise SystemExit("FAIL 2025 QB history present in Phase2C context")

    # Reuse immutable Phase2C supplemental snap files. No network fallback is allowed.
    ctx_root=root/"data/raw/nfl/nflverse/phase2c_context/snapshots"; manifest=None
    for mp in sorted(ctx_root.glob("*/SOURCE_MANIFEST.json"), reverse=True):
        try:
            d=json.loads(mp.read_text())
            if d.get("sourcePhase1SnapshotId")==sid and d.get("holdoutRead") is False:
                manifest=d; break
        except Exception: pass
    if manifest is None: raise SystemExit("FAIL no reusable Phase2C snap-count manifest; Phase2D never downloads")
    snap_rows=[]
    cols=("game_id","season","game_type","week","pfr_player_id","position","team","opponent","offense_snaps","defense_snaps")
    for asset in manifest.get("assets",[]):
        if int(asset.get("season", 9999))>=2025: raise SystemExit("FAIL Phase2D supplemental manifest contains holdout snap asset")
        path=root/asset["blobPath"]
        if not path.exists(): raise SystemExit(f"FAIL missing existing snap blob: {path}")
        for r in parquet_rows(path, cols):
            if r.get("team"): r["team"]=contract.normalize_team_abbr(r["team"])
            if r.get("opponent"): r["opponent"]=contract.normalize_team_abbr(r["opponent"])
            snap_rows.append(r)

    qb=hd.build_strict_lag_qb_context(games, qb_hist)
    sc=hd.build_strict_lag_snap_context(games, snap_rows)
    qmap={r["game_id"]:r for r in qb}; smap={r["game_id"]:r for r in sc}
    merged=[]
    for b in base:
        if int(b["season"])>=2025: continue
        r=dict(b); gid=r["game_id"]
        for src in (qmap.get(gid,{}), smap.get(gid,{})):
            for k,v in src.items():
                if k not in {"game_id","season","week","home_team","away_team"}: r[k]=v
        merged.append(r)
    merged.sort(key=lambda r:(int(r["season"]),int(r["week"]),r["game_id"]))
    if not merged or any(int(r["season"])>=2025 for r in merged): raise SystemExit("FAIL strict-lag context holdout boundary")

    side_cells=2*len(merged)
    qb_resolved=sum(1 for r in merged for s in ("home","away") if r.get(f"{s}_lag_qb_gsis_id"))
    stems=hd.STRICT_SNAP_STEMS; cov={}
    for stem in stems:
        vals=[r.get(f"{s}_{stem}") for r in merged for s in ("home","away")]
        good=sum(v not in (None,"") for v in vals); cov[stem]={"nonMissing":good,"cells":len(vals),"nonMissingPct":100*good/len(vals) if vals else None}
    w1=[r for r in merged if int(r["week"])==1]
    audit={
        "generatedAt":now(),"sourceSnapshotId":sid,"sourcePhase2CSnapSnapshotId":manifest.get("contextSnapshotId"),
        "developmentRows":len(merged),"holdoutRowsRead":0,"marketFieldsAllowed":False,"oddsPapiRequests":0,
        "targetWeekRosterRowsRead":0,"strictLagRule":"QB=previous observed primary only; continuity=G-2 to G-1 snap retention",
        "qbResolvedSides":qb_resolved,"sideCells":side_cells,"qbResolvedPct":100*qb_resolved/side_cells if side_cells else None,
        "snapCoverage":cov,"week1Rows":len(w1),"sourceTimingGate":"RESOLVED_FOR_STRICT_LAG_CHALLENGER_ONLY"
    }
    st=out.parent/("."+sid+".staging"); st.mkdir(parents=True, exist_ok=False)
    try:
        writecsv(st/"strict_lag_qb_context.csv", qb); writecsv(st/"strict_lag_snap_context.csv", sc); writecsv(st/"phase2d_safe_features.csv", merged)
        (st/"PHASE2D_SAFE_CONTEXT_AUDIT.json").write_text(json.dumps(audit, indent=2)+"\n")
        md=["# MODEL NFL 2.9.0 Phase 2D — Strict-Lag Context Audit","","**2025 HOLDOUT REMAINS SEALED. NOT PRODUCTION.**","",
            f"- Source Phase1 snapshot: `{sid}`",f"- Reused Phase2C snap snapshot: `{manifest.get('contextSnapshotId')}`",f"- Development rows: **{len(merged)}**",
            "- 2025 rows read: **0**","- Target-week roster rows read: **0**","- Sportsbook/market fields: **DISALLOWED**","- OddsPapi requests: **0**","",
            "## Temporal-safety rule","","- QB identity is the previous observed primary QB from a strictly earlier game only.","- No target-week roster is consulted to infer a replacement QB.","- Snap continuity for target game G is measured from G-2 to G-1 only.","- Target-game snaps and target-week roster membership are never used.","- This intentionally sacrifices current availability information to create a provenance-safe challenger.","",
            "## Coverage","",f"- Strict-lag QB available: **{qb_resolved}/{side_cells} ({audit['qbResolvedPct']:.3f}%)**"]
        for stem,v in cov.items(): md.append(f"- `{stem}`: {v['nonMissingPct']:.3f}% ({v['nonMissing']}/{v['cells']})")
        md += ["",f"- Week 1 rows: **{len(w1)}**","",f"Source timing verdict: **{audit['sourceTimingGate']}**",""]
        (st/"PHASE2D_SAFE_CONTEXT_AUDIT.md").write_text("\n".join(md))
        os.replace(st,out); (root/"data/normalized/nfl/CURRENT_PHASE2D_SAFE_CONTEXT").write_text(sid+"\n")
    except Exception:
        shutil.rmtree(st, ignore_errors=True); raise
    print("MODEL NFL 2.9.0 PHASE 2D.2 — STRICT-LAG CONTEXT")
    print(f"PASS Phase1 snapshot: {sid}")
    print("PASS reuse existing snap-count blobs · network 0")
    print("PASS target-week roster rows read: 0")
    print("PASS 2025 holdout rows read: 0")
    print(f"PASS strict-lag QB available: {qb_resolved}/{side_cells}")
    print(f"REPORT: {out/'PHASE2D_SAFE_CONTEXT_AUDIT.md'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

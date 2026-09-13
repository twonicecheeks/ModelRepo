#!/usr/bin/env python3
"""OMEGA 0.23 — freeze an immutable prospective evaluation bundle.

This is downstream evaluation infrastructure only. It never changes OMEGA model
coefficients, features, probabilities, or frozen artifacts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse, csv, hashlib, json, os, shutil

SCHEMA = "OMEGA_PROSPECTIVE_EVALUATION_FREEZE_0.23.0"
LINEAGE = "omega-prospective-evaluation-v0.23.0"
FORECAST_FIELDS = [
    "game_id","season","week","gameday","kickoff_utc","team","opponent",
    "player_id","player_name","position","position_group","prior_games",
    "predicted_xto","predicted_snap_share","predicted_xtc",
    "distribution_family","distribution_role_tier","distribution_size",
    "research_ready","verified_ready","verified_block_reason",
]
DECISION_REQUIRED = [
    "decision_rank","player_name","team","side","line","book","price_american",
    "model_probability","model_fair_price","expected_roi","decision_status",
]
FORBIDDEN_DECISION_FIELDS = {"actual_xtc","result","realized_roi","settlement_result"}

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def sha(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""):
            h.update(b)
    return h.hexdigest()

def read_csv(path: Path):
    with path.open(newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, rows, fields):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k:r.get(k,"") for k in fields})

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--decision-csv",default="")
    ap.add_argument("--note",default="")
    a=ap.parse_args()
    root=Path(a.root).resolve()

    lp=root/"data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER"
    if not lp.exists():
        raise SystemExit("FAIL no current OMEGA probability ledger pointer")
    lid=lp.read_text(encoding="utf-8").strip()
    ldir=root/"data/prospective/nfl/omega/tackle_probability_016"/lid
    ledger=ldir/"OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv"
    sidecar=ldir/"OMEGA_2026_PROSPECTIVE_PROBABILITIES.sha256"
    audit=ldir/"OMEGA_0.16_PROSPECTIVE_AUDIT.json"
    for p in (ledger,sidecar,audit):
        if not p.exists():
            raise SystemExit(f"FAIL probability artifact missing: {p}")
    ledger_sha=sha(ledger)
    if sidecar.read_text(encoding="utf-8").strip()!=ledger_sha:
        raise SystemExit("FAIL OMEGA probability ledger hash mismatch")

    forecast_rows=read_csv(ledger)
    if not forecast_rows:
        raise SystemExit("FAIL probability ledger empty")
    keys=set()
    for r in forecast_rows:
        k=(r.get("game_id",""),r.get("player_id",""))
        if not k[0] or not k[1] or k in keys:
            raise SystemExit(f"FAIL duplicate/blank forecast key {k}")
        keys.add(k)

    market_snapshot_id=""
    market_manifest_sha=""
    market_rows_sha=""
    mp=root/"data/raw/nfl/omega/CURRENT_MARKET_SNAPSHOT"
    market_dir=None
    if mp.exists():
        market_snapshot_id=mp.read_text(encoding="utf-8").strip()
        market_dir=root/"data/raw/nfl/omega/market_snapshots"/market_snapshot_id
        mm=market_dir/"MARKET_SNAPSHOT_MANIFEST.json"
        mr=market_dir/"normalized_market_rows.csv"
        if mm.exists() and mr.exists():
            market_manifest_sha=sha(mm)
            market_rows_sha=sha(mr)
        else:
            raise SystemExit("FAIL current market snapshot incomplete")

    comparison_id=""
    comparison_sha=""
    comparison_path=None
    cp=root/"data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_MARKET_COMPARISON"
    if cp.exists():
        comparison_id=cp.read_text(encoding="utf-8").strip()
        cdir=root/"data/prospective/nfl/omega/market_comparison_0180"/comparison_id
        comparison_path=cdir/"OMEGA_0.18.0_MARKET_COMPARISON.csv"
        ca=cdir/"OMEGA_0.18.0_MARKET_COMPARISON_AUDIT.json"
        if comparison_path.exists() and ca.exists():
            meta=json.loads(ca.read_text(encoding="utf-8"))
            if meta.get("omegaLedgerSha256")!=ledger_sha:
                comparison_path=None
                comparison_id=""
            else:
                comparison_sha=sha(comparison_path)

    decision_path=Path(a.decision_csv).expanduser().resolve() if a.decision_csv else None
    decision_rows=[]
    if decision_path:
        if not decision_path.exists():
            raise SystemExit(f"FAIL decision CSV missing: {decision_path}")
        decision_rows=read_csv(decision_path)
        if not decision_rows:
            raise SystemExit("FAIL decision CSV empty")
        cols=set(decision_rows[0].keys())
        missing=[x for x in DECISION_REQUIRED if x not in cols]
        if missing:
            raise SystemExit("FAIL decision CSV missing fields: "+", ".join(missing))
        bad=sorted(FORBIDDEN_DECISION_FIELDS & {c.lower() for c in cols})
        if bad:
            raise SystemExit("FAIL outcome fields forbidden at freeze: "+", ".join(bad))
        for i,r in enumerate(decision_rows,1):
            if str(r.get("side","")).upper() not in {"OVER","UNDER"}:
                raise SystemExit(f"FAIL decision row {i} side must be OVER/UNDER")
            try:
                float(r.get("line","")); float(r.get("price_american","")); float(r.get("model_probability",""))
            except Exception:
                raise SystemExit(f"FAIL decision row {i} numeric field invalid")
            if not (0 < float(r["model_probability"]) < 1):
                raise SystemExit(f"FAIL decision row {i} model_probability outside (0,1)")

    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sid=f"{stamp}_{ledger_sha[:8]}"
    base=root/"data/prospective/nfl/omega/evaluation_0230"
    final=base/sid
    staging=base/("."+sid+".staging")
    base.mkdir(parents=True,exist_ok=True)
    if final.exists() or staging.exists():
        raise SystemExit("FAIL evaluation bundle already exists")
    staging.mkdir(parents=True,exist_ok=False)
    try:
        compact=[]
        for r in forecast_rows:
            compact.append({k:r.get(k,"") for k in FORECAST_FIELDS})
        fp=staging/"OMEGA_0.23_FORECAST_INDEX.csv"
        write_csv(fp,compact,FORECAST_FIELDS)
        fp_sha=sha(fp)

        shutil.copy2(audit,staging/"OMEGA_0.16_PROSPECTIVE_AUDIT.json")
        audit_sha=sha(staging/"OMEGA_0.16_PROSPECTIVE_AUDIT.json")

        if market_dir:
            shutil.copy2(market_dir/"normalized_market_rows.csv",staging/"OMEGA_0.23_MARKET_SNAPSHOT.csv")
            shutil.copy2(market_dir/"MARKET_SNAPSHOT_MANIFEST.json",staging/"OMEGA_0.23_MARKET_SNAPSHOT_MANIFEST.json")
        if comparison_path:
            shutil.copy2(comparison_path,staging/"OMEGA_0.23_MARKET_COMPARISON.csv")

        decisions_sha=""
        if decision_path:
            dst=staging/"OMEGA_0.23_DECISION_LEDGER.csv"
            shutil.copy2(decision_path,dst)
            decisions_sha=sha(dst)

        manifest={
            "schemaVersion":SCHEMA,
            "lineage":LINEAGE,
            "evaluationId":sid,
            "frozenAt":now(),
            "status":"PREGAME_FORECAST_FROZEN",
            "note":a.note,
            "integrity":{
                "omegaModelModified":False,
                "omegaProbabilityLedgerReadOnly":True,
                "outcomesReadAtFreeze":False,
                "marketEnteredModel":False,
                "oddsPapiPlayerPropRequests":0,
            },
            "forecast":{
                "sourceLedgerId":lid,
                "sourceLedgerSha256":ledger_sha,
                "forecastIndexSha256":fp_sha,
                "prospectiveAuditSha256":audit_sha,
                "rows":len(compact),
                "games":len({r.get("game_id","") for r in compact}),
            },
            "market":{
                "snapshotId":market_snapshot_id,
                "marketRowsSha256":market_rows_sha,
                "marketManifestSha256":market_manifest_sha,
                "comparisonId":comparison_id,
                "comparisonSha256":comparison_sha,
            },
            "decisions":{
                "rows":len(decision_rows),
                "sha256":decisions_sha,
                "present":bool(decision_rows),
            },
            "gradingTarget":"standard defensive-scrimmage combined tackle credits reconstructed from nflverse PBP using frozen OMEGA tackle_events semantics",
        }
        (staging/"OMEGA_0.23_EVALUATION_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        manifest_sha=sha(staging/"OMEGA_0.23_EVALUATION_MANIFEST.json")
        (staging/"OMEGA_0.23_EVALUATION_MANIFEST.sha256").write_text(manifest_sha+"\n",encoding="utf-8")
        os.replace(staging,final)
        ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_PROSPECTIVE_EVALUATION"
        tmp=ptr.with_name("."+ptr.name+".tmp")
        tmp.write_text(sid+"\n",encoding="utf-8")
        os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise

    print("OMEGA 0.23 — PROSPECTIVE EVALUATION FREEZE")
    print(f"PASS evaluation {sid}")
    print(f"PASS forecasts {len(compact)} · games {manifest['forecast']['games']}")
    print(f"PASS model ledger {ledger_sha} · read-only")
    print(f"PASS market snapshot {market_snapshot_id or 'NONE'}")
    print(f"PASS compatible 0.18 comparison {comparison_id or 'NONE'}")
    print(f"PASS decisions frozen {len(decision_rows)}")
    print("PASS outcomes read 0 · OMEGA model writes 0 · OddsPapi player-prop requests 0")
    print(f"MANIFEST: {final/'OMEGA_0.23_EVALUATION_MANIFEST.json'}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

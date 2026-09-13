#!/usr/bin/env python3
"""OMEGA 0.23 — freeze an immutable prospective evaluation bundle.

Downstream evaluation infrastructure only. It never changes OMEGA model
coefficients, features, probabilities, or frozen artifacts. The bundle preserves
both the full model probability ledger and a compact forecast index, plus the raw
market snapshot, compatible downstream market comparison, and optional explicit
pre-result decision ledger.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse, csv, hashlib, json, math, os, shutil

SCHEMA = "OMEGA_PROSPECTIVE_EVALUATION_FREEZE_0.23.1"
LINEAGE = "omega-prospective-evaluation-v0.23.1"
FORECAST_FIELDS = [
    "captured_at","pregame_source_snapshot","game_id","season","week","kickoff_utc",
    "team","opponent","player_id","player_name","position","position_group","prior_games",
    "predicted_xto","predicted_snap_share","availability_authority","game_status",
    "injury_designation","listed_starter","depth_role","verified_ready","verified_block_reason",
    "predicted_xtc","distribution_family","distribution_role_tier","distribution_size",
]
DECISION_REQUIRED = [
    "decision_rank","game_id","player_id","player_name","team","opponent","side","line",
    "book","price_american","market_captured_at","model_probability","model_fair_price",
    "expected_roi","decision_status",
]
FORBIDDEN_DECISION_FIELDS = {"actual_xtc","result","realized_roi","settlement_result","outcome"}

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

def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def tag(line: float) -> str:
    return str(float(line)).replace(".","_")

def american_profit(price: float) -> float:
    return price/100.0 if price > 0 else 100.0/abs(price)

def expected_roi(prob: float, price: float) -> float:
    return prob*american_profit(price) - (1.0-prob)

def parse_ts(s: str):
    s=str(s or "").strip()
    if not s: return None
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00"))
    except Exception:
        return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--decision-csv",default="")
    ap.add_argument("--game-id",action="append",default=[],help="Restrict this evaluation bundle to one or more model game_id values")
    ap.add_argument("--note",default="")
    a=ap.parse_args()
    root=Path(a.root).resolve()

    lp=root/"data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER"
    if not lp.exists(): raise SystemExit("FAIL no current OMEGA probability ledger pointer")
    lid=lp.read_text(encoding="utf-8").strip()
    ldir=root/"data/prospective/nfl/omega/tackle_probability_016"/lid
    ledger=ldir/"OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv"
    sidecar=ldir/"OMEGA_2026_PROSPECTIVE_PROBABILITIES.sha256"
    audit=ldir/"OMEGA_0.16_PROSPECTIVE_AUDIT.json"
    for p in (ledger,sidecar,audit):
        if not p.exists(): raise SystemExit(f"FAIL probability artifact missing: {p}")
    ledger_sha=sha(ledger)
    if sidecar.read_text(encoding="utf-8").strip()!=ledger_sha:
        raise SystemExit("FAIL OMEGA probability ledger hash mismatch")

    source_forecast_rows=read_csv(ledger)
    if not source_forecast_rows: raise SystemExit("FAIL probability ledger empty")
    requested_games=set(a.game_id or [])
    available_games={str(r.get("game_id") or "") for r in source_forecast_rows}
    unknown=sorted(requested_games-available_games)
    if unknown: raise SystemExit("FAIL requested game_id not in current OMEGA ledger: "+", ".join(unknown))
    forecast_rows=[r for r in source_forecast_rows if not requested_games or str(r.get("game_id") or "") in requested_games]
    if not forecast_rows: raise SystemExit("FAIL scoped forecast row set is empty")
    keys=set(); by_key={}
    for r in forecast_rows:
        k=(r.get("game_id",""),r.get("player_id",""))
        if not k[0] or not k[1] or k in keys: raise SystemExit(f"FAIL duplicate/blank forecast key {k}")
        keys.add(k); by_key[k]=r

    market_snapshot_id=""; market_manifest_sha=""; market_rows_sha=""; market_dir=None
    mp=root/"data/raw/nfl/omega/CURRENT_MARKET_SNAPSHOT"
    if mp.exists():
        market_snapshot_id=mp.read_text(encoding="utf-8").strip()
        market_dir=root/"data/raw/nfl/omega/market_snapshots"/market_snapshot_id
        mm=market_dir/"MARKET_SNAPSHOT_MANIFEST.json"; mr=market_dir/"normalized_market_rows.csv"
        if not mm.exists() or not mr.exists(): raise SystemExit("FAIL current market snapshot incomplete")
        market_manifest_sha=sha(mm); market_rows_sha=sha(mr)

    comparison_id=""; comparison_sha=""; comparison_path=None; comparison_rows=[]
    cp=root/"data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_MARKET_COMPARISON"
    if cp.exists():
        candidate_id=cp.read_text(encoding="utf-8").strip()
        cdir=root/"data/prospective/nfl/omega/market_comparison_0180"/candidate_id
        cpath=cdir/"OMEGA_0.18.0_MARKET_COMPARISON.csv"; ca=cdir/"OMEGA_0.18.0_MARKET_COMPARISON_AUDIT.json"
        if cpath.exists() and ca.exists():
            meta=json.loads(ca.read_text(encoding="utf-8"))
            if meta.get("omegaLedgerSha256")==ledger_sha and (not market_snapshot_id or meta.get("marketSnapshotId")==market_snapshot_id):
                comparison_id=candidate_id; comparison_path=cpath; comparison_sha=sha(cpath); comparison_rows=[r for r in read_csv(cpath) if not requested_games or str(r.get("game_id_model") or "") in requested_games]

    decision_path=Path(a.decision_csv).expanduser().resolve() if a.decision_csv else None
    decision_rows=[]
    if decision_path:
        if not decision_path.exists(): raise SystemExit(f"FAIL decision CSV missing: {decision_path}")
        decision_rows=read_csv(decision_path)
        if not decision_rows: raise SystemExit("FAIL decision CSV empty")
        cols=set(decision_rows[0].keys())
        missing=[x for x in DECISION_REQUIRED if x not in cols]
        if missing: raise SystemExit("FAIL decision CSV missing fields: "+", ".join(missing))
        bad=sorted(FORBIDDEN_DECISION_FIELDS & {c.lower() for c in cols})
        if bad: raise SystemExit("FAIL outcome fields forbidden at freeze: "+", ".join(bad))
        if not comparison_rows:
            raise SystemExit("FAIL decisions require a compatible current OMEGA 0.18 comparison; run compare_omega_tackle_market_0180.py first")
        ranks=set()
        for i,r in enumerate(decision_rows,1):
            try: rank=int(r.get("decision_rank",""))
            except Exception: raise SystemExit(f"FAIL decision row {i} invalid decision_rank")
            if rank<=0 or rank in ranks: raise SystemExit(f"FAIL decision row {i} duplicate/nonpositive decision_rank")
            ranks.add(rank)
            side=str(r.get("side","")).upper()
            if side not in {"OVER","UNDER"}: raise SystemExit(f"FAIL decision row {i} side must be OVER/UNDER")
            line=num(r.get("line")); price=num(r.get("price_american")); prob=num(r.get("model_probability")); fair=num(r.get("model_fair_price")); ev=num(r.get("expected_roi"))
            if None in (line,price,prob,fair,ev): raise SystemExit(f"FAIL decision row {i} numeric field invalid")
            if not (0 < prob < 1): raise SystemExit(f"FAIL decision row {i} model_probability outside (0,1)")
            key=(str(r.get("game_id") or ""),str(r.get("player_id") or ""))
            fr=by_key.get(key)
            if fr is None: raise SystemExit(f"FAIL decision row {i} game/player key not in frozen forecast: {key}")
            if str(fr.get("player_name"))!=str(r.get("player_name")) or str(fr.get("team"))!=str(r.get("team")):
                raise SystemExit(f"FAIL decision row {i} player/team identity drift")
            t=tag(line); pfield=f"p_{side.lower()}_{t}"; ffield=f"fair_{side.lower()}_{t}"
            mpv=num(fr.get(pfield)); mfv=num(fr.get(ffield))
            if mpv is None or mfv is None: raise SystemExit(f"FAIL decision row {i} model threshold {line} unavailable")
            if abs(mpv-prob)>1e-9 or abs(mfv-fair)>1e-6:
                raise SystemExit(f"FAIL decision row {i} model probability/fair price drift from frozen ledger")
            calc_ev=expected_roi(prob,price)
            if abs(calc_ev-ev)>1e-6: raise SystemExit(f"FAIL decision row {i} expected ROI arithmetic drift")
            matches=[]
            for cr in comparison_rows:
                if str(cr.get("game_id_model"))!=key[0] or str(cr.get("player_id"))!=key[1]: continue
                if str(cr.get("book"))!=str(r.get("book")): continue
                if abs((num(cr.get("line")) or -999)-line)>1e-9: continue
                cprice=num(cr.get("over_price" if side=="OVER" else "under_price"))
                cprob=num(cr.get("model_p_over" if side=="OVER" else "model_p_under"))
                if cprice is not None and cprob is not None and abs(cprice-price)<1e-9 and abs(cprob-prob)<1e-9:
                    matches.append(cr)
            if len(matches)!=1: raise SystemExit(f"FAIL decision row {i} does not map uniquely to compatible OMEGA 0.18 market comparison")
            if str(matches[0].get("market_captured_at"))!=str(r.get("market_captured_at")):
                raise SystemExit(f"FAIL decision row {i} market capture timestamp drift")

    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); sid=f"{stamp}_{ledger_sha[:8]}"
    base=root/"data/prospective/nfl/omega/evaluation_0230"; final=base/sid; staging=base/("."+sid+".staging"); base.mkdir(parents=True,exist_ok=True)
    if final.exists() or staging.exists(): raise SystemExit("FAIL evaluation bundle already exists")
    staging.mkdir(parents=True,exist_ok=False)
    try:
        compact=[{k:r.get(k,"") for k in FORECAST_FIELDS} for r in forecast_rows]
        fp=staging/"OMEGA_0.23_FORECAST_INDEX.csv"; write_csv(fp,compact,FORECAST_FIELDS); fp_sha=sha(fp)
        fullp=staging/"OMEGA_0.23_FORECAST_FULL.csv"; write_csv(fullp,forecast_rows,list(source_forecast_rows[0].keys())); full_sha=sha(fullp)
        shutil.copy2(audit,staging/"OMEGA_0.16_PROSPECTIVE_AUDIT.json"); audit_sha=sha(staging/"OMEGA_0.16_PROSPECTIVE_AUDIT.json")
        if market_dir:
            shutil.copy2(market_dir/"normalized_market_rows.csv",staging/"OMEGA_0.23_MARKET_SNAPSHOT.csv")
            shutil.copy2(market_dir/"MARKET_SNAPSHOT_MANIFEST.json",staging/"OMEGA_0.23_MARKET_SNAPSHOT_MANIFEST.json")
        if comparison_path:
            write_csv(staging/"OMEGA_0.23_MARKET_COMPARISON.csv",comparison_rows,list(read_csv(comparison_path)[0].keys()) if read_csv(comparison_path) else ["game_id_model"])
        decisions_sha=""
        if decision_path:
            dst=staging/"OMEGA_0.23_DECISION_LEDGER.csv"; shutil.copy2(decision_path,dst); decisions_sha=sha(dst)

        f_times=[parse_ts(r.get("captured_at")) for r in forecast_rows]; f_times=[x for x in f_times if x]
        m_times=[]
        if market_dir:
            m_times=[parse_ts(r.get("captured_at")) for r in read_csv(market_dir/"normalized_market_rows.csv")]; m_times=[x for x in m_times if x]
        kickoff_times=[parse_ts(r.get("kickoff_utc")) for r in forecast_rows]; kickoff_times=[x for x in kickoff_times if x]
        packaged=datetime.now(timezone.utc)
        manifest={
            "schemaVersion":SCHEMA,"lineage":LINEAGE,"evaluationId":sid,"packagedAt":packaged.isoformat(timespec="seconds").replace("+00:00","Z"),
            "status":"IMMUTABLE_PREGAME_INPUTS_PACKAGED","note":a.note,
            "integrity":{"omegaModelModified":False,"omegaProbabilityLedgerReadOnly":True,"outcomesReadAtPackaging":False,"marketEnteredModel":False,"oddsPapiPlayerPropRequests":0,"packagedAfterSomeKickoffs":bool(kickoff_times and packaged>min(kickoff_times))},
            "sourceTiming":{"forecastCapturedMin":min(f_times).isoformat().replace("+00:00","Z") if f_times else "","forecastCapturedMax":max(f_times).isoformat().replace("+00:00","Z") if f_times else "","marketCapturedMin":min(m_times).isoformat().replace("+00:00","Z") if m_times else "","marketCapturedMax":max(m_times).isoformat().replace("+00:00","Z") if m_times else "","earliestKickoff":min(kickoff_times).isoformat().replace("+00:00","Z") if kickoff_times else ""},
            "scope":{"gameIds":sorted({r.get("game_id","") for r in compact}),"explicitGameScope":bool(requested_games)},
            "forecast":{"sourceLedgerId":lid,"sourceLedgerSha256":ledger_sha,"forecastIndexSha256":fp_sha,"forecastFullSha256":full_sha,"prospectiveAuditSha256":audit_sha,"rows":len(compact),"games":len({r.get("game_id","") for r in compact})},
            "market":{"snapshotId":market_snapshot_id,"marketRowsSha256":market_rows_sha,"marketManifestSha256":market_manifest_sha,"comparisonId":comparison_id,"comparisonSha256":comparison_sha},
            "decisions":{"rows":len(decision_rows),"sha256":decisions_sha,"present":bool(decision_rows),"validatedAgainstComparison":bool(decision_rows)},
            "gradingTarget":"standard defensive-scrimmage combined tackle credits reconstructed from nflverse PBP using frozen OMEGA tackle_events semantics",
        }
        mpth=staging/"OMEGA_0.23_EVALUATION_MANIFEST.json"; mpth.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        manifest_sha=sha(mpth); (staging/"OMEGA_0.23_EVALUATION_MANIFEST.sha256").write_text(manifest_sha+"\n",encoding="utf-8")
        os.replace(staging,final)
        ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_PROSPECTIVE_EVALUATION"; tmp=ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(sid+"\n",encoding="utf-8"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

    print("OMEGA 0.23.1 — PROSPECTIVE EVALUATION FREEZE")
    print(f"PASS evaluation {sid}")
    print(f"PASS forecasts {len(compact)} · games {manifest['forecast']['games']} · full probability curve preserved")
    print(f"PASS model ledger {ledger_sha} · read-only")
    print(f"PASS market snapshot {market_snapshot_id or 'NONE'}")
    print(f"PASS compatible 0.18 comparison {comparison_id or 'NONE'}")
    print(f"PASS decisions frozen {len(decision_rows)} · stable game/player IDs")
    print(f"PASS source forecast capture {manifest['sourceTiming']['forecastCapturedMax'] or 'UNKNOWN'} · market capture {manifest['sourceTiming']['marketCapturedMax'] or 'UNKNOWN'}")
    print("PASS outcomes read 0 · OMEGA model writes 0 · OddsPapi player-prop requests 0")
    print(f"MANIFEST: {final/'OMEGA_0.23_EVALUATION_MANIFEST.json'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

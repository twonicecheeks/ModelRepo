#!/usr/bin/env python3
"""Create an immutable explicit OMEGA test-portfolio decision input from a 0.18 comparison.

Selection syntax: --selection 'Player Name|OVER|4.5|DraftKings'
The tool never chooses bets. It only records explicitly supplied selections using the
already-frozen model probability and executable market price from the current 0.18
comparison, before outcomes are read by the evaluation scorer.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import argparse, csv, hashlib, json, os, shutil

SCHEMA="OMEGA_DECISION_INPUT_0.23.0"
FIELDS=[
 "decision_rank","game_id","player_id","player_name","team","opponent","side","line",
 "book","price_american","market_captured_at","model_probability","model_fair_price",
 "expected_roi","decision_status","comparison_id","settlement_policy_status",
 "settlement_resolved","verified_ready","actionability","actionability_blockers",
]

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(p:Path):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()
def read_csv(p):
 with p.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def norm(s): return " ".join(str(s or "").strip().casefold().split())
def num(v):
 try:return float(v)
 except:return None

def parse_selection(s):
 parts=[x.strip() for x in s.split("|")]
 if len(parts)!=4: raise ValueError("selection must be Player Name|OVER|line|Book")
 name,side,line,book=parts; side=side.upper()
 if side not in {"OVER","UNDER"}: raise ValueError("side must be OVER or UNDER")
 try: line=float(line)
 except: raise ValueError("line must be numeric")
 return name,side,line,book

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
 ap.add_argument("--selection",action="append",required=True,help="Player Name|OVER|4.5|Book")
 ap.add_argument("--status",default="MODEL_TEST_PORTFOLIO_RESEARCH_ONLY")
 a=ap.parse_args(); root=Path(a.root).resolve()
 ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_MARKET_COMPARISON"
 if not ptr.exists(): raise SystemExit("FAIL no current OMEGA 0.18 market comparison")
 cid=ptr.read_text().strip(); cdir=root/"data/prospective/nfl/omega/market_comparison_0180"/cid
 cp=cdir/"OMEGA_0.18.0_MARKET_COMPARISON.csv"; ca=cdir/"OMEGA_0.18.0_MARKET_COMPARISON_AUDIT.json"
 if not cp.exists() or not ca.exists(): raise SystemExit("FAIL current OMEGA 0.18 comparison incomplete")
 audit=json.loads(ca.read_text(encoding="utf-8")); rows=read_csv(cp)
 if not rows: raise SystemExit("FAIL OMEGA 0.18 comparison empty")
 out=[]
 for rank,spec in enumerate(a.selection,1):
  try:name,side,line,book=parse_selection(spec)
  except ValueError as e: raise SystemExit(f"FAIL selection {rank}: {e}")
  cand=[r for r in rows if norm(r.get("player_name"))==norm(name) and norm(r.get("book"))==norm(book) and num(r.get("line")) is not None and abs(num(r.get("line"))-line)<1e-9]
  if len(cand)!=1: raise SystemExit(f"FAIL selection {rank} {name} {side} {line} {book}: expected 1 comparison row, found {len(cand)}")
  r=cand[0]
  price=num(r.get("over_price" if side=="OVER" else "under_price")); prob=num(r.get("model_p_over" if side=="OVER" else "model_p_under")); fair=num(r.get("model_fair_over" if side=="OVER" else "model_fair_under")); ev=num(r.get("over_roi" if side=="OVER" else "under_roi"))
  if None in (price,prob,fair,ev): raise SystemExit(f"FAIL selection {rank}: executable {side} price/model fields unavailable")
  out.append({
   "decision_rank":rank,"game_id":r.get("game_id_model"),"player_id":r.get("player_id"),
   "player_name":r.get("player_name"),"team":r.get("team"),"opponent":r.get("opponent"),
   "side":side,"line":f"{line:.1f}","book":r.get("book"),"price_american":price,
   "market_captured_at":r.get("market_captured_at"),"model_probability":prob,
   "model_fair_price":fair,"expected_roi":ev,"decision_status":a.status,
   "comparison_id":cid,"settlement_policy_status":r.get("settlement_policy_status"),
   "settlement_resolved":r.get("settlement_resolved"),"verified_ready":r.get("verified_ready"),
   "actionability":r.get("actionability"),"actionability_blockers":r.get("actionability_blockers"),
  })
 stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
 sid=f"{stamp}_{sha(cp)[:8]}"; base=root/"data/prospective/nfl/omega/decision_inputs_0230"; final=base/sid; st=base/("."+sid+".staging"); base.mkdir(parents=True,exist_ok=True)
 if final.exists() or st.exists(): raise SystemExit("FAIL duplicate decision input id")
 st.mkdir(parents=True,exist_ok=False)
 try:
  dp=st/"OMEGA_0.23_DECISIONS_INPUT.csv"
  with dp.open("w",newline="",encoding="utf-8") as f:
   w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator="\n"); w.writeheader(); w.writerows(out)
  meta={"schemaVersion":SCHEMA,"decisionInputId":sid,"createdAt":now(),"comparisonId":cid,"comparisonSha256":sha(cp),"omegaLedgerSha256":audit.get("omegaLedgerSha256"),"marketSnapshotId":audit.get("marketSnapshotId"),"rows":len(out),"selectionRule":"explicit user/model-test portfolio only; this tool performs no ranking or bet selection","outcomesRead":False,"omegaModelModified":False}
  (st/"OMEGA_0.23_DECISIONS_INPUT_AUDIT.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf-8")
  os.replace(st,final)
  p=root/"data/prospective/nfl/omega/CURRENT_OMEGA_DECISION_INPUT"; tmp=p.with_name("."+p.name+".tmp"); tmp.write_text(sid+"\n",encoding="utf-8"); os.replace(tmp,p)
 except Exception:
  shutil.rmtree(st,ignore_errors=True); raise
 print("OMEGA 0.23 — EXPLICIT DECISION PORTFOLIO")
 print(f"PASS decision input {sid} · selections {len(out)}")
 for r in out:
  print(f"  {r['decision_rank']}. {r['player_name']} {r['side']} {r['line']} @ {r['price_american']:+g} {r['book']} · p {float(r['model_probability']):.1%} · EV {float(r['expected_roi']):+.1%}")
 print("PASS stable game/player IDs · exact 0.18 prices · outcomes read 0 · model writes 0")
 print(f"DECISION_CSV: {final/'OMEGA_0.23_DECISIONS_INPUT.csv'}")
 return 0
if __name__=="__main__": raise SystemExit(main())

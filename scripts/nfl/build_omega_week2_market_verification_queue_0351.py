#!/usr/bin/env python3
"""OMEGA 0.35.1 — mixed executable/reference Week 2 verification queue.

Read-only downstream triage over immutable OMEGA 0.34.1 comparison.

0.35.0 intentionally required an all-reference-only PropsMadness board. The current
0.17.11 adapter can emit a mixed board containing:
- EXECUTABLE_OFFER rows from named downstream books/platforms, and
- REFERENCE_ONLY_NON_EXECUTABLE noOffer/referenceBet rows.

0.35.1 preserves that distinction rather than weakening 0.35.0.

Policy:
- frozen OMEGA CONTROL remains the decision probability track;
- role-point probability remains SHADOW_ONLY_NOT_PROMOTED;
- all PropsMadness prices still require direct verification at the named venue;
- traditional sportsbook rows are eligible for PRIMARY_DIRECT_BOOK_VERIFY only when
  role-aligned, CONTROL/ROLE agree on side, and CONTROL EV is positive;
- reference-only rows are never primary executable candidates;
- alternative/fantasy platforms are segregated from sportsbook candidates;
- backup conflicts remain quarantined;
- starter conflicts remain review-only;
- no model fit/write and no market mutation occurs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse,csv,hashlib,json,math,os,shutil

SCHEMA="OMEGA_WEEK2_MIXED_MARKET_VERIFICATION_QUEUE_0.35.1"
VERSION="0.35.1"
ALLOWED_QUOTES={"EXECUTABLE_OFFER","REFERENCE_ONLY_NON_EXECUTABLE"}
TRADITIONAL_BOOKS={"DraftKings","FanDuel","Caesars","BetMGM","Hard Rock","Hard Rock Bet","Fanatics","bet365","Pinnacle","Circa Sports"}
ALTERNATIVE_PLATFORMS={"Underdog Fantasy","Props Builder"}

def nowdt(): return datetime.now(timezone.utc)
def now(): return nowdt().isoformat(timespec="seconds").replace("+00:00","Z")

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def rcsv(path:Path):
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))

def wcsv(path:Path,rows:list[dict[str,Any]],fields:list[str]|None=None):
    if fields is None:
        fields=[]
        for r in rows:
            for k in r:
                if k not in fields:fields.append(k)
    if not fields:fields=["status"]
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        w.writeheader()
        for r in rows:w.writerow({k:"" if r.get(k) is None else r.get(k) for k in fields})

def atomic_text(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name("."+path.name+".tmp");tmp.write_text(text,encoding="utf-8");os.replace(tmp,path)

def num(v):
    try:
        if v in (None,""):return None
        x=float(v);return x if math.isfinite(x) else None
    except:return None

def fair_american(p):
    if p is None or not (0<p<1):return None
    return -100*p/(1-p) if p>=.5 else 100*(1-p)/p

def comparison_bundle(root:Path):
    ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_MARKET_COMPARISON"
    if not ptr.exists():raise SystemExit("FAIL current Week 2 market comparison pointer missing")
    cid=ptr.read_text().strip()
    dirs=[
      root/"data/prospective/nfl/omega_week2_market_comparison_0341"/cid,
      root/"data/prospective/nfl/omega_week2_market_comparison_0340"/cid,
    ]
    d=next((x for x in dirs if x.exists()),None)
    if d is None:raise SystemExit(f"FAIL comparison bundle not found: {cid}")
    cp=next((x for x in [d/"OMEGA_0.34.1_WEEK2_MARKET_COMPARISON.csv",d/"OMEGA_0.34_WEEK2_MARKET_COMPARISON.csv"] if x.exists()),None)
    ap=next((x for x in [d/"OMEGA_0.34.1_WEEK2_MARKET_COMPARISON_AUDIT.json",d/"OMEGA_0.34_WEEK2_MARKET_COMPARISON_AUDIT.json"] if x.exists()),None)
    hp=d/"OMEGA_OUTPUT_HASHES.json"
    if cp is None or ap is None or not hp.exists():raise SystemExit(f"FAIL incomplete comparison bundle: {d}")
    hm=json.loads(hp.read_text());expected=str(hm.get(cp.name) or "")
    if not expected or sha(cp)!=expected:raise SystemExit("FAIL comparison CSV hash mismatch")
    audit=json.loads(ap.read_text())
    if audit.get("decisionProbabilityTrack")!="FROZEN_OMEGA_CONTROL":raise SystemExit("FAIL unexpected decision probability track")
    if audit.get("roleProbabilityStatus")!="SHADOW_ONLY_NOT_PROMOTED":raise SystemExit("FAIL role probability is not shadow-only")
    return cid,d,cp,audit

def price_for_side(r,side):
    if side=="OVER":
        x=num(r.get("over_odds_american"))
        if x is not None:return x
    if side=="UNDER":
        x=num(r.get("under_odds_american"))
        if x is not None:return x
    if str(r.get("one_sided_side") or "").upper()==side:return num(r.get("one_sided_odds_american"))
    return None

def prob_for_side(r,prefix,side):return num(r.get(f"{prefix}p_{side.lower()}"))
def ev_for_side(r,prefix,side):return num(r.get(f"{prefix}{side.lower()}_ev"))

def venue_class(book:str)->str:
    if book in TRADITIONAL_BOOKS:return "TRADITIONAL_SPORTSBOOK"
    if book in ALTERNATIVE_PLATFORMS:return "ALTERNATIVE_OR_FANTASY_PLATFORM"
    return "UNCLASSIFIED_VENUE"

def queue_class(r:dict[str,str])->str:
    quote=str(r.get("market_quote_classification") or "")
    book=str(r.get("book") or "")
    venue=venue_class(book)
    role=str(r.get("role_state") or "")
    agree=str(r.get("tracks_agree_side") or "").upper()=="TRUE"
    ev=num(r.get("control_best_ev"))
    if ev is None or ev<=0:return "NONPOSITIVE_CONTROL_EV"
    if role=="REVIEW_BACKUP_CONFLICT":return "BACKUP_CONFLICT_QUARANTINE"
    if role=="STARTER_CONFLICT_REVIEW":return "STARTER_CONFLICT_REVIEW"
    if role=="NO_DEPTH_FALLBACK_H012":return "NO_DEPTH_REVIEW"
    if quote=="REFERENCE_ONLY_NON_EXECUTABLE":
        return "REFERENCE_ONLY_WATCH" if role=="ROLE_ALIGNED" and agree else "REFERENCE_ONLY_REVIEW"
    if quote!="EXECUTABLE_OFFER":return "UNKNOWN_QUOTE_CLASS_REVIEW"
    if venue!="TRADITIONAL_SPORTSBOOK":
        return "ALTERNATIVE_PLATFORM_REVIEW" if venue=="ALTERNATIVE_OR_FANTASY_PLATFORM" else "UNCLASSIFIED_VENUE_REVIEW"
    if role=="ROLE_ALIGNED" and agree:return "PRIMARY_DIRECT_BOOK_VERIFY"
    if role=="ROLE_ALIGNED" and not agree:return "TRACK_DISAGREEMENT_REVIEW"
    return "OTHER_REVIEW"

def best_primary_per_player(rows):
    best={}
    for r in rows:
        if r["queue_class"]!="PRIMARY_DIRECT_BOOK_VERIFY":continue
        ev=num(r.get("control_ev_at_quote"))
        if ev is None:continue
        key=(str(r.get("game_id") or ""),str(r.get("player_name") or ""),str(r.get("side") or ""))
        old=best.get(key)
        if old is None or ev>num(old.get("control_ev_at_quote")):
            best[key]=r
    return sorted(best.values(),key=lambda r:-(num(r.get("control_ev_at_quote")) or -999))

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--data-root",default="")
    args=ap.parse_args();root=Path(args.root).expanduser().resolve()
    data_root=Path(args.data_root).expanduser().resolve() if args.data_root else root
    cid,cdir,cp,caudit=comparison_bundle(data_root)
    rows=rcsv(cp)
    if not rows:raise SystemExit("FAIL comparison CSV empty")
    classes={str(r.get("market_quote_classification") or "") for r in rows}
    bad=classes-ALLOWED_QUOTES
    if bad:raise SystemExit(f"FAIL unsupported market quote classifications: {sorted(bad)}")
    if "EXECUTABLE_OFFER" not in classes:
        raise SystemExit("FAIL 0.35.1 mixed queue requires at least one EXECUTABLE_OFFER; use 0.35.0 for all-reference boards")

    enriched=[]
    for r in rows:
        side=str(r.get("control_best_side") or "").strip().upper()
        if side not in {"OVER","UNDER"}:continue
        cpv=prob_for_side(r,"control_",side)
        rpv=prob_for_side(r,"role_shadow_",side)
        cev=ev_for_side(r,"control_",side)
        rev=ev_for_side(r,"role_shadow_",side)
        price=price_for_side(r,side)
        q=queue_class(r)
        book=str(r.get("book") or "")
        enriched.append({
          "queue_class":q,
          "game_id":r.get("game_id"),"kickoff_utc":r.get("kickoff_utc"),
          "player_name":r.get("player_name"),"team":r.get("team"),"opponent":r.get("opponent"),
          "position_group":r.get("position_group"),"role_state":r.get("role_state"),
          "tracks_agree_side":r.get("tracks_agree_side"),
          "side":side,"line":r.get("line"),"book":book,"venue_class":venue_class(book),
          "quote_price":price,"quote_captured_at":r.get("market_captured_at"),
          "market_quote_classification":r.get("market_quote_classification"),
          "control_probability":cpv,"role_shadow_probability_same_side":rpv,
          "control_ev_at_quote":cev,"role_shadow_ev_at_quote_same_side":rev,
          "control_fair_american":fair_american(cpv),"role_shadow_fair_american_same_side":fair_american(rpv),
          "control_xtc":r.get("control_xtc"),"role_point_xtc":r.get("role_point_xtc"),
          "control_h012_snap_share":r.get("control_h012_snap_share"),"role_point_snap_share":r.get("role_point_snap_share"),
          "operational_status":r.get("operational_status"),
          "direct_book_verification_required":"TRUE" if venue_class(book)=="TRADITIONAL_SPORTSBOOK" else "FALSE",
          "authoritative_inactive_overlay_required":"TRUE",
          "actual_book":"","actual_line":"","actual_price":"","actual_observed_at":"",
          "actual_available":"","availability_verified":"","verification_notes":"",
        })

    order={
      "PRIMARY_DIRECT_BOOK_VERIFY":0,
      "STARTER_CONFLICT_REVIEW":1,
      "TRACK_DISAGREEMENT_REVIEW":2,
      "NO_DEPTH_REVIEW":3,
      "REFERENCE_ONLY_WATCH":4,
      "REFERENCE_ONLY_REVIEW":5,
      "ALTERNATIVE_PLATFORM_REVIEW":6,
      "UNCLASSIFIED_VENUE_REVIEW":7,
      "BACKUP_CONFLICT_QUARANTINE":8,
      "OTHER_REVIEW":9,
      "UNKNOWN_QUOTE_CLASS_REVIEW":10,
      "NONPOSITIVE_CONTROL_EV":11,
    }
    enriched.sort(key=lambda r:(order.get(str(r["queue_class"]),99),-(num(r.get("control_ev_at_quote")) or -999)))
    for i,r in enumerate(enriched,1):r["queue_rank"]=i
    primary=best_primary_per_player(enriched)
    for i,r in enumerate(primary,1):r["primary_rank"]=i

    stamp=nowdt().strftime("%Y%m%dT%H%M%SZ");seed=hashlib.sha256((cid+sha(cp)).encode()).hexdigest()[:8]
    qid=f"{stamp}_{seed}"
    base=data_root/"data/prospective/nfl/omega_week2_verification_queue_0351";st=base/("."+qid+".staging");final=base/qid
    if final.exists():raise SystemExit(f"FAIL immutable queue exists: {final}")
    st.mkdir(parents=True,exist_ok=False)
    try:
        fields=["queue_rank"]+[k for k in enriched[0] if k!="queue_rank"]
        wcsv(st/"OMEGA_0.35.1_WEEK2_MIXED_MARKET_VERIFICATION_QUEUE.csv",enriched,fields)
        pfields=["primary_rank"]+[k for k in primary[0] if k!="primary_rank"] if primary else ["primary_rank"]
        wcsv(st/"OMEGA_0.35.1_PRIMARY_DIRECT_BOOK_VERIFY.csv",primary,pfields)
        ref=[r for r in enriched if r["market_quote_classification"]=="REFERENCE_ONLY_NON_EXECUTABLE"]
        wcsv(st/"OMEGA_0.35.1_REFERENCE_ONLY_WATCH.csv",ref,fields)
        alt=[r for r in enriched if r["venue_class"]!="TRADITIONAL_SPORTSBOOK" and r["market_quote_classification"]=="EXECUTABLE_OFFER"]
        wcsv(st/"OMEGA_0.35.1_ALTERNATIVE_PLATFORM_REVIEW.csv",alt,fields)
        review=[r for r in enriched if r["queue_class"] not in {"PRIMARY_DIRECT_BOOK_VERIFY","REFERENCE_ONLY_WATCH","NONPOSITIVE_CONTROL_EV"}]
        wcsv(st/"OMEGA_0.35.1_REVIEW_AND_QUARANTINE.csv",review,fields)

        unmatched_file=cdir/"OMEGA_0.34.1_UNMATCHED.csv"
        if not unmatched_file.exists():unmatched_file=cdir/"OMEGA_0.34_UNMATCHED.csv"
        unmatched=rcsv(unmatched_file) if unmatched_file.exists() else []
        wcsv(st/"OMEGA_0.35.1_UPSTREAM_UNMATCHED.csv",unmatched)

        counts={};quote_counts={};venue_counts={}
        for r in enriched:
            counts[r["queue_class"]]=counts.get(r["queue_class"],0)+1
            quote_counts[r["market_quote_classification"]]=quote_counts.get(r["market_quote_classification"],0)+1
            venue_counts[r["venue_class"]]=venue_counts.get(r["venue_class"],0)+1
        audit={
          "schemaVersion":SCHEMA,"queueId":qid,"createdAt":now(),
          "comparisonId":cid,"comparisonSha256":sha(cp),"comparisonRows":len(rows),"queueRows":len(enriched),
          "codeRoot":str(root),"dataRoot":str(data_root),
          "classCounts":counts,"quoteClassCounts":quote_counts,"venueClassCounts":venue_counts,
          "primaryBestPerPlayerRows":len(primary),"unmatchedRowsCarriedForward":len(unmatched),
          "mixedExecutableReferenceInputSupported":True,
          "referenceOnlyRowsPrimaryEligible":False,
          "alternativePlatformRowsPrimarySportsbookEligible":False,
          "decisionProbabilityTrack":"FROZEN_OMEGA_CONTROL",
          "roleProbabilityStatus":"SHADOW_ONLY_NOT_PROMOTED",
          "queueRankingPolicy":"SPORTSBOOK_PRIMARY_THEN_REVIEW_REFERENCE_ALTERNATIVE_QUARANTINE; CONTROL_EV_WITHIN_CLASS",
          "directBookVerificationRequired":True,
          "authoritativeInactiveOverlayApplied":False,
          "modelRefits":0,"modelWrites":0,"oddsPapiRequests":0,
          "note":"Queue is market triage, not a bet recommendation. PropsMadness executable offers still require direct verification at the named sportsbook before any decision."
        }
        (st/"OMEGA_0.35.1_WEEK2_VERIFICATION_QUEUE_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n")
        (st/"OMEGA_OUTPUT_HASHES.json").write_text(json.dumps({p.name:sha(p) for p in st.iterdir() if p.is_file()},indent=2)+"\n")
        os.replace(st,final)
        atomic_text(data_root/"data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_VERIFICATION_QUEUE",qid+"\n")
        atomic_text(data_root/"data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_VERIFICATION_QUEUE_0351",qid+"\n")
    except BaseException:
        shutil.rmtree(st,ignore_errors=True);raise

    print("OMEGA 0.35.1 — WEEK 2 MIXED EXECUTABLE/REFERENCE VERIFICATION QUEUE")
    print(f"PASS comparison {cid} · rows {len(rows)} · queue {len(enriched)}")
    print("PASS quote classes:",json.dumps(quote_counts,sort_keys=True))
    print("PASS venue classes:",json.dumps(venue_counts,sort_keys=True))
    print("QUEUE CLASSES:",json.dumps(counts,sort_keys=True))
    print(f"PRIMARY BEST-PER-PLAYER DIRECT BOOK VERIFY {len(primary)}")
    print(f"REFERENCE-ONLY ROWS {len(ref)} · ALTERNATIVE-PLATFORM EXECUTABLE ROWS {len(alt)}")
    print(f"PASS upstream unmatched {len(unmatched)} · model refits/writes 0 · OddsPapi 0")
    print("TOP PRIMARY — DIRECTLY VERIFY NAMED BOOK + FINAL AVAILABILITY BEFORE DECISION:")
    for r in primary[:20]:
        cev=100*float(r["control_ev_at_quote"])
        rev=r.get("role_shadow_ev_at_quote_same_side");revs="NA" if rev is None else f"{100*float(rev):+.1f}%"
        cpct=100*float(r["control_probability"])
        rp=r.get("role_shadow_probability_same_side");rpct="NA" if rp is None else f"{100*float(rp):.1f}%"
        price=r.get("quote_price");prices="NA" if price is None else f"{float(price):+.0f}"
        print(f"  {r['game_id']} · {r['player_name']} {r['side']} {r['line']} {prices} {r['book']} · CONTROL p {cpct:.1f}% EV {cev:+.1f}% · ROLE p {rpct} EV {revs} · {r['role_state']}")
    print(f"QUEUE: {final/'OMEGA_0.35.1_WEEK2_MIXED_MARKET_VERIFICATION_QUEUE.csv'}")
    print(f"PRIMARY: {final/'OMEGA_0.35.1_PRIMARY_DIRECT_BOOK_VERIFY.csv'}")
    print(f"REFERENCE: {final/'OMEGA_0.35.1_REFERENCE_ONLY_WATCH.csv'}")
    print(f"REPORT: {final/'OMEGA_0.35.1_WEEK2_VERIFICATION_QUEUE_AUDIT.json'}")
    return 0

if __name__=="__main__":raise SystemExit(main())

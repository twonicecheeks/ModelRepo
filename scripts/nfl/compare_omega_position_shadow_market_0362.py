#!/usr/bin/env python3
"""OMEGA 0.36.2 — downstream market comparison for position challenger shadow.

Joins the immutable 0.36.1 prospective shadow to an already-built OMEGA 0.34.1
market comparison. The source market comparison has already enforced pre-kickoff
capture and deterministic identity matching. This layer does not recapture markets,
mutate control, or promote the LB shadow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse,csv,hashlib,json,math,os,uuid


VERSION="0.36.2"


def rcsv(p:Path):
    with p.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def wcsv(p:Path,rows):
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields or ["status"],extrasaction="ignore",lineterminator="\n");w.writeheader();w.writerows(rows)
def num(v):
    try:
        if v in (None,""):return None
        x=float(v);return x if math.isfinite(x) else None
    except:return None
def sha(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def atomic(p:Path,t:str):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name("."+p.name+".tmp");tmp.write_text(t.rstrip()+"\n",encoding="utf-8");os.replace(tmp,p)


def latest_comparison(root:Path)->Path:
    base=root/"data/prospective/nfl/omega_week2_market_comparison_0341"
    paths=sorted(base.glob("*/OMEGA_0.34.1_WEEK2_MARKET_COMPARISON.csv"))
    if not paths:raise FileNotFoundError("no OMEGA 0.34.1 market comparison found")
    return paths[-1]


def resolve_shadow(root:Path)->Path:
    ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_POSITION_SHADOW_0361"
    if not ptr.exists():raise FileNotFoundError("OMEGA 0.36.1 position shadow pointer missing")
    d=root/ptr.read_text(encoding="utf-8").strip()
    p=d/"OMEGA_0.36.1_WEEK2_POSITION_SHADOW.csv"
    if not p.exists():raise FileNotFoundError(p)
    return p


def roi(prob:float,american:float)->float:
    payout=american/100.0 if american>0 else 100.0/abs(american)
    return prob*payout-(1-prob)


def best(oe,ue):
    z=[("OVER",oe),("UNDER",ue)];z=[x for x in z if x[1] is not None]
    return max(z,key=lambda x:x[1]) if z else ("",None)


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--comparison-path",default="")
    args=ap.parse_args();root=Path(args.root).expanduser().resolve()
    shadow=resolve_shadow(root);srows=rcsv(shadow)
    smap={(str(r.get("game_id") or ""),str(r.get("player_id") or "")):r for r in srows}
    comparison=Path(args.comparison_path).expanduser().resolve() if args.comparison_path else latest_comparison(root)
    rows=rcsv(comparison)
    out=[];missing=0
    for r in rows:
        key=(str(r.get("game_id") or ""),str(r.get("player_id") or ""))
        s=smap.get(key)
        if s is None:
            missing+=1
            continue
        line=num(r.get("line"))
        if line is None:continue
        tag=str(float(line)).replace(".","_")
        po=num(s.get(f"position_shadow_p_over_{tag}"));pu=num(s.get(f"position_shadow_p_under_{tag}"))
        if po is None or pu is None:raise ValueError(f"missing position shadow probability at {line} for {r.get('player_name')}")
        oo=num(r.get("over_odds_american"));uo=num(r.get("under_odds_american"))
        one_side=str(r.get("one_sided_side") or "").upper();one=num(r.get("one_sided_odds_american"))
        oe=ue=None
        if oo is not None:oe=roi(po,oo)
        if uo is not None:ue=roi(pu,uo)
        if oo is None and uo is None and one is not None:
            if one_side=="OVER":oe=roi(po,one)
            elif one_side=="UNDER":ue=roi(pu,one)
        side,ev=best(oe,ue)
        z=dict(r);z.update({
            "position_shadow_comparison_version":VERSION,
            "position_shadow_track":s.get("position_shadow_track"),
            "position_shadow_xtc":s.get("position_shadow_xtc"),
            "position_shadow_delta_xtc":s.get("position_shadow_delta_xtc"),
            "position_shadow_p_over":po,"position_shadow_p_under":pu,
            "position_shadow_over_ev":oe,"position_shadow_under_ev":ue,
            "position_shadow_best_side":side,"position_shadow_best_ev":ev,
            "position_shadow_agrees_control":"TRUE" if side and side==str(r.get("control_best_side") or "") else "FALSE",
            "position_shadow_status":"SHADOW_ONLY_NOT_PROMOTED",
        })
        out.append(z)
    if not out:raise SystemExit("FAIL no position-shadow rows matched the selected market comparison")

    now=datetime.now(timezone.utc);run_id=now.strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    final=root/"data/prospective/nfl/omega_position_shadow_market_0362"/run_id;final.mkdir(parents=True,exist_ok=False)
    cp=final/"OMEGA_0.36.2_POSITION_SHADOW_MARKET_COMPARISON.csv";wcsv(cp,out)
    audit={
        "version":VERSION,"createdAt":now.isoformat(),"runId":run_id,
        "sourcePositionShadow":str(shadow.relative_to(root)),"sourcePositionShadowSha256":sha(shadow),
        "sourceMarketComparison":str(comparison.relative_to(root) if comparison.is_relative_to(root) else comparison),
        "sourceMarketComparisonSha256":sha(comparison),"rows":len(out),"unmatchedPastOrUnavailableRows":missing,
        "lbRows":sum(str(r.get("position_shadow_track") or "").startswith("LB_") for r in out),
        "lbSideChangesVsControl":sum(str(r.get("position_shadow_track") or "").startswith("LB_") and r.get("position_shadow_agrees_control")=="FALSE" for r in out),
        "integrity":{"marketReadDownstreamOnly":True,"modelRefits":0,"frozenOmegaMutation":False,
                     "positionShadowPromotion":False,"oddsPapiRequests":0},
    }
    apath=final/"OMEGA_0.36.2_POSITION_SHADOW_MARKET_AUDIT.json";apath.write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    atomic(root/"data/prospective/nfl/omega/CURRENT_OMEGA_POSITION_SHADOW_MARKET_0362",str(final.relative_to(root)))
    print("OMEGA 0.36.2 — POSITION SHADOW DOWNSTREAM MARKET COMPARISON")
    print(f"PASS rows {len(out)} · LB {audit['lbRows']} · LB control-side changes {audit['lbSideChangesVsControl']}")
    print("PASS SHADOW ONLY · frozen control unchanged · market downstream only")
    ranked=sorted([r for r in out if str(r.get("position_shadow_track") or "").startswith("LB_")],key=lambda r:float(r.get("position_shadow_best_ev") or -999),reverse=True)
    print("TOP LB SHADOW ROWS:")
    for r in ranked[:15]:
        cev=num(r.get("control_best_ev"));sev=num(r.get("position_shadow_best_ev"))
        print(f"  {r.get('game_id')} · {r.get('player_name')} · {r.get('book')} {r.get('line')} · CONTROL {r.get('control_best_side')} {'' if cev is None else f'{100*cev:+.1f}%'} · LB-shadow {r.get('position_shadow_best_side')} {'' if sev is None else f'{100*sev:+.1f}%'} · ΔxTC {float(r.get('position_shadow_delta_xtc') or 0):+.3f}")
    print(f"COMPARISON: {cp}")
    print(f"AUDIT: {apath}")
    return 0

if __name__=="__main__":raise SystemExit(main())

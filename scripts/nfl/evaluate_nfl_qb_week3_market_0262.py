#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse,csv,hashlib,json,re,sys,unicodedata,uuid
import week3_scope_0380 as scope
from run_nfl_week3_remaining_0380 import load_capture

SCHEMA="NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_0.2.4.3"
TRAD_BOOKS={"DraftKings","FanDuel","Caesars","BetMGM","Hard Rock","Hard Rock Bet","Fanatics","bet365","Pinnacle","Circa Sports"}
TEAM_ALIAS={"JAC":"JAX","GNB":"GB","KAN":"KC","LVR":"LV","NWE":"NE","NOR":"NO","SFO":"SF","TAM":"TB","WSH":"WAS"}

def fold(s): return unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode("ascii")
def cname(s):
    toks=re.findall(r"[A-Z0-9]+",fold(s).upper())
    while toks and toks[-1] in {"JR","SR","II","III","IV","V"}: toks.pop()
    return "".join(toks)
def cteam(s):
    x=re.sub(r"[^A-Z0-9]","",str(s or "").upper())
    return TEAM_ALIAS.get(x,x)
def team_abbr(t):
    if not isinstance(t,dict): return ""
    for k in ("nameAbbreviation","abbreviation","abbr","code","shortName","name"):
        v=t.get(k)
        if v not in (None,""): return cteam(v)
    return ""
def team_id(t):
    if not isinstance(t,dict): return ""
    for k in ("id","teamId","team_id"):
        v=t.get(k)
        if v not in (None,""): return str(v)
    return ""
def pname(player):
    v=player.get("name") or player.get("fullName")
    if v:return str(v).strip()
    return " ".join(str(x).strip() for x in (player.get("firstName"),player.get("lastName")) if x).strip()
def extract_matches(payload):
    raw=payload.get("matches") if isinstance(payload,dict) else None
    return [x.get("match",x) for x in raw if isinstance(x,dict)] if isinstance(raw,list) else []
def match_maps(payload, games):
    by_pair={(scope.team(g["away_team"]),scope.team(g["home_team"])):g for g in games}
    seen=set()
    teams={}; matches={}
    for m in extract_matches(payload):
        mid=m.get("id") or m.get("matchId")
        if mid in (None,""): continue
        home=m.get("homeTeam") if isinstance(m.get("homeTeam"),dict) else {}
        away=m.get("awayTeam") if isinstance(m.get("awayTeam"),dict) else {}
        hid,aid=team_id(home),team_id(away); h,a=team_abbr(home),team_abbr(away)
        if hid and h: teams[hid]=h
        if aid and a: teams[aid]=a
        pair=(scope.team(a),scope.team(h))
        if pair not in by_pair: continue
        if pair in seen: raise ValueError("ambiguous provider matchup")
        seen.add(pair)
        matches[str(mid)]=dict(by_pair[pair])
    return teams,matches
def load_jsonl(path):
    out=[]
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip(): out.append(json.loads(line))
    return out
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def read_csv(path):
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))
def write_csv(path,rows):
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n");w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser(description="Evaluate full frozen QB passing-yards slate against direct captured sportsbook quotes")
    ap.add_argument("--code-root",default="/Users/abbeyfelix/Developer/MODEL-NFL-039")
    ap.add_argument("--data-root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--capture",default="")
    args=ap.parse_args()
    code_root=Path(args.code_root).expanduser().resolve(); data_root=Path(args.data_root).expanduser().resolve()
    sys.path.insert(0,str(code_root/"packages/models/nfl/game"))
    import qb_passing_yards_market_025 as q25
    import qb_passing_yards_board_026 as q26

    slate_ptr=data_root/"data/prospective/nfl/CURRENT_QB_WEEK3_REMAINING_0245"
    if not slate_ptr.exists(): raise FileNotFoundError("CURRENT_QB_WEEK3_REMAINING_0245 missing")
    slate_dir=data_root/slate_ptr.read_text().strip()
    slate_path=slate_dir/"NFL_QB_PASSING_YARDS_SLATE_PROJECTIONS.csv"
    slate_audit=json.loads((slate_dir/"NFL_QB_WEEK3_AUDIT.json").read_text())
    if slate_audit.get("status")!="PROSPECTIVE_SHADOW_SLATE_COMPLETE": raise ValueError("incomplete Week 3 QB slate")
    games=slate_audit["scope"]
    scope.before_kickoff(games)
    if sha(slate_path)!=slate_audit["boardSha256"]: raise ValueError("QB board hash mismatch")
    slate=read_csv(slate_path)
    if not slate: raise ValueError("QB slate is empty")

    cap=Path(args.capture).expanduser().resolve() if args.capture else None
    if cap is None:
        caps=sorted((Path.home()/"Downloads").glob("NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_*.json"),key=lambda p:p.stat().st_mtime,reverse=True)
        if not caps: raise FileNotFoundError("no QB passing-yards direct capture in ~/Downloads")
        cap=caps[0]
    raw,_=load_capture(cap)
    if raw.get("schemaVersion")!=SCHEMA: raise ValueError("QB capture schema mismatch")
    slug=str(raw.get("marketSlug") or ""); reqs=raw.get("requests") or {}
    market_req=reqs.get(slug) or {}; match_req=reqs.get("matches") or {}
    if not slug or market_req.get("ok") is not True or match_req.get("ok") is not True: raise ValueError("QB capture requests not ready")
    offers=(market_req.get("data") or {}).get("offers") or []
    teams,matches=match_maps(match_req.get("data") or {},games)
    if not offers or not matches: raise ValueError("QB capture has no usable offers/matches")

    # Load frozen OOF residuals once.
    freeze_ptr=data_root/"data/models/nfl/CURRENT_QB_MODEL_021"
    if not freeze_ptr.exists(): raise FileNotFoundError("CURRENT_QB_MODEL_021 missing")
    freeze_dir=data_root/freeze_ptr.read_text().strip()
    freeze=json.loads((freeze_dir/"NFL_QB_PASSING_YARDS_FROZEN_SPEC.json").read_text())
    fm=json.loads((freeze_dir/"NFL_QB_PASSING_YARDS_FREEZE_MANIFEST.json").read_text())
    oof_path=data_root/str(freeze.get("sourceModelRunDirectory") or "")/"NFL_QB_PASSING_YARDS_OOF.jsonl"
    expected=(fm.get("sourceHashes") or {}).get("qb020OofJsonlSha256")
    if not expected or sha(oof_path)!=expected: raise ValueError("frozen OOF residual hash drift")
    residuals=q25.residual_rows(load_jsonl(oof_path))

    by_identity={}
    for r in slate:
        key=(str(r["game_id"]),cteam(r["team"]),cname(r["qb_name"]))
        if key in by_identity: raise ValueError(f"duplicate slate QB identity {key}")
        score_path=data_root/str(r["score_path"])
        if sha(score_path)!=r["score_sha256"]: raise ValueError("QB saved score hash mismatch")
        score=json.loads(score_path.read_text())
        frozen_sha=hashlib.sha256((json.dumps(freeze,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()
        if score.get("frozenSpecSha256")!=frozen_sha: raise ValueError("QB model/market frozen lineage mismatch")
        q25.assert_score_ready(score)
        by_identity[key]={"row":r,"score":score,"score_path":score_path}

    rows=[]; unmatched=[]; unsupported=[]
    cache={}
    for entry in offers:
        if not isinstance(entry,dict): continue
        root=entry.get("offer") if isinstance(entry.get("offer"),dict) else entry
        bet=root.get("bet") if isinstance(root.get("bet"),dict) else None
        if not bet: continue
        sb=bet.get("sportsbook") if isinstance(bet.get("sportsbook"),dict) else {}
        book=str(sb.get("name") or "")
        if book not in TRAD_BOOKS: continue
        line=bet.get("line"); odds=bet.get("odds") if isinstance(bet.get("odds"),dict) else {}
        if line is None or not odds: continue
        try: ln=q25.assert_half_yard_line(float(line))
        except Exception:
            unsupported.append({"book":book,"line":line,"player":pname(root.get("player") or {})}); continue
        player=root.get("player") if isinstance(root.get("player"),dict) else {}
        name=pname(player); team=scope.team(teams.get(str(player.get("teamId") or root.get("teamId") or ""),""))
        mid=str(root.get("matchId") or ""); mm=matches.get(mid)
        if not name or not team or mm is None: continue
        key=(mm["game_id"],team,cname(name))
        target=by_identity.get(key)
        if target is None:
            unmatched.append({"game_id":mm["game_id"],"team":team,"qb_name":name,"book":book,"line":ln}); continue
        over=odds.get("over"); under=odds.get("under")
        op=None if over is None else q25.validate_american(over)
        up=None if under is None else q25.validate_american(under)
        if op is None and up is None: continue
        point=float(target["score"]["projectionPassingYards"])
        ck=(target["score"]["runId"],ln)
        if ck not in cache:
            probs=q25.empirical_market_probability(residuals,point,ln)
            boot=q25.cluster_bootstrap_probability(residuals,point,ln)
            cache[ck]=(probs,boot)
        probs,boot=cache[ck]
        nv=q25.no_vig_two_way(op,up) if op is not None and up is not None else None
        osum=q26.add_probability_ci(q25.market_side_summary(probs["overProbability"],op,None if nv is None else nv["overNoVig"]),boot["overCi95"],op,q25)
        usum=q26.add_probability_ci(q25.market_side_summary(probs["underProbability"],up,None if nv is None else nv["underNoVig"]),boot["underCi95"],up,q25)
        osum["shadowDisposition"]=q26.shadow_disposition(osum); usum["shadowDisposition"]=q26.shadow_disposition(usum)
        rows.append({
          "game_id":mm["game_id"],"team":team,"opponent":target["row"]["opponent"],"qb_name":name,
          "projection_passing_yards":round(point,3),"book":book,"line":ln,
          "over_price":"" if op is None else op,"under_price":"" if up is None else up,
          "over_probability":round(float(probs["overProbability"]),6),"under_probability":round(float(probs["underProbability"]),6),
          "over_fair":osum["modelFairAmerican"],"under_fair":usum["modelFairAmerican"],
          "over_ev_pct":"" if osum["expectedRoiPct"] is None else round(float(osum["expectedRoiPct"]),3),
          "under_ev_pct":"" if usum["expectedRoiPct"] is None else round(float(usum["expectedRoiPct"]),3),
          "over_ci_low_ev_pct":"" if osum.get("expectedRoiPctCi95") is None else round(float(osum["expectedRoiPctCi95"][0]),3),
          "under_ci_low_ev_pct":"" if usum.get("expectedRoiPctCi95") is None else round(float(usum["expectedRoiPctCi95"][0]),3),
          "over_disposition":osum["shadowDisposition"],"under_disposition":usum["shadowDisposition"],
          "score_path":str(target["score_path"].relative_to(data_root))
        })

    if not rows: raise ValueError("no captured sportsbook quotes matched the QB slate")
    # Deduplicate identical player/book/line quotes caused by repeated capture structures.
    dedup={}
    for r in rows:
        k=(r["game_id"],r["team"],cname(r["qb_name"]),r["book"],r["line"],r["over_price"],r["under_price"])
        dedup[k]=r
    rows=list(dedup.values())

    best=[]
    for r in rows:
        for side in ("OVER","UNDER"):
            ev=r[f"{side.lower()}_ev_pct"]
            if ev=="": continue
            best.append({
              "game_id":r["game_id"],"team":r["team"],"qb_name":r["qb_name"],"projection":r["projection_passing_yards"],
              "book":r["book"],"side":side,"line":r["line"],"price":r[f"{side.lower()}_price"],
              "model_probability":r[f"{side.lower()}_probability"],"fair_american":r[f"{side.lower()}_fair"],
              "ev_pct":float(ev),"ci_low_ev_pct":r[f"{side.lower()}_ci_low_ev_pct"],
              "disposition":r[f"{side.lower()}_disposition"]
            })
    best.sort(key=lambda r:(-r["ev_pct"],r["game_id"],r["qb_name"],r["book"],r["side"]))
    seen=set(); best_player=[]
    for r in best:
        k=(r["game_id"],r["team"],cname(r["qb_name"]))
        if k in seen: continue
        seen.add(k); best_player.append(r)

    scope.before_kickoff(games)
    scope.fresh(raw["capturedAt"])
    now=datetime.now(timezone.utc); run_id=now.strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    od=data_root/"data/prospective/nfl/qb_week3_market_0262"/run_id; od.mkdir(parents=True,exist_ok=False)
    allp=od/"NFL_QB_PASSING_YARDS_MARKET_QUOTES.csv"; write_csv(allp,sorted(rows,key=lambda r:(r["game_id"],r["team"],r["line"],r["book"])))
    bestp=od/"NFL_QB_PASSING_YARDS_BEST_PER_PLAYER.csv"; write_csv(bestp,best_player)
    audit={
      "version":"0.2.6.2","createdAt":now.isoformat(),"runId":run_id,"capture":str(cap),"captureCapturedAt":raw.get("capturedAt"),
      "slatePath":str(slate_path),"slateQbs":len(slate),"matchedQuoteRows":len(rows),"bestPlayerRows":len(best_player),
      "unmatchedQuoteRows":len(unmatched),"unsupportedLineRows":len(unsupported),"frozenOofResidualRows":len(residuals),
      "marketFieldsUsedAsModelFeatures":False,"coefficientRefitPerformed":False,"candidateReselectionPerformed":False,
      "targetOrLater2026OutcomeRowsAdmitted":0,"marketExecutionEligible":False,
      "sourceClass":"PROPSMADNESS_AGGREGATED_BOOK_REFERENCE", "captureSha256":sha(cap),
      "nextGate":"DIRECT_BOOK_FRESHNESS_PLUS_AVAILABILITY_AND_PROSPECTIVE_CLV_VALIDATION"
    }
    (od/"NFL_QB_PASSING_YARDS_MARKET_SLATE_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n")
    scope.before_kickoff(games)
    ptr=data_root/"data/prospective/nfl/CURRENT_QB_WEEK3_MARKET_0262"; ptr.write_text(str(od.relative_to(data_root))+"\n")

    print("\nNFL QB MODEL 0.2.6.2 — WEEK 3 AGGREGATED-BOOK REFERENCE SLATE")
    print(f"PASS slate QBs {len(slate)} · matched quote rows {len(rows)} · best-per-player {len(best_player)}")
    print(f"PASS unmatched {len(unmatched)} · unsupported whole/non-half lines {len(unsupported)}")
    print("PASS frozen OOF probabilities · market downstream only · refits 0 · same-week outcomes 0")
    print("\nTOP BEST-PER-PLAYER SHADOW EDGES")
    for r in best_player[:30]:
        ci="" if r["ci_low_ev_pct"]=="" else f" · CI-low EV {float(r['ci_low_ev_pct']):+.1f}%"
        print(f"  {r['game_id']} · {r['qb_name']} {r['side']} {r['line']:.1f} {int(r['price']):+d} {r['book']} · p {100*float(r['model_probability']):.1f}% · EV {r['ev_pct']:+.1f}%{ci} · {r['disposition']}")
    print(f"ALL QUOTES: {allp}")
    print(f"BEST: {bestp}")
    print(f"AUDIT: {od/'NFL_QB_PASSING_YARDS_MARKET_SLATE_AUDIT.json'}")
    return 0

if __name__=="__main__": raise SystemExit(main())


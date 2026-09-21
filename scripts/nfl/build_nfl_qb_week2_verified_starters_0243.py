#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import csv, json, os, re, unicodedata

ROOT=Path(os.environ.get("MODEL_DATA_ROOT_OVERRIDE","/Users/abbeyfelix/Developer/MODEL")).expanduser().resolve()
SCHEMA="NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_0.2.4.3"
TRAD_BOOKS={"DraftKings","FanDuel","Caesars","BetMGM","Hard Rock","Hard Rock Bet","Fanatics","bet365","Pinnacle","Circa Sports"}

TEAM_ALIAS={
 "JAC":"JAX","GNB":"GB","KAN":"KC","LVR":"LV","NWE":"NE","NOR":"NO","SFO":"SF","TAM":"TB","WSH":"WAS"
}

def fold(s):
    return unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode("ascii")

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

def extract_matches(payload):
    if isinstance(payload,dict):
        raw=payload.get("matches")
        if isinstance(raw,list):
            return [x.get("match",x) for x in raw if isinstance(x,dict)]
    return []

def match_maps(payload):
    teams={}; matches={}
    for m in extract_matches(payload):
        mid=m.get("id") or m.get("matchId")
        if mid in (None,""): continue
        home=m.get("homeTeam") if isinstance(m.get("homeTeam"),dict) else {}
        away=m.get("awayTeam") if isinstance(m.get("awayTeam"),dict) else {}
        hid,aid=team_id(home),team_id(away); h,a=team_abbr(home),team_abbr(away)
        if hid and h: teams[hid]=h
        if aid and a: teams[aid]=a
        matches[str(mid)]={"home":h,"away":a}
    return teams,matches

def pname(player):
    v=player.get("name") or player.get("fullName")
    if v:return str(v).strip()
    return " ".join(str(x).strip() for x in (player.get("firstName"),player.get("lastName")) if x).strip()

def roster_name(r):
    for k in ("full_name","player_name","display_name","football_name","name"):
        if str(r.get(k) or "").strip(): return str(r[k]).strip()
    first=str(r.get("first_name") or "").strip(); last=str(r.get("last_name") or "").strip()
    return (first+" "+last).strip()

def phase1_dir(root):
    ptr=root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"
    if not ptr.exists(): raise FileNotFoundError("CURRENT_PHASE1_SNAPSHOT missing")
    sid=ptr.read_text().strip()
    p=root/"data/normalized/nfl/phase1"/sid
    if not p.exists(): raise FileNotFoundError(p)
    return p

def load_identity_indexes(root):
    """Build exact canonical identity indexes without pretending historical rosters are 2026 rosters.

    player_identity.csv is a canonical crosswalk with display_name/latest_team.
    qb_roster_weekly.csv is historical only and is used strictly as a fallback
    identity crosswalk, never as evidence that the player is on a 2026 roster.
    """
    p1=phase1_dir(root)
    player_path=p1/"player_identity.csv"
    roster_path=p1/"qb_roster_weekly.csv"
    if not player_path.exists(): raise FileNotFoundError(player_path)
    if not roster_path.exists(): raise FileNotFoundError(roster_path)

    current=defaultdict(set)
    name_only=defaultdict(set)
    with player_path.open(newline="",encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            gid=str(r.get("gsis_id") or "").strip()
            name=str(r.get("display_name") or "").strip()
            team=cteam(r.get("latest_team"))
            if not gid or not name: continue
            norm=cname(name)
            name_only[norm].add(gid)
            if team: current[(team,norm)].add(gid)

    historical_name=defaultdict(set)
    with roster_path.open(newline="",encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            gid=str(r.get("gsis_id") or "").strip()
            name=roster_name(r)
            if gid and name:
                historical_name[cname(name)].add(gid)
    return player_path,roster_path,current,name_only,historical_name

def main():
    caps=sorted((Path.home()/"Downloads").glob("NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_*.json"),key=lambda p:p.stat().st_mtime,reverse=True)
    if not caps: raise SystemExit("FAIL no QB passing-yards direct capture found in ~/Downloads")
    src=caps[0]; data=json.loads(src.read_text())
    if data.get("schemaVersion")!=SCHEMA: raise SystemExit("FAIL wrong QB capture schema")
    slug=str(data.get("marketSlug") or "")
    if not slug: raise SystemExit("FAIL no passing-yards market route resolved in capture")
    reqs=data.get("requests") or {}
    mreq=reqs.get(slug) or {}; matches_req=reqs.get("matches") or {}
    if mreq.get("ok") is not True: raise SystemExit("FAIL passing-yards market request was not HTTP OK")
    if matches_req.get("ok") is not True: raise SystemExit("FAIL matches request was not HTTP OK")
    payload=mreq.get("data") or {}; offers=payload.get("offers") or []
    if not isinstance(offers,list) or not offers: raise SystemExit("FAIL no passing-yards offers")
    teams,matches=match_maps(matches_req.get("data"))
    if not teams or not matches: raise SystemExit("FAIL could not resolve PropsMadness team/match maps")

    # Build direct traditional-sportsbook player identity evidence.
    candidates=defaultdict(lambda:{"books":set(),"matches":set(),"names":set()})
    for entry in offers:
        if not isinstance(entry,dict): continue
        root=entry.get("offer") if isinstance(entry.get("offer"),dict) else entry
        bet=root.get("bet") if isinstance(root.get("bet"),dict) else None
        if not bet: continue
        book=(bet.get("sportsbook") or {}).get("name") if isinstance(bet.get("sportsbook"),dict) else None
        if book not in TRAD_BOOKS: continue
        player=root.get("player") if isinstance(root.get("player"),dict) else {}
        name=pname(player); tid=str(player.get("teamId") or root.get("teamId") or "")
        team=teams.get(tid,""); mid=str(root.get("matchId") or "")
        if not name or not team or mid not in matches: continue
        mm=matches[mid]
        if team not in {mm["away"],mm["home"]}: continue
        key=(team,cname(name))
        candidates[key]["books"].add(book); candidates[key]["matches"].add(mid); candidates[key]["names"].add(name)

    # Resolve direct-market identity to canonical GSIS ID.
    # IMPORTANT: the Phase1 weekly roster snapshot intentionally ends before
    # prospective 2026, so it must never be filtered as though it were a 2026 roster.
    player_path,roster_path,current_by_team,name_only,historical_name=load_identity_indexes(ROOT)

    resolved=[]; unresolved=[]
    team_players=defaultdict(list)
    for (team,norm),meta in candidates.items():
        name=sorted(meta["names"])[0]
        mids=sorted(meta["matches"])
        # Strongest identity route: exact canonical name + current latest_team.
        ids=sorted(current_by_team.get((team,norm),set()))
        method="PLAYER_IDENTITY_NAME_TEAM"
        # If latest_team is unavailable/stale, allow exact-name-only only when
        # it uniquely identifies one canonical GSIS ID across the player table.
        if len(ids)!=1:
            ids2=sorted(name_only.get(norm,set()))
            if len(ids2)==1:
                ids=ids2; method="PLAYER_IDENTITY_UNIQUE_NAME"
        # Final identity-only fallback: exact historical QB name with one GSIS ID.
        # This does NOT assert current roster membership; the direct sportsbook
        # market is the 2026 starter/team evidence.
        if len(ids)!=1:
            ids3=sorted(historical_name.get(norm,set()))
            if len(ids3)==1:
                ids=ids3; method="HISTORICAL_QB_IDENTITY_UNIQUE_NAME"
        if len(ids)!=1 or len(mids)!=1:
            unresolved.append({"team":team,"qb_name":name,"gsis_ids":"|".join(ids),"match_ids":"|".join(mids),"reason":"CANONICAL_ID_OR_MATCH_AMBIGUOUS"})
            continue
        mid=mids[0]; mm=matches[mid]
        game_id=f"2026_02_{mm['away']}_{mm['home']}"
        rec={"game_id":game_id,"team":team,"qb_gsis_id":ids[0],"qb_name":name,"identity_source":"DIRECT_SPORTSBOOK_MARKET","books":"|".join(sorted(meta["books"])),"identity_method":method}
        team_players[team].append(rec)

    for team,rows in sorted(team_players.items()):
        if len(rows)==1:
            resolved.append(rows[0])
        else:
            for r in rows:
                unresolved.append({**r,"reason":"MULTIPLE_DIRECT_MARKET_QBS_FOR_TEAM"})

    # Only manifest columns consumed by 0.2.4.2.
    outdir=ROOT/"data/inputs/nfl"; outdir.mkdir(parents=True,exist_ok=True)
    manifest=outdir/"qb_week2_verified_starters.csv"
    fields=["game_id","team","qb_gsis_id","qb_name","identity_source"]
    with manifest.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader()
        for r in sorted(resolved,key=lambda x:(x["game_id"],x["team"])):
            w.writerow({k:r[k] for k in fields})

    qpath=outdir/"qb_week2_verified_starters_unresolved.csv"
    qfields=["team","qb_name","gsis_ids","match_ids","game_id","qb_gsis_id","identity_source","books","reason"]
    with qpath.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=qfields,extrasaction="ignore",lineterminator="\n");w.writeheader();w.writerows(unresolved)

    audit={
      "version":"0.2.4.3","createdAt":datetime.now(timezone.utc).isoformat(),
      "capture":str(src),"marketSlug":slug,"directMarketIdentitySource":"DIRECT_SPORTSBOOK_MARKET",
      "traditionalSportsbookCandidates":len(candidates),"resolvedStarterRows":len(resolved),"unresolvedRows":len(unresolved),
      "playerIdentityFile":str(player_path),"historicalQbRosterFile":str(roster_path),
      "identityMatching":"EXACT_CANONICAL_NAME_TEAM_THEN_UNIQUE_EXACT_NAME_NO_FUZZY",
      "modelFitPerformed":False,"marketUsedAsModelFeature":False
    }
    (outdir/"qb_week2_verified_starters_audit.json").write_text(json.dumps(audit,indent=2)+"\n")

    print("\nNFL QB 0.2.4.3 — DIRECT-MARKET STARTER MANIFEST")
    print(f"PASS passing-yards market slug {slug} · direct sportsbook QB identities {len(candidates)}")
    print(f"PASS resolved manifest rows {len(resolved)} · unresolved {len(unresolved)}")
    print("PASS canonical player identity first · historical QB identity fallback only · fuzzy matching NO")
    print("PASS direct sportsbook market is current 2026 team/starter evidence; historical roster is NOT treated as current")
    for r in sorted(resolved,key=lambda x:(x["game_id"],x["team"])):
        print(f"  {r['game_id']} · {r['team']} · {r['qb_name']} · {r['qb_gsis_id']} · {r['identity_method']} · {r['books']}")
    print(f"MANIFEST: {manifest}")
    print(f"UNRESOLVED: {qpath}")
    if not resolved: raise SystemExit("FAIL no QB starter identities resolved")
    return 0

if __name__=="__main__": raise SystemExit(main())

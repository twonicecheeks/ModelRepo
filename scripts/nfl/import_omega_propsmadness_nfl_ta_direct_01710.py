#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, json, re, subprocess, sys, zipfile
from collections import Counter

EXPECTED_SCHEMA = "OMEGA_PM_NFL_TA_DIRECT_CAPTURE_0.17.6"
EXPECTED_SLUG = "player-tackles-assists"
FIELDS = [
 'captured_at','source','book','game_id','game_date','away_team','home_team',
 'player_id','player_name','player_team','opponent','market_kind','market_label','line',
 'over_odds_american','under_odds_american','one_sided_side','one_sided_odds_american',
 'settlement_scope','includes_special_teams','stat_correction_policy','source_event_id','notes'
]
QUARANTINE_FIELDS = ['raw_index','reason','top_level_keys','raw_json']
REFERENCE_FIELDS = [
 'raw_index','offer_type','match_id','player_id','player_name','sportsbook',
 'market_slug','line','over_odds_american','under_odds_american','classification','raw_json'
]

LINE_KEYS = ('line','points','point','threshold','total','handicap')
ODDS_KEYS = ('american','americanOdds','american_odds','price','odds')

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def first(*vals):
    for v in vals:
        if v is not None and v != "":
            return v
    return None

def obj(*vals):
    for v in vals:
        if isinstance(v, dict):
            return v
    return {}

def numberish(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int,float)):
        return float(v)
    if isinstance(v, str):
        m=re.search(r'[-+]?\d+(?:\.\d+)?',v.replace(",",""))
        return float(m.group()) if m else None
    return None

def american(v):
    """Extract American odds only; fail closed on decimal/probability-looking values."""
    if v is None:
        return None
    if isinstance(v,dict):
        for k in ODDS_KEYS:
            if k in v:
                n=numberish(v[k])
                if n is not None:
                    break
        else:
            n=None
    else:
        n=numberish(v)
    if n is None:
        return None
    # Normal US prices generally have magnitude >= 100.
    if -100 < n < 100:
        raise ValueError(f"non-American-looking odds value {n}")
    return int(round(n)) if abs(n-round(n)) < 1e-8 else n

def scalar_line(v):
    n=numberish(v)
    if n is None:
        return None
    # NFL T+A lines outside this range are almost certainly not line values.
    if 0 <= n <= 30:
        return n
    return None

def line_from_dict(d):
    if not isinstance(d,dict):
        return None
    for k in LINE_KEYS:
        if k in d:
            n=scalar_line(d[k])
            if n is not None:
                return n
    return None

def recursive_line(x, depth=0):
    """Search only line-semantic keys; never infer a line from generic numeric values."""
    if depth > 6:
        return None
    if isinstance(x,dict):
        n=line_from_dict(x)
        if n is not None:
            return n
        # Prefer semantic containers commonly used by offer APIs.
        for k in ('selection','selections','outcome','outcomes','over','under','bet','offer','market'):
            if k in x:
                n=recursive_line(x[k],depth+1)
                if n is not None:
                    return n
        for v in x.values():
            if isinstance(v,(dict,list)):
                n=recursive_line(v,depth+1)
                if n is not None:
                    return n
    elif isinstance(x,list):
        for v in x:
            n=recursive_line(v,depth+1)
            if n is not None:
                return n
    return None

def odds_pair(raw):
    if not isinstance(raw,dict):
        return None,None
    over=first(raw.get('over'),raw.get('o'),raw.get('Over'),raw.get('OVER'))
    under=first(raw.get('under'),raw.get('u'),raw.get('Under'),raw.get('UNDER'))
    return american(over) if over is not None else None, american(under) if under is not None else None

def recursive_side_odds(x):
    """Fallback for payloads that encode OVER/UNDER as selection objects."""
    over=under=None
    def walk(v,depth=0):
        nonlocal over,under
        if depth>7:return
        if isinstance(v,dict):
            label=str(first(v.get('side'),v.get('label'),v.get('name'),v.get('type'),v.get('outcome')) or '').strip().upper()
            if label in ('OVER','O') and over is None:
                try: over=american(first(v.get('americanOdds'),v.get('american_odds'),v.get('price'),v.get('odds')))
                except ValueError: raise
            if label in ('UNDER','U') and under is None:
                try: under=american(first(v.get('americanOdds'),v.get('american_odds'),v.get('price'),v.get('odds')))
                except ValueError: raise
            for vv in v.values():
                if isinstance(vv,(dict,list)):walk(vv,depth+1)
        elif isinstance(v,list):
            for vv in v:walk(vv,depth+1)
    walk(x)
    return over,under

def name_of(player):
    if not isinstance(player,dict):
        return None
    fn=first(player.get('firstName'),player.get('first_name'),player.get('givenName'))
    ln=first(player.get('lastName'),player.get('last_name'),player.get('familyName'))
    return first(player.get('name'),player.get('fullName')," ".join(str(x) for x in (fn,ln) if x).strip())

def team_label(t):
    if not isinstance(t,dict):
        return None
    return first(t.get('abbreviation'),t.get('abbr'),t.get('code'),t.get('shortName'),t.get('name'))

def team_id(t):
    if not isinstance(t,dict):
        return None
    return first(t.get('id'),t.get('teamId'),t.get('team_id'))

def walk_dicts(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():
            yield from walk_dicts(v)
    elif isinstance(x,list):
        for v in x:
            yield from walk_dicts(v)

def build_team_map(matches_payload):
    out={}
    for d in walk_dicts(matches_payload):
        ident=team_id(d); label=team_label(d)
        if ident is not None and label:
            out[str(ident)] = str(label)
    return out

def extract_match_records(matches_payload):
    if isinstance(matches_payload,dict):
        for key in ('matches','games','events'):
            if isinstance(matches_payload.get(key),list):
                return matches_payload[key]
    if isinstance(matches_payload,list):
        return matches_payload
    return []

def match_meta(matches_payload):
    out={}
    for m in extract_match_records(matches_payload):
        if not isinstance(m,dict): continue
        mid=first(m.get('id'),m.get('matchId'),m.get('match_id'),m.get('eventId'))
        if mid is None: continue
        home=obj(m.get('homeTeam'),m.get('home_team'),m.get('home'))
        away=obj(m.get('awayTeam'),m.get('away_team'),m.get('away'))
        out[str(mid)]={
            'home_team': team_label(home) or '',
            'away_team': team_label(away) or '',
            'home_team_id': str(team_id(home) or ''),
            'away_team_id': str(team_id(away) or ''),
            'game_date': str(first(m.get('startTime'),m.get('startDate'),m.get('date'),m.get('gameDate')) or '')
        }
    return out

def normalize_offer(entry, payload_market, team_map, match_map, raw_index):
    if not isinstance(entry,dict):
        raise ValueError("offer is not an object")
    root=obj(entry.get('offer'), entry)
    bet=obj(root.get('bet'), entry.get('bet'))
    player=obj(root.get('player'), entry.get('player'), bet.get('player'))
    market=obj(bet.get('market'),root.get('market'),entry.get('market'),payload_market)
    sportsbook=obj(bet.get('sportsbook'),root.get('sportsbook'),entry.get('sportsbook'))

    raw_odds=first(bet.get('odds'),root.get('odds'),entry.get('odds'))
    over,under=odds_pair(raw_odds)
    if over is None and under is None:
        over,under=recursive_side_odds(entry)

    match_id=first(root.get('matchId'),entry.get('matchId'),bet.get('matchId'),
                   obj(root.get('match')).get('id'),obj(entry.get('match')).get('id'))
    player_id=first(player.get('id'),root.get('playerId'),entry.get('playerId'))
    pteam=first(team_label(obj(player.get('team'))), player.get('teamAbbreviation'), player.get('team'), player.get('teamName'))
    pteam_id=first(player.get('teamId'),player.get('team_id'),root.get('teamId'),entry.get('teamId'))
    if isinstance(pteam,(dict,list)): pteam=None
    if not pteam and pteam_id is not None: pteam=team_map.get(str(pteam_id))

    # Direct locations first; then semantic recursive search.
    line=first(
        line_from_dict(bet),
        line_from_dict(root),
        line_from_dict(entry),
        recursive_line(raw_odds),
        recursive_line(entry)
    )
    if line is None:
        raise ValueError("missing line after nested/selection search")

    pname=name_of(player)
    if not pname: raise ValueError("missing player name")
    book=first(sportsbook.get('name'),sportsbook.get('slug'),sportsbook.get('id'))
    if not book: raise ValueError("missing sportsbook")
    if over is None and under is None: raise ValueError("missing over/under American odds")

    mm=match_map.get(str(match_id),{}) if match_id is not None else {}
    home,away=mm.get('home_team',''),mm.get('away_team','')
    opponent=''
    if pteam:
        if str(pteam).upper()==str(home).upper(): opponent=away
        elif str(pteam).upper()==str(away).upper(): opponent=home

    source_event_id=first(root.get('id'),bet.get('id'),entry.get('id'))
    if source_event_id is None:
        source_event_id=f"{match_id or ''}:{player_id or pname}:{book}:{line}:{raw_index}"

    row={k:'' for k in FIELDS}
    row.update({
      'captured_at':'',
      'source':'propsmadness-table-api',
      'book':str(book),
      'game_id':str(match_id or ''),
      'game_date':mm.get('game_date',''),
      'away_team':away,'home_team':home,
      'player_id':str(player_id or ''),'player_name':str(pname),
      'player_team':str(pteam or ''),'opponent':str(opponent or ''),
      'market_kind':'tackles_assists',
      'market_label':str(first(market.get('name'),payload_market.get('name'),'Tackles + Assists')),
      'line':str(float(line)).rstrip('0').rstrip('.') if isinstance(line,float) else str(line),
      'settlement_scope':'UNKNOWN',
      'includes_special_teams':'UNKNOWN',
      'stat_correction_policy':'UNKNOWN',
      'source_event_id':str(source_event_id),
      'notes':f"PropsMadness market slug {first(market.get('slug'),payload_market.get('slug'),EXPECTED_SLUG)}; settlement unresolved"
    })
    if over is not None and under is not None:
        row['over_odds_american']=str(over); row['under_odds_american']=str(under)
    elif over is not None:
        row['one_sided_side']='OVER'; row['one_sided_odds_american']=str(over)
    elif under is not None:
        row['one_sided_side']='UNDER'; row['one_sided_odds_american']=str(under)
    return row


def classify_reference_only(entry, raw_index):
    """Return a preserved non-executable reference quote for explicit noOffer rows."""
    if not isinstance(entry,dict):
        return None
    root=obj(entry.get('offer'),entry)
    offer_type=str(root.get('offerType') or '').strip()
    if offer_type != 'noOffer':
        return None
    live_bet=obj(root.get('bet'))
    # A noOffer row should not carry an executable live bet.
    if live_bet.get('sportsbook') is not None or live_bet.get('line') is not None or live_bet.get('odds') is not None:
        raise ValueError(f"offer {raw_index}: noOffer unexpectedly contains executable bet fields")
    ref=obj(root.get('referenceBet'))
    player=obj(root.get('player'),entry.get('player'))
    book_obj=obj(ref.get('sportsbook'))
    book=first(book_obj.get('name'),book_obj.get('slug'),book_obj.get('id'))
    market=obj(ref.get('market'))
    slug=first(market.get('slug'),market.get('code'))
    line=recursive_line(ref)
    over,under=odds_pair(ref.get('odds'))
    pname=name_of(player)
    return {
      'raw_index':raw_index,
      'offer_type':offer_type,
      'match_id':str(root.get('matchId') or ''),
      'player_id':str(player.get('id') or ''),
      'player_name':str(pname or ''),
      'sportsbook':str(book or ''),
      'market_slug':str(slug or ''),
      'line':'' if line is None else str(float(line)).rstrip('0').rstrip('.'),
      'over_odds_american':'' if over is None else str(over),
      'under_odds_american':'' if under is None else str(under),
      'classification':'REFERENCE_ONLY_NON_EXECUTABLE',
      'raw_json':json.dumps(entry,ensure_ascii=False,separators=(',',':'))[:12000]
    }

def normalize_capture(data):
    req=data.get('requests') or {}
    market_req=req.get('market') or {}
    matches_req=req.get('matches') or {}
    if market_req.get('ok') is not True:
        raise ValueError(f"market endpoint failed HTTP {market_req.get('status')}: {market_req.get('error') or market_req.get('text')}")
    payload=market_req.get('data')
    if not isinstance(payload,dict): raise ValueError("market endpoint did not return JSON object")
    offers=payload.get('offers')
    if not isinstance(offers,list): raise ValueError("market payload offers[] missing")
    if not offers: raise ValueError("market payload offers[] is empty")
    pm=payload.get('market') if isinstance(payload.get('market'),dict) else {}
    observed=pm.get('slug')
    if observed and observed != EXPECTED_SLUG:
        raise ValueError(f"market slug mismatch: {observed} != {EXPECTED_SLUG}")

    matches_payload=matches_req.get('data') if isinstance(matches_req.get('data'),(dict,list)) else {}
    teams=build_team_map(matches_payload); matches=match_meta(matches_payload)

    rows=[]; reference_only=[]; quarantine=[]
    for i,x in enumerate(offers):
        try:
            ref=classify_reference_only(x,i)
            if ref is not None:
                reference_only.append(ref)
                continue
            rows.append(normalize_offer(x,pm,teams,matches,i))
        except Exception as e:
            quarantine.append({
              'raw_index':i,
              'reason':str(e),
              'top_level_keys':','.join(sorted(x.keys())) if isinstance(x,dict) else '',
              'raw_json':json.dumps(x,ensure_ascii=False,separators=(',',':'))[:12000]
            })

    if not rows:
        raise ValueError(f"no executable offers normalized from {len(offers)} endpoint rows")
    # Expected explicit noOffer/referenceBet rows are not schema failures.
    # Only genuinely malformed/unclassified rows count against the drift threshold.
    reject_rate=len(quarantine)/len(offers)
    if reject_rate > 0.25:
        reasons=Counter(q['reason'] for q in quarantine)
        raise ValueError(f"schema drift: rejected {len(quarantine)}/{len(offers)} offers ({reject_rate:.1%}); reasons={dict(reasons)}")

    stats={
      'offerCount':len(offers),'normalizedRows':len(rows),'referenceOnlyRows':len(reference_only),
      'quarantinedRows':len(quarantine),'quarantineRate':reject_rate,
      'quarantineReasons':dict(Counter(q['reason'] for q in quarantine)),
      'teamMapCount':len(teams),'matchMapCount':len(matches),
      'observedMarketSlug':observed or EXPECTED_SLUG
    }
    return rows,reference_only,quarantine,stats

def main():
    downloads=Path.home()/'Downloads'
    cap=sorted(downloads.glob('OMEGA_0176_PROPSMADNESS_NFL_TA_DIRECT_CAPTURE_*.json'),
               key=lambda p:p.stat().st_mtime, reverse=True)
    if not cap: raise SystemExit('FAIL no OMEGA 0.17.6 direct capture found in ~/Downloads')
    src=cap[0]; raw=src.read_bytes()
    try:data=json.loads(raw)
    except Exception as e:raise SystemExit(f'FAIL capture is not valid JSON: {e}')
    if data.get('schemaVersion') != EXPECTED_SCHEMA: raise SystemExit(f'FAIL wrong capture schema: {data.get("schemaVersion")}')
    if data.get('marketSlug') != EXPECTED_SLUG: raise SystemExit('FAIL capture market slug mismatch')
    try: rows,reference_only,quarantine,stats=normalize_capture(data)
    except Exception as e: raise SystemExit(f'FAIL direct PropsMadness T+A payload validation: {e}')

    captured=(data.get('requests',{}).get('market',{}).get('observedAt') or data.get('capturedAt') or now())
    for r in rows:r['captured_at']=captured
    digest=hashlib.sha256(raw).hexdigest()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); sid=f'{stamp}_{digest[:8]}'
    root=Path('/Users/abbeyfelix/Developer/MODEL')
    outdir=root/'data/raw/nfl/omega/propsmadness_ta_direct_01710'/sid
    outdir.mkdir(parents=True,exist_ok=False)
    (outdir/'PROPSMADNESS_NFL_TA_DIRECT_CAPTURE.json').write_bytes(raw)

    csvp=outdir/'OMEGA_TACKLE_MARKET_ROWS_01710.csv'
    with csvp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n');w.writeheader();w.writerows(rows)
    qp=outdir/'OMEGA_TACKLE_MARKET_QUARANTINE_01710.csv'
    with qp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=QUARANTINE_FIELDS,lineterminator='\n');w.writeheader();w.writerows(quarantine)

    rp=outdir/'OMEGA_TACKLE_MARKET_REFERENCE_ONLY_01710.csv'
    with rp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=REFERENCE_FIELDS,lineterminator='\n');w.writeheader();w.writerows(reference_only)

    audit={
      'schemaVersion':'OMEGA_PM_NFL_TA_DIRECT_ADAPTER_AUDIT_0.17.10',
      'sourceId':sid,'sourceSha256':digest,'marketSlug':EXPECTED_SLUG,
      'normalizedRows':len(rows),'referenceOnlyRows':len(reference_only),**stats,
      'books':sorted({r['book'] for r in rows}),
      'rowsWithPlayerTeam':sum(bool(r['player_team']) for r in rows),
      'rowsWithMatchId':sum(bool(r['game_id']) for r in rows),
      'twoSidedRows':sum(bool(r['over_odds_american'] and r['under_odds_american']) for r in rows),
      'oneSidedRows':sum(bool(r['one_sided_side']) for r in rows),
      'settlementResolvedRows':0,'modelFieldsPresent':False,'omegaIWritten':False,'oddsPapiRequests':0
    }
    (outdir/'OMEGA_0.17.10_PROPSMADNESS_ADAPTER_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')

    append=root/'scripts/nfl/append_omega_tackle_market_snapshot_017.py'
    compare=root/'scripts/nfl/compare_omega_tackle_market_017.py'
    if not append.exists(): raise SystemExit(f'FAIL OMEGA 0.17 append script not installed: {append}')

    print()
    print('OMEGA 0.17.10 — PROPSMADNESS NFL T+A REFERENCE-ONLY CLASSIFICATION')
    print()
    print(f'PASS endpoint rows {stats["offerCount"]} · executable {len(rows)} · reference-only {len(reference_only)} · quarantined {len(quarantine)} ({stats["quarantineRate"]:.1%})')
    if reference_only:
        from collections import Counter as _Counter
        rb=_Counter(r['sportsbook'] for r in reference_only)
        print(f'PASS explicit noOffer/referenceBet rows preserved separately: {dict(rb)}')
    if quarantine:
        print(f'PASS quarantine reasons: {stats["quarantineReasons"]}')
    print(f'PASS books {len(audit["books"])} · two-sided {audit["twoSidedRows"]} · one-sided {audit["oneSidedRows"]}')
    print(f'PASS rows with player team {audit["rowsWithPlayerTeam"]}/{len(rows)} · match id {audit["rowsWithMatchId"]}/{len(rows)}')
    print('PASS settlement unresolved by design · model fields 0 · OMEGA-I writes 0 · OddsPapi 0')
    print()

    subprocess.run([sys.executable,str(append),str(csvp),'--source','propsmadness-table-api'],check=True)

    comparison='NOT_RUN'
    if compare.exists():
        cp=subprocess.run([sys.executable,str(compare)],text=True,capture_output=True)
        print()
        print('--- OMEGA 0.17 DOWNSTREAM COMPARISON ---')
        if cp.stdout: print(cp.stdout.rstrip())
        if cp.returncode != 0:
            if cp.stderr: print(cp.stderr.rstrip())
            print(f'NOTE comparison did not complete (exit {cp.returncode}); raw immutable market snapshot remains valid.')
            comparison='BLOCKED'
        else: comparison='PASS'

    handoff=downloads/'OMEGA_01710_PROPSMADNESS_NFL_TA_ADAPTER_HANDOFF.zip'
    if handoff.exists():handoff.unlink()
    with zipfile.ZipFile(handoff,'w',zipfile.ZIP_DEFLATED) as z:
        for p in (outdir/'OMEGA_0.17.10_PROPSMADNESS_ADAPTER_AUDIT.json',
                  outdir/'PROPSMADNESS_NFL_TA_DIRECT_CAPTURE.json',csvp,rp,qp):
            z.write(p,'OMEGA_01710_HANDOFF/'+p.name)
    print()
    print(f'COMPARISON STATUS: {comparison}')
    print(f'UPLOAD: {handoff}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import csv, hashlib, importlib.util, json, math, os, shutil, sys

ROOT = Path('/Users/abbeyfelix/Developer/MODEL')
EXPECTED_SCHEMA = 'OMEGA_PM_NFL_TA_MULTIBOOK_CAPTURE_0.36.0'
EXPECTED_SLUG = 'player-tackles-assists'
RETAIL_BOOKS = {'DraftKings','FanDuel','Caesars','BetMGM','Hard Rock','Fanatics','bet365'}
SHARP_BOOKS = {'Pinnacle','Circa Sports'}

RAW_FIELDS = [
    'captured_at','player_id','player_name','player_team','opponent','match_id','game_date','away_team','home_team',
    'book','book_slug','market_slug','line','over_odds_american','under_odds_american','quote_classification','source_endpoint'
]


def nowdt(): return datetime.now(timezone.utc)
def now(): return nowdt().isoformat(timespec='seconds').replace('+00:00','Z')
def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha_path(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def num(v):
    try:
        if v in (None,''): return None
        x=float(v); return x if math.isfinite(x) else None
    except Exception: return None

def parse_ts(v):
    s=str(v or '').strip()
    if not s:return None
    try:
        d=datetime.fromisoformat(s.replace('Z','+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:return None

def iso_epoch(v):
    try:return datetime.fromtimestamp(float(v),tz=timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    except Exception:return ''

def american_profit(odds: float) -> float:
    return odds/100.0 if odds>0 else 100.0/abs(odds)

def roi(p: float|None, odds: float|None) -> float|None:
    if p is None or odds is None or not (0<=p<=1): return None
    return p*american_profit(odds) - (1-p)

def implied(odds: float) -> float:
    return 100/(odds+100) if odds>0 else abs(odds)/(abs(odds)+100)

def devig(over: float, under: float) -> tuple[float,float]:
    a,b=implied(over),implied(under); z=a+b
    return a/z,b/z

def is_half(x: float) -> bool:
    return abs((x*2)-round(x*2))<1e-8 and int(round(x*2))%2==1

def load(path: Path, name: str):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise SystemExit(f'FAIL cannot load {path}')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def extract_matches(payload: Any) -> list[dict[str,Any]]:
    if isinstance(payload,dict) and isinstance(payload.get('matches'),list):
        return [x.get('match',x) for x in payload['matches'] if isinstance(x,dict)]
    return []

def match_maps(payload: Any):
    teams={}; matches={}
    for m in extract_matches(payload):
        mid=str(m.get('id') or '')
        if not mid: continue
        h=m.get('homeTeam') if isinstance(m.get('homeTeam'),dict) else {}
        a=m.get('awayTeam') if isinstance(m.get('awayTeam'),dict) else {}
        def ab(t):
            return str(t.get('nameAbbreviation') or t.get('abbreviation') or t.get('shortName') or t.get('name') or '')
        hid,aid=str(h.get('id') or ''),str(a.get('id') or '')
        if hid: teams[hid]=ab(h)
        if aid: teams[aid]=ab(a)
        matches[mid]={
            'home_team':ab(h),'away_team':ab(a),
            'home_team_id':hid,'away_team_id':aid,
            'game_date':iso_epoch(m.get('startDateTimestamp')),
            'status':str(m.get('status') or '')
        }
    return teams,matches

def freeze_bundle():
    ptr=ROOT/'data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_DUAL_TRACK_FREEZE'
    if not ptr.exists(): raise SystemExit('FAIL current Week 2 dual-track freeze pointer missing')
    fid=ptr.read_text().strip()
    d=ROOT/'data/prospective/nfl/omega_week2_dual_track_0330'/fid
    dual=d/'OMEGA_0.33_WEEK2_DUAL_TRACK.csv'
    hashes=d/'OMEGA_OUTPUT_HASHES.json'
    if not dual.exists() or not hashes.exists(): raise SystemExit('FAIL incomplete Week 2 freeze bundle')
    hm=json.loads(hashes.read_text())
    if sha_path(dual)!=str(hm.get(dual.name) or ''): raise SystemExit('FAIL Week 2 freeze hash mismatch')
    with dual.open(newline='',encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    return fid,rows,sha_path(dual)

def model_probability(row: dict[str,str], prefix: str, side: str, line: float) -> float:
    tag=str(float(line)).replace('.','_')
    key=f'{prefix}p_{side.lower()}_{tag}'
    x=num(row.get(key))
    if x is None or not (0<=x<=1): raise ValueError(f'missing model probability {key}')
    return x

def best_side(po,pu,oo,uo):
    vals=[]
    if oo is not None: vals.append(('OVER',roi(po,oo)))
    if uo is not None: vals.append(('UNDER',roi(pu,uo)))
    vals=[x for x in vals if x[1] is not None]
    return max(vals,key=lambda z:z[1]) if vals else ('',None)

def queue_class(role, agree, ev):
    if ev is None or ev<=0: return 'NONPOSITIVE_CONTROL_EV'
    if role=='REVIEW_BACKUP_CONFLICT': return 'BACKUP_CONFLICT_QUARANTINE'
    if role=='STARTER_CONFLICT_REVIEW': return 'STARTER_CONFLICT_REVIEW'
    if role=='NO_DEPTH_FALLBACK_H012': return 'NO_DEPTH_REVIEW'
    if role=='ROLE_ALIGNED' and agree: return 'PRIMARY_DIRECT_VERIFY'
    if role=='ROLE_ALIGNED' and not agree: return 'TRACK_DISAGREEMENT_REVIEW'
    return 'OTHER_REVIEW'

def main() -> int:
    downloads=Path.home()/'Downloads'
    caps=sorted(downloads.glob('OMEGA_0360_PROPSMADNESS_NFL_TA_MULTIBOOK_*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if not caps: raise SystemExit('FAIL no OMEGA 0.36 multibook capture found in ~/Downloads')
    src=caps[0]; raw=src.read_bytes(); digest=sha_bytes(raw)
    try:data=json.loads(raw)
    except Exception as e: raise SystemExit(f'FAIL capture invalid JSON: {e}')
    if data.get('schemaVersion')!=EXPECTED_SCHEMA: raise SystemExit(f'FAIL wrong capture schema {data.get("schemaVersion")}')
    if data.get('fatalError'): raise SystemExit(f'FAIL browser capture fatalError: {data.get("fatalError")}')
    req=data.get('requests') or {}
    disc=req.get('discovery') or {}; mreq=req.get('matches') or {}
    if disc.get('ok') is not True or mreq.get('ok') is not True: raise SystemExit('FAIL discovery/matches request not HTTP OK')
    dpay=disc.get('data'); mpay=mreq.get('data')
    if not isinstance(dpay,dict) or not isinstance(dpay.get('offers'),list): raise SystemExit('FAIL discovery offers[] missing')
    if ((dpay.get('market') or {}).get('slug') not in (None,'',EXPECTED_SLUG)): raise SystemExit('FAIL discovery market slug mismatch')
    teams,matches=match_maps(mpay)
    if len(matches)!=16: raise SystemExit(f'FAIL expected 16 Week 2 matches from PropsMadness; got {len(matches)}')

    player_requests=data.get('playerMarketRequests')
    if not isinstance(player_requests,list) or not player_requests: raise SystemExit('FAIL playerMarketRequests missing/empty')
    failed=[x for x in player_requests if not isinstance(x,dict) or (x.get('response') or {}).get('ok') is not True]
    if failed: raise SystemExit(f'FAIL {len(failed)}/{len(player_requests)} per-player multibook requests failed; recapture rather than accept partial board')

    rows=[]; unavailable=0; bad_market=0
    for pr in player_requests:
        pid=str(pr.get('playerId') or ''); mid=str(pr.get('matchId') or ''); pname=str(pr.get('playerName') or '')
        tid=str(pr.get('teamId') or ''); pteam=teams.get(tid,''); mm=matches.get(mid,{})
        home,away=mm.get('home_team',''),mm.get('away_team','')
        opp=away if pteam==home else home if pteam==away else ''
        response=pr.get('response') or {}; captured=response.get('observedAt') or data.get('capturedAt') or now()
        payload=response.get('data')
        bets=payload.get('bets') if isinstance(payload,dict) else None
        if not isinstance(bets,list): raise SystemExit(f'FAIL player {pname or pid} multibook response lacks bets[]')
        for b in bets:
            if not isinstance(b,dict): continue
            market=b.get('market') if isinstance(b.get('market'),dict) else {}
            if market.get('slug')!=EXPECTED_SLUG:
                bad_market+=1; continue
            book=b.get('sportsbook') if isinstance(b.get('sportsbook'),dict) else {}
            line=num(b.get('line')); odds=b.get('odds') if isinstance(b.get('odds'),dict) else {}
            oo=num(odds.get('over')); uo=num(odds.get('under'))
            if line is None or (oo is None and uo is None): unavailable+=1; continue
            rows.append({
                'captured_at':captured,'player_id':pid,'player_name':pname,'player_team':pteam,'opponent':opp,
                'match_id':mid,'game_date':mm.get('game_date',''),'away_team':away,'home_team':home,
                'book':str(book.get('name') or ''),'book_slug':str(book.get('slug') or ''),'market_slug':EXPECTED_SLUG,
                'line':line,'over_odds_american':'' if oo is None else oo,'under_odds_american':'' if uo is None else uo,
                'quote_classification':'PROPSMADNESS_AGGREGATED_BOOK_QUOTE_NOT_DIRECT_VERIFIED',
                'source_endpoint':str(pr.get('endpoint') or '')
            })
    if not rows: raise SystemExit('FAIL no non-null multibook T+A quotes normalized')

    stamp=nowdt().strftime('%Y%m%dT%H%M%SZ'); sid=f'{stamp}_{digest[:8]}'
    raw_base=ROOT/'data/raw/nfl/omega/propsmadness_ta_multibook_0360'; final=raw_base/sid; st=raw_base/('.'+sid+'.staging')
    raw_base.mkdir(parents=True,exist_ok=True)
    if final.exists(): raise SystemExit(f'FAIL immutable raw multibook snapshot exists: {final}')
    st.mkdir(parents=True,exist_ok=False)
    try:
        (st/'PROPSMADNESS_NFL_TA_MULTIBOOK_CAPTURE.json').write_bytes(raw)
        qp=st/'OMEGA_0.36_MULTIBOOK_QUOTES.csv'
        with qp.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=RAW_FIELDS,lineterminator='\n'); w.writeheader(); w.writerows(rows)
        audit={
            'schemaVersion':'OMEGA_PM_NFL_TA_MULTIBOOK_AUDIT_0.36.0','snapshotId':sid,'createdAt':now(),
            'sourceSha256':digest,'playerMarketRequests':len(player_requests),'failedPlayerRequests':0,
            'normalizedQuoteRows':len(rows),'nullOrUnavailableBookRows':unavailable,'wrongMarketRows':bad_market,
            'books':sorted({r['book'] for r in rows}),'players':len({(r['player_id'],r['match_id']) for r in rows}),
            'matches':len({r['match_id'] for r in rows}),'sharpBooksObserved':sorted(SHARP_BOOKS & {r['book'] for r in rows}),
            'alternateLineRequests':0,'modelFieldsPresent':False,'oddsPapiRequests':0,
            'quoteClassification':'PROPSMADNESS_AGGREGATED_BOOK_QUOTE_NOT_DIRECT_VERIFIED'
        }
        (st/'OMEGA_0.36_MULTIBOOK_CAPTURE_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
        os.replace(st,final)
        (ROOT/'data/raw/nfl/omega/CURRENT_OMEGA_TA_MULTIBOOK_0360').write_text(sid+'\n')
    except BaseException:
        shutil.rmtree(st,ignore_errors=True); raise

    # Downstream comparison against immutable Week 2 freeze.
    fid,forecasts,dual_sha=freeze_bundle()
    h=load(ROOT/'scripts/nfl/compare_omega_tackle_market_0180.py','omega018_helpers')
    indexes=h.build_indexes(forecasts)
    comp=[]; unmatched=[]; unsupported=[]; postkick=[]
    for m in rows:
        market_row={'player_name':m['player_name'],'player_team':m['player_team'],'opponent':m['opponent'],'game_id':m['match_id'],'book':m['book'],'line':m['line']}
        cand,method=h.resolve_market_identity(market_row,indexes)
        if len(cand)!=1:
            unmatched.append({**m,'join_method':method,'candidate_count':len(cand)}); continue
        p=cand[0]; line=float(m['line'])
        if not is_half(line) or line<0.5 or line>14.5:
            unsupported.append({**m,'reason':'UNSUPPORTED_LINE'}); continue
        mt=parse_ts(m['captured_at']); ko=parse_ts(p.get('kickoff_utc'))
        if mt is None or ko is None or mt>=ko:
            postkick.append({**m,'kickoff_utc':p.get('kickoff_utc'),'reason':'MISSING_TIME_OR_POSTKICK'}); continue
        try:
            cpo=model_probability(p,'control_','over',line); cpu=model_probability(p,'control_','under',line)
            rpo=model_probability(p,'role_shadow_','over',line); rpu=model_probability(p,'role_shadow_','under',line)
        except ValueError as e:
            unsupported.append({**m,'reason':str(e)}); continue
        oo=num(m['over_odds_american']); uo=num(m['under_odds_american'])
        cb,cev=best_side(cpo,cpu,oo,uo); rb,rev=best_side(rpo,rpu,oo,uo)
        rec={
            'freeze_id':fid,'freeze_sha256':dual_sha,'market_snapshot_id':sid,'market_captured_at':m['captured_at'],
            'game_id':p.get('game_id'),'kickoff_utc':p.get('kickoff_utc'),'player_id':p.get('player_id'),'player_name':p.get('player_name'),
            'team':p.get('team'),'opponent':p.get('opponent'),'position_group':p.get('position_group'),'book':m['book'],'book_slug':m['book_slug'],
            'line':line,'over_odds_american':m['over_odds_american'],'under_odds_american':m['under_odds_american'],
            'two_sided':'TRUE' if oo is not None and uo is not None else 'FALSE',
            'control_p_over':cpo,'control_p_under':cpu,'role_shadow_p_over':rpo,'role_shadow_p_under':rpu,
            'control_over_ev':roi(cpo,oo),'control_under_ev':roi(cpu,uo),'role_shadow_over_ev':roi(rpo,oo),'role_shadow_under_ev':roi(rpu,uo),
            'control_best_side':cb,'control_best_ev':cev,'role_shadow_best_side':rb,'role_shadow_best_ev':rev,
            'tracks_agree_side':'TRUE' if cb and cb==rb else 'FALSE','role_state':p.get('role_state'),
            'control_xtc':p.get('control_xtc'),'role_point_xtc':p.get('role_point_xtc'),
            'control_h012_snap_share':p.get('control_h012_snap_share'),'role_point_snap_share':p.get('role_point_snap_share'),
            'identity_join_method':method,'quote_classification':m['quote_classification'],
            'operational_status':'AGGREGATED_BOOK_QUOTE_VERIFY_AT_BOOK'
        }
        if oo is not None and uo is not None:
            nv_o,nv_u=devig(oo,uo); rec['book_novig_over']=nv_o; rec['book_novig_under']=nv_u
        comp.append(rec)
    if not comp: raise SystemExit('FAIL no multibook quotes matched Week 2 frozen forecasts')

    # Strict same-line sharp reference only; never interpolate across different lines.
    groups={}
    for r in comp: groups.setdefault((r['player_id'],float(r['line'])),[]).append(r)
    sharp_rows=[]
    for key,grp in groups.items():
        refs=[]
        for r in grp:
            if r['book'] not in SHARP_BOOKS or r.get('book_novig_over') in (None,''): continue
            refs.append(r)
        if not refs: continue
        over=sum(float(r['book_novig_over']) for r in refs)/len(refs); under=1-over
        sharp_rows.append({
            'game_id':refs[0]['game_id'],'player_id':refs[0]['player_id'],'player_name':refs[0]['player_name'],'team':refs[0]['team'],
            'line':refs[0]['line'],'sharp_books':'|'.join(sorted(r['book'] for r in refs)),
            'sharp_book_count':len(refs),'sharp_consensus_over':over,'sharp_consensus_under':under,
            'same_line_rule':'EXACT_LINE_ONLY_NO_INTERPOLATION'
        })
        for r in grp:
            r['sharp_same_line_books']='|'.join(sorted(x['book'] for x in refs)); r['sharp_same_line_count']=len(refs)
            r['sharp_consensus_over']=over; r['sharp_consensus_under']=under
            r['control_edge_vs_sharp_over']=float(r['control_p_over'])-over
            r['control_edge_vs_sharp_under']=float(r['control_p_under'])-under

    # Best retail quote per player, based on frozen-control EV across available line/price combinations.
    best_by_player={}
    for r in comp:
        if r['book'] not in RETAIL_BOOKS: continue
        ev=num(r.get('control_best_ev'))
        if ev is None: continue
        k=r['player_id']
        if k not in best_by_player or ev>num(best_by_player[k].get('control_best_ev')):
            best_by_player[k]=r
    candidates=[]
    for r in best_by_player.values():
        ev=num(r.get('control_best_ev')); agree=str(r.get('tracks_agree_side'))=='TRUE'; role=str(r.get('role_state') or '')
        q=queue_class(role,agree,ev)
        x=dict(r); x['queue_class']=q; x['direct_book_verification_required']='TRUE'; candidates.append(x)
    order={'PRIMARY_DIRECT_VERIFY':0,'STARTER_CONFLICT_REVIEW':1,'TRACK_DISAGREEMENT_REVIEW':2,'NO_DEPTH_REVIEW':3,'BACKUP_CONFLICT_QUARANTINE':4,'OTHER_REVIEW':5,'NONPOSITIVE_CONTROL_EV':6}
    candidates.sort(key=lambda r:(order.get(r['queue_class'],99),-(num(r.get('control_best_ev')) or -999)))

    cid=f"{nowdt().strftime('%Y%m%dT%H%M%SZ')}_{hashlib.sha256((sid+dual_sha).encode()).hexdigest()[:8]}"
    base=ROOT/'data/prospective/nfl/omega_week2_multibook_comparison_0360'; fd=base/cid; fs=base/('.'+cid+'.staging'); fs.mkdir(parents=True,exist_ok=False)
    def wcsv(name,rr):
        fields=[]
        for row in rr:
            for k in row:
                if k not in fields: fields.append(k)
        if not fields: fields=['status']
        with (fs/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n'); w.writeheader(); w.writerows(rr)
    try:
        wcsv('OMEGA_0.36_MULTIBOOK_ALL_QUOTES.csv',comp)
        wcsv('OMEGA_0.36_BEST_RETAIL_CANDIDATES.csv',candidates)
        wcsv('OMEGA_0.36_SHARP_SAME_LINE_REFERENCE.csv',sharp_rows)
        wcsv('OMEGA_0.36_UNMATCHED.csv',unmatched); wcsv('OMEGA_0.36_UNSUPPORTED.csv',unsupported); wcsv('OMEGA_0.36_POSTKICK_EXCLUDED.csv',postkick)
        audit={
            'schemaVersion':'OMEGA_WEEK2_MULTIBOOK_COMPARISON_0.36.0','comparisonId':cid,'createdAt':now(),'freezeId':fid,'marketSnapshotId':sid,
            'quoteRows':len(comp),'bestRetailCandidateRows':len(candidates),'primaryDirectVerifyRows':sum(r['queue_class']=='PRIMARY_DIRECT_VERIFY' for r in candidates),
            'starterReviewRows':sum(r['queue_class']=='STARTER_CONFLICT_REVIEW' for r in candidates),'backupQuarantineRows':sum(r['queue_class']=='BACKUP_CONFLICT_QUARANTINE' for r in candidates),
            'sharpSameLineRows':len(sharp_rows),'unmatchedRows':len(unmatched),'unsupportedRows':len(unsupported),'postKickExcludedRows':len(postkick),
            'retailBooks':sorted(RETAIL_BOOKS),'sharpBooks':sorted(SHARP_BOOKS),'sharpConsensusRule':'EXACT_SAME_LINE_DEVIG_AVERAGE_ONLY_NO_INTERPOLATION',
            'decisionProbabilityTrack':'FROZEN_OMEGA_CONTROL','roleProbabilityStatus':'SHADOW_ONLY_NOT_PROMOTED',
            'marketQuoteStatus':'PROPSMADNESS_AGGREGATED_NOT_DIRECT_BOOK_VERIFIED','alternateLineRequests':0,'modelRefits':0,'modelWrites':0,'oddsPapiRequests':0
        }
        (fs/'OMEGA_0.36_MULTIBOOK_COMPARISON_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
        (fs/'OMEGA_OUTPUT_HASHES.json').write_text(json.dumps({p.name:sha_path(p) for p in fs.iterdir() if p.is_file()},indent=2)+'\n')
        os.replace(fs,fd)
        (ROOT/'data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_MULTIBOOK_COMPARISON').write_text(cid+'\n')
    except BaseException:
        shutil.rmtree(fs,ignore_errors=True); raise

    primary=[r for r in candidates if r['queue_class']=='PRIMARY_DIRECT_VERIFY']
    print('OMEGA 0.36 — WEEK 2 PROPSMADNESS MULTIBOOK MAIN-LINE CAPTURE + COMPARISON')
    print(f'PASS player requests {len(player_requests)} · normalized book quotes {len(rows)} · books {len({r["book"] for r in rows})} · games {len({r["match_id"] for r in rows})}')
    print(f'PASS comparison rows {len(comp)} · unmatched {len(unmatched)} · unsupported {len(unsupported)} · postkick {len(postkick)}')
    print(f'PASS sharp same-line reference rows {len(sharp_rows)} · sharp books observed {sorted(SHARP_BOOKS & {r["book"] for r in rows})}')
    print(f'PRIMARY DIRECT VERIFY {len(primary)} · STARTER REVIEW {sum(r["queue_class"]=="STARTER_CONFLICT_REVIEW" for r in candidates)} · BACKUP QUARANTINE {sum(r["queue_class"]=="BACKUP_CONFLICT_QUARANTINE" for r in candidates)}')
    print('PASS all prices labeled PropsMadness aggregated/not directly verified · full alternate ladders NOT requested')
    print('PASS frozen control unchanged · role probability shadow-only · model refits/writes 0 · OddsPapi 0')
    print('TOP BEST-RETAIL CANDIDATES — VERIFY AT BOOK BEFORE DECISION:')
    for r in primary[:20]:
        ev=100*float(r['control_best_ev']); rev=num(r.get('role_shadow_best_ev')); revs='NA' if rev is None else f'{100*rev:+.1f}%'
        sharp=''
        if r.get('sharp_same_line_count') not in (None,''):
            sharp=f" · sharp {r.get('sharp_same_line_books')} same-line"
        print(f"  {r['game_id']} · {r['player_name']} {r['control_best_side']} {r['line']} {r['book']} · CONTROL EV {ev:+.1f}% · ROLE {r['role_shadow_best_side']} {revs} · {r['role_state']}{sharp}")
    print(f'RAW SNAPSHOT: {final}')
    print(f'REPORT: {fd/"OMEGA_0.36_MULTIBOOK_COMPARISON_AUDIT.json"}')
    print(f'BEST RETAIL: {fd/"OMEGA_0.36_BEST_RETAIL_CANDIDATES.csv"}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""OMEGA 0.18.0 downstream market comparison with explicit PropsMadness→GSIS identity bridge.

Important:
- PropsMadness numeric player IDs are provider-local and are NOT GSIS IDs.
- Matching is deterministic only: canonical player name + canonical NFL team,
  then canonical name + opponent, then exact canonical-name unique fallback.
- No fuzzy/edit-distance matching.
- OMEGA-I and raw market snapshots remain read-only.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,math,os,re,shutil,unicodedata

EXPECTED_WEEK1_LEDGER='fe4991a743a1c02994b59d473a1bec9a1ccafa61a60548df43f2f5292e4ca08a'

TEAM_GROUPS = {
 'CARDINALS': ['ARI','ARIZONA','ARIZONACARDINALS'],
 'FALCONS': ['ATL','ATLANTA','ATLANTAFALCONS'],
 'RAVENS': ['BAL','BALTIMORE','BALTIMORERAVENS'],
 'BILLS': ['BUF','BUFFALO','BUFFALOBILLS'],
 'PANTHERS': ['CAR','CAROLINA','CAROLINAPANTHERS'],
 'BEARS': ['CHI','CHICAGO','CHICAGOBEARS'],
 'BENGALS': ['CIN','CINCINNATI','CINCINNATIBENGALS'],
 'BROWNS': ['CLE','CLEVELAND','CLEVELANDBROWNS'],
 'COWBOYS': ['DAL','DALLAS','DALLASCOWBOYS'],
 'BRONCOS': ['DEN','DENVER','DENVERBRONCOS'],
 'LIONS': ['DET','DETROIT','DETROITLIONS'],
 'PACKERS': ['GB','GNB','GREENBAY','GREENBAYPACKERS'],
 'TEXANS': ['HOU','HOUSTON','HOUSTONTEXANS'],
 'COLTS': ['IND','INDIANAPOLIS','INDIANAPOLISCOLTS'],
 'JAGUARS': ['JAX','JAC','JACKSONVILLE','JACKSONVILLEJAGUARS'],
 'CHIEFS': ['KC','KAN','KANSASCITY','KANSASCITYCHIEFS'],
 'RAIDERS': ['LV','LVR','LASVEGAS','LASVEGASRAIDERS','OAK'],
 'CHARGERS': ['LAC','LOSANGELESCHARGERS','LACHARGERS','SD'],
 'RAMS': ['LA','LAR','LOSANGELESRAMS','LARAMS','STL'],
 'DOLPHINS': ['MIA','MIAMI','MIAMIDOLPHINS'],
 'VIKINGS': ['MIN','MINNESOTA','MINNESOTAVIKINGS'],
 'PATRIOTS': ['NE','NWE','NEWENGLAND','NEWENGLANDPATRIOTS'],
 'SAINTS': ['NO','NOR','NEWORLEANS','NEWORLEANSSAINTS'],
 'GIANTS': ['NYG','NEWYORKGIANTS','NYGIANTS'],
 'JETS': ['NYJ','NEWYORKJETS','NYJETS'],
 'EAGLES': ['PHI','PHILADELPHIA','PHILADELPHIAEAGLES'],
 'STEELERS': ['PIT','PITTSBURGH','PITTSBURGHSTEELERS'],
 'SEAHAWKS': ['SEA','SEATTLE','SEATTLESEAHAWKS'],
 '49ERS': ['SF','SFO','SANFRANCISCO','SANFRANCISCO49ERS','49ERS'],
 'BUCCANEERS': ['TB','TAM','TAMPABAY','TAMPABAYBUCCANEERS','BUCS'],
 'TITANS': ['TEN','TENNESSEE','TENNESSEETITANS'],
 'COMMANDERS': ['WAS','WSH','WASHINGTON','WASHINGTONCOMMANDERS','WASHINGTONFOOTBALLTEAM']
}
TEAM_ALIAS={}
for canon,aliases in TEAM_GROUPS.items():
    for a in aliases:
        TEAM_ALIAS[re.sub(r'[^A-Z0-9]','',a.upper())]=canon

SUFFIXES={'JR','JUNIOR','SR','SENIOR','II','III','IV','V'}

# Explicit, provider-observed display-name aliases.
# Keys are (canonical PropsMadness display name, canonical NFL franchise).
# These are intentionally narrow and team-scoped; no generic nickname expansion.
EXPLICIT_PROVIDER_NAME_ALIASES = {
    ('FOYESADEOLUOKUN','JAGUARS'): 'FOYEOLUOKUN',
    ('JOSHUAMETELLUS','VIKINGS'): 'JOSHMETELLUS',
}


# Book-specific settlement policies verified against current official sources on 2026-09-11.
# Novig is intentionally unresolved on special-teams inclusion because the current official
# public materials verified here do not state that point for NFL T+A.
SETTLEMENT_POLICIES = {
    'DRAFTKINGS': {
        'status': 'RESOLVED',
        'settlement_scope': 'DEFENSIVE_PLAYS_ONLY_TACKLES_PLUS_ASSISTS',
        'includes_special_teams': 'FALSE',
        'stat_correction_policy': 'OFFICIAL_STAT_PROVIDER_AT_INITIAL_SETTLEMENT; DRAFTKINGS_RESERVES_RESETTLEMENT_RIGHT',
        'participation_policy': 'PLAYER_MUST_PARTICIPATE_IN_AT_LEAST_ONE_PLAY',
        'source_urls': [
            'https://sportsbook.draftkings.com/help/sport-rules/football',
            'https://sportsbook.draftkings.com/help/general-betting-rules/general-rules'
        ],
        'evidence_note': 'DraftKings football rules say defensive-stat markets count only defensive plays and exclude special teams; general rules use official statistical provider/governing-body data and allow resettlement.'
    },
    'UNDERDOGFANTASY': {
        'status': 'RESOLVED',
        'settlement_scope': 'SOLO_TACKLES_PLUS_ASSISTS_OFFICIAL_NFL_STATS',
        'includes_special_teams': 'FALSE',
        'stat_correction_policy': 'OFFICIAL_LEAGUE_STATS_AT_SETTLEMENT; LATER_CORRECTIONS_TYPICALLY_DO_NOT_CHANGE_FINALIZED_RESULTS; DISCRETIONARY_REVISION_RESERVED',
        'participation_policy': 'OFFICIALLY_INACTIVE_PICK_VOID',
        'source_urls': [
            'https://help.underdogsports.com/en/articles/8974214-pick-em-scoring-nfl',
            'https://help.underdogsports.com/en/articles/8923398-how-long-does-it-take-to-finalize-results',
            'https://help.underdogsports.com/en/articles/11146189-what-happens-if-my-player-gets-injured'
        ],
        'evidence_note': 'Underdog NFL Pick’em defines Tackles + Assist as solo tackles plus assists and excludes special-teams stats from Pick’em unless special-teams specific.'
    },
    'NOVIG': {
        'status': 'PARTIAL_UNRESOLVED_SPECIAL_TEAMS',
        'settlement_scope': 'OFFICIAL_LEAGUE_STATISTICS_PLAYER_PROP',
        'includes_special_teams': 'UNKNOWN',
        'stat_correction_policy': 'OFFICIAL_STATS_AT_GRADING; NO_REGRADE_FOR_LATER_OFFICIAL_STAT_CORRECTIONS',
        'participation_policy': 'NON_PARTICIPATION_PUSH_OR_VOID_PER_CONTRACT/FVS_RULES',
        'source_urls': [
            'https://support.novig.com/en/articles/16194045-how-does-settlement-work',
            'https://support.novig.com/en/articles/10336135-how-settlement-works-grading-disputes-and-voided-trades'
        ],
        'evidence_note': 'Novig confirms official league/stat-provider settlement and no re-grade after later stat corrections, but current public official materials verified here do not resolve NFL T+A special-teams inclusion.'
    }
}

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def rcsv(p):
    with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def ascii_fold(s):
    return unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode('ascii')
def canon_name(s):
    x=ascii_fold(s).upper()
    toks=re.findall(r'[A-Z0-9]+',x)
    while toks and toks[-1] in SUFFIXES:toks.pop()
    return ''.join(toks)
def canon_team(s):
    raw=re.sub(r'[^A-Z0-9]','',ascii_fold(s).upper())
    return TEAM_ALIAS.get(raw,raw)

def canon_book(s):
    return re.sub(r'[^A-Z0-9]','',ascii_fold(s).upper())

def settlement_policy_for_book(book):
    key=canon_book(book)
    if key in SETTLEMENT_POLICIES:
        return SETTLEMENT_POLICIES[key]
    return {
        'status':'UNRESOLVED_UNKNOWN_BOOK',
        'settlement_scope':'UNKNOWN',
        'includes_special_teams':'UNKNOWN',
        'stat_correction_policy':'UNKNOWN',
        'participation_policy':'UNKNOWN',
        'source_urls':[],
        'evidence_note':'No verified OMEGA settlement policy for this book.'
    }

def alias_market_name(name, team):
    n=canon_name(name)
    t=canon_team(team)
    return EXPLICIT_PROVIDER_NAME_ALIASES.get((n,t),n)
def num(s):
    try:return float(s)
    except:return None
def american_break_even(a):
    a=float(a)
    if a==0:raise ValueError('zero American odds')
    return (-a)/((-a)+100) if a<0 else 100/(a+100)
def roi(p,a):
    a=float(a);profit=100/abs(a) if a<0 else a/100
    return p*profit-(1-p)
def devig(a,b):
    x=american_break_even(a);y=american_break_even(b);t=x+y
    return x/t,y/t
def is_half(line):return abs((float(line)*2)-round(float(line)*2))<1e-9 and int(round(float(line)*2))%2==1
def tag(line):return str(float(line)).replace('.','_')
def settlement_resolved(r):
    # Raw capture remains immutable and intentionally unresolved.
    # Resolution is supplied only by the downstream verified book-policy overlay.
    policy=settlement_policy_for_book(r.get('book'))
    return policy.get('status')=='RESOLVED'

def build_indexes(rows):
    by_name_team={}
    by_name_opp={}
    by_name={}
    for r in rows:
        n=canon_name(r.get('player_name'))
        t=canon_team(r.get('team'))
        o=canon_team(r.get('opponent'))
        if n:
            by_name.setdefault(n,[]).append(r)
            if t:by_name_team.setdefault((n,t),[]).append(r)
            if o:by_name_opp.setdefault((n,o),[]).append(r)
    return by_name_team,by_name_opp,by_name

def resolve_market_identity(m,indexes):
    by_name_team,by_name_opp,by_name=indexes
    raw_n=canon_name(m.get('player_name'))
    t=canon_team(m.get('player_team'))
    o=canon_team(m.get('opponent'))
    n=alias_market_name(m.get('player_name'),m.get('player_team'))
    alias_used=(n != raw_n)
    if not n:
        return [],'NO_CANONICAL_NAME'
    c=by_name_team.get((n,t),[]) if t else []
    if len(c)==1:return c,('EXPLICIT_ALIAS_NAME_TEAM' if alias_used else 'CANON_NAME_TEAM')
    if len(c)>1 and o:
        z=[r for r in c if canon_team(r.get('opponent'))==o]
        if len(z)==1:return z,('EXPLICIT_ALIAS_NAME_TEAM_OPP' if alias_used else 'CANON_NAME_TEAM_OPP')
        return z or c,'AMBIG_CANON_NAME_TEAM'
    if o:
        c=by_name_opp.get((n,o),[])
        if len(c)==1:return c,('EXPLICIT_ALIAS_NAME_OPP' if alias_used else 'CANON_NAME_OPP')
        if len(c)>1:return c,'AMBIG_CANON_NAME_OPP'
    c=by_name.get(n,[])
    if len(c)==1:return c,('EXPLICIT_ALIAS_NAME_UNIQUE' if alias_used else 'CANON_NAME_UNIQUE')
    if len(c)>1:return c,'AMBIG_CANON_NAME'
    return [],'UNMATCHED_CANON_NAME'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--allow-ledger-hash',default=EXPECTED_WEEK1_LEDGER)
    a=ap.parse_args();root=Path(a.root).resolve()

    lp=root/'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER'
    mp=root/'data/raw/nfl/omega/CURRENT_MARKET_SNAPSHOT'
    if not lp.exists():raise SystemExit('FAIL no current OMEGA probability ledger pointer')
    if not mp.exists():raise SystemExit('FAIL no current raw market snapshot pointer')

    lid=lp.read_text().strip()
    ld=root/'data/prospective/nfl/omega/tackle_probability_016'/lid
    ledger=ld/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv'
    hp=ld/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.sha256'
    if not ledger.exists() or not hp.exists():raise SystemExit('FAIL probability ledger/hash missing')
    actual=sha(ledger);recorded=hp.read_text().strip()
    if actual!=recorded:raise SystemExit('FAIL OMEGA-I ledger hash mismatch')
    if a.allow_ledger_hash and actual!=a.allow_ledger_hash:
        raise SystemExit(f'FAIL unexpected OMEGA-I ledger hash {actual}; expected {a.allow_ledger_hash}')

    mid=mp.read_text().strip()
    md=root/'data/raw/nfl/omega/market_snapshots'/mid
    market=md/'normalized_market_rows.csv'
    mm=md/'MARKET_SNAPSHOT_MANIFEST.json'
    if not market.exists() or not mm.exists():raise SystemExit('FAIL market snapshot incomplete')
    mmeta=json.loads(mm.read_text())
    if mmeta.get('modelFieldsPresent') is not False or int(mmeta.get('oddsPapiRequests',0))!=0:
        raise SystemExit('FAIL raw-market integrity contract')

    lr=rcsv(ledger)
    mr=[r for r in rcsv(market) if str(r.get('market_kind') or '').lower()=='tackles_assists']
    indexes=build_indexes(lr)

    out=[];unmatched=[];ambig=[];unsupported=[];methods={}
    for m in mr:
        cand,method=resolve_market_identity(m,indexes)
        methods[method]=methods.get(method,0)+1
        if len(cand)==0:
            unmatched.append({
                'market_player_id':m.get('player_id'),'market_player_name':m.get('player_name'),
                'market_team':m.get('player_team'),'market_opponent':m.get('opponent'),
                'canonical_name':canon_name(m.get('player_name')),
                'canonical_team':canon_team(m.get('player_team')),
                'canonical_opponent':canon_team(m.get('opponent')),
                'join_method':method
            })
            continue
        if len(cand)!=1:
            ambig.append({
                'market_player_name':m.get('player_name'),'market_team':m.get('player_team'),
                'candidate_count':len(cand),'candidate_names':'|'.join(str(x.get('player_name')) for x in cand),
                'candidate_teams':'|'.join(str(x.get('team')) for x in cand),'join_method':method
            })
            continue

        l=num(m.get('line'))
        if l is None or not is_half(l) or l<0.5 or l>14.5:
            unsupported.append({'player_name':m.get('player_name'),'line':m.get('line'),'reason':'UNSUPPORTED_LINE'})
            continue

        p=cand[0];t=tag(l)
        po=num(p.get('p_over_'+t));pu=num(p.get('p_under_'+t))
        if po is None or pu is None:
            unsupported.append({'player_name':m.get('player_name'),'line':m.get('line'),'reason':'MISSING_MODEL_THRESHOLD'})
            continue

        over=num(m.get('over_odds_american'));under=num(m.get('under_odds_american'))
        side=str(m.get('one_sided_side') or '').upper();one=num(m.get('one_sided_odds_american'))
        policy=settlement_policy_for_book(m.get('book'))
        row={
            'model_ledger_id':lid,'model_ledger_sha256':actual,'market_snapshot_id':mid,
            'market_captured_at':m.get('captured_at'),'book':m.get('book'),
            'settlement_policy_status':policy.get('status'),
            'settlement_scope':policy.get('settlement_scope'),
            'includes_special_teams':policy.get('includes_special_teams'),
            'stat_correction_policy':policy.get('stat_correction_policy'),
            'participation_policy':policy.get('participation_policy'),
            'settlement_policy_sources':'|'.join(policy.get('source_urls') or []),
            'market_player_id':m.get('player_id'),'market_player_name':m.get('player_name'),
            'market_player_team':m.get('player_team'),'identity_join_method':method,
            'game_id_model':p.get('game_id'),'player_id':p.get('player_id'),
            'player_name':p.get('player_name'),'team':p.get('team'),'opponent':p.get('opponent'),
            'line':f'{l:.1f}','predicted_xtc':p.get('predicted_xtc'),
            'predicted_snap_share':p.get('predicted_snap_share'),
            'distribution_role_tier':p.get('distribution_role_tier'),
            'model_p_over':po,'model_p_under':pu,
            'model_fair_over':p.get('fair_over_'+t),'model_fair_under':p.get('fair_under_'+t),
            'verified_ready':p.get('verified_ready'),'verified_block_reason':p.get('verified_block_reason'),
            'settlement_resolved':'TRUE' if settlement_resolved(m) else 'FALSE',
            'market_reference_quality':'TWO_SIDED_NO_VIG' if over is not None and under is not None else 'ONE_SIDED_EV_ONLY'
        }
        if over is not None:
            row['over_price']=over;row['over_break_even']=american_break_even(over)
            row['over_roi']=roi(po,over);row['over_prob_edge']=po-row['over_break_even']
        if under is not None:
            row['under_price']=under;row['under_break_even']=american_break_even(under)
            row['under_roi']=roi(pu,under);row['under_prob_edge']=pu-row['under_break_even']
        if over is not None and under is not None:
            no,nu=devig(over,under)
            row['market_novig_over']=no;row['market_novig_under']=nu
            row['model_vs_novig_over']=po-no;row['model_vs_novig_under']=pu-nu
        elif one is not None and side in {'OVER','UNDER'}:
            ps=po if side=='OVER' else pu
            row['one_sided_side']=side;row['one_sided_price']=one
            row['one_sided_break_even']=american_break_even(one)
            row['one_sided_roi']=roi(ps,one);row['one_sided_prob_edge']=ps-row['one_sided_break_even']

        blockers=[]
        if str(p.get('verified_ready')).upper()!='TRUE':blockers.append('AVAILABILITY_UNVERIFIED')
        if not settlement_resolved(m):blockers.append('SETTLEMENT_UNRESOLVED')
        row['actionability']='NON_ACTIONABLE' if blockers else 'RESEARCH_READY_ONLY'
        row['actionability_blockers']='|'.join(blockers)
        out.append(row)

    if not out:
        print('OMEGA 0.18.0 — IDENTITY BRIDGE DIAGNOSTIC')
        print(f'FAIL no comparable T+A rows · unmatched {len(unmatched)} · ambiguous {len(ambig)} · unsupported {len(unsupported)}')
        print('JOIN METHODS:',json.dumps(methods,sort_keys=True))
        for x in unmatched[:12]:
            print('UNMATCHED:',json.dumps(x,sort_keys=True))
        for x in ambig[:8]:
            print('AMBIG:',json.dumps(x,sort_keys=True))
        raise SystemExit(1)

    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    sid=f'{stamp}_{actual[:8]}_{mid[-8:]}'
    base=root/'data/prospective/nfl/omega/market_comparison_0180'
    final=base/sid;st=base/('.'+sid+'.staging')
    base.mkdir(parents=True,exist_ok=True);st.mkdir(parents=True,exist_ok=False)
    try:
        fields=[]
        for r in out:
            for k in r:
                if k not in fields:fields.append(k)
        op=st/'OMEGA_0.18.0_MARKET_COMPARISON.csv'
        with op.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(out)
        for fname,rows,fields2 in (
            ('OMEGA_0.18.0_UNMATCHED.csv',unmatched,list(unmatched[0].keys()) if unmatched else ['market_player_name']),
            ('OMEGA_0.18.0_AMBIGUOUS.csv',ambig,list(ambig[0].keys()) if ambig else ['market_player_name']),
            ('OMEGA_0.18.0_UNSUPPORTED.csv',unsupported,list(unsupported[0].keys()) if unsupported else ['player_name'])
        ):
            with (st/fname).open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=fields2,lineterminator='\n');w.writeheader()
                if rows:w.writerows(rows)
        policy_doc={
            'schemaVersion':'OMEGA_SETTLEMENT_POLICY_0.18.0',
            'verifiedAsOf':'2026-09-11',
            'marketKind':'tackles_assists',
            'policies':SETTLEMENT_POLICIES,
            'policyRule':'Only status=RESOLVED clears SETTLEMENT_UNRESOLVED. Partial policies remain blocked.'
        }
        (st/'OMEGA_0.18.0_SETTLEMENT_POLICY.json').write_text(json.dumps(policy_doc,indent=2)+'\n')
        oh=sha(op)
        audit={
            'schemaVersion':'OMEGA_MARKET_COMPARISON_0.18.0',
            'generatedAt':now(),'omegaLedgerId':lid,'omegaLedgerSha256':actual,
            'marketSnapshotId':mid,'comparisonRows':len(out),'unmatchedRows':len(unmatched),
            'ambiguousRows':len(ambig),'unsupportedLineRows':len(unsupported),
            'identityJoinMethods':methods,
            'explicitTeamScopedAliases':{
                'FOYESADEOLUOKUN|JAGUARS':'FOYEOLUOKUN',
                'JOSHUAMETELLUS|VIKINGS':'JOSHMETELLUS'
            },
            'propsMadnessIdsTreatedAsGsis':False,
            'fuzzyMatchingUsed':False,
            'twoSidedRows':sum(r['market_reference_quality']=='TWO_SIDED_NO_VIG' for r in out),
            'oneSidedRows':sum(r['market_reference_quality']=='ONE_SIDED_EV_ONLY' for r in out),
            'settlementResolvedRows':sum(r['settlement_resolved']=='TRUE' for r in out),
            'settlementUnresolvedRows':sum(r['settlement_resolved']!='TRUE' for r in out),
            'settlementPolicyCounts':{
                k:sum(r.get('settlement_policy_status')==k for r in out)
                for k in sorted({r.get('settlement_policy_status') for r in out})
            },
            'verifiedReadyRows':sum(str(r['verified_ready']).upper()=='TRUE' for r in out),
            'actionableRows':0,'modelReadOnly':True,'rawMarketReadOnly':True,
            'marketEnteredModel':False,'oddsPapiPlayerPropRequests':0,
            'comparisonSha256':oh,'status':'PROSPECTIVE_RESEARCH_ONLY'
        }
        (st/'OMEGA_0.18.0_MARKET_COMPARISON_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
        (st/'OMEGA_0.18.0_MARKET_COMPARISON.sha256').write_text(oh+'\n')
        os.replace(st,final)
        (root/'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_MARKET_COMPARISON').write_text(sid+'\n')
    except Exception:
        shutil.rmtree(st,ignore_errors=True);raise

    print('OMEGA 0.18.0 — DOWNSTREAM MARKET COMPARISON / IDENTITY BRIDGE')
    print(f'PASS OMEGA-I ledger {actual} · read-only')
    print(f'PASS comparison rows {len(out)} · two-sided {audit["twoSidedRows"]} · one-sided {audit["oneSidedRows"]}')
    print(f'PASS unmatched {len(unmatched)} · ambiguous {len(ambig)} · unsupported lines {len(unsupported)}')
    print('PASS identity join methods:',json.dumps(methods,sort_keys=True))
    print('PASS PropsMadness numeric IDs treated as GSIS: NO · fuzzy matching: NO')
    print('PASS explicit team-scoped aliases: Foyesade Oluokun→Foye Oluokun · Joshua Metellus→Josh Metellus')
    print(f'PASS settlement-resolved {audit["settlementResolvedRows"]} · settlement-unresolved {audit["settlementUnresolvedRows"]}')
    print('PASS settlement policies:',json.dumps(audit['settlementPolicyCounts'],sort_keys=True))
    print(f'PASS VERIFIED-ready {audit["verifiedReadyRows"]} · actionable 0')
    print('PASS market entered OMEGA-I: NO · OddsPapi player-prop requests 0')
    print(f'PASS immutable comparison SHA256: {oh}')
    print('STATUS: PROSPECTIVE_RESEARCH_ONLY — positive EV is not a VERIFIED pick')
    print(f'REPORT: {final/"OMEGA_0.18.0_MARKET_COMPARISON_AUDIT.json"}')
    return 0

if __name__=='__main__':raise SystemExit(main())

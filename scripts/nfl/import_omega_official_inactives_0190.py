#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import csv,hashlib,json,re,shutil,sys,unicodedata,zipfile

EXPECTED_SCHEMA='OMEGA_NFL_OFFICIAL_INACTIVES_CAPTURE_0.19.0'
EXPECTED_LEDGER_SHA='fe4991a743a1c02994b59d473a1bec9a1ccafa61a60548df43f2f5292e4ca08a'
SUFFIXES={'JR','JUNIOR','SR','SENIOR','II','III','IV','V'}

TEAM_ALIAS={
 'ARI':'CARDINALS','ARIZONACARDINALS':'CARDINALS','ATL':'FALCONS','ATLANTAFALCONS':'FALCONS',
 'BAL':'RAVENS','BALTIMORERAVENS':'RAVENS','BUF':'BILLS','BUFFALOBILLS':'BILLS',
 'CAR':'PANTHERS','CAROLINAPANTHERS':'PANTHERS','CHI':'BEARS','CHICAGOBEARS':'BEARS',
 'CIN':'BENGALS','CINCINNATIBENGALS':'BENGALS','CLE':'BROWNS','CLEVELANDBROWNS':'BROWNS',
 'DAL':'COWBOYS','DALLASCOWBOYS':'COWBOYS','DEN':'BRONCOS','DENVERBRONCOS':'BRONCOS',
 'DET':'LIONS','DETROITLIONS':'LIONS','GB':'PACKERS','GNB':'PACKERS','GREENBAYPACKERS':'PACKERS',
 'HOU':'TEXANS','HOUSTONTEXANS':'TEXANS','IND':'COLTS','INDIANAPOLISCOLTS':'COLTS',
 'JAX':'JAGUARS','JAC':'JAGUARS','JACKSONVILLEJAGUARS':'JAGUARS','KC':'CHIEFS','KANSASCITYCHIEFS':'CHIEFS',
 'LV':'RAIDERS','LVR':'RAIDERS','LASVEGASRAIDERS':'RAIDERS','LAC':'CHARGERS','LOSANGELESCHARGERS':'CHARGERS',
 'LA':'RAMS','LAR':'RAMS','LOSANGELESRAMS':'RAMS','MIA':'DOLPHINS','MIAMIDOLPHINS':'DOLPHINS',
 'MIN':'VIKINGS','MINNESOTAVIKINGS':'VIKINGS','NE':'PATRIOTS','NWE':'PATRIOTS','NEWENGLANDPATRIOTS':'PATRIOTS',
 'NO':'SAINTS','NOR':'SAINTS','NEWORLEANSSAINTS':'SAINTS','NYG':'GIANTS','NEWYORKGIANTS':'GIANTS',
 'NYJ':'JETS','NEWYORKJETS':'JETS','PHI':'EAGLES','PHILADELPHIAEAGLES':'EAGLES',
 'PIT':'STEELERS','PITTSBURGHSTEELERS':'STEELERS','SEA':'SEAHAWKS','SEATTLESEAHAWKS':'SEAHAWKS',
 'SF':'NINERS','SFO':'NINERS','SANFRANCISCO49ERS':'NINERS','TB':'BUCCANEERS','TAM':'BUCCANEERS','TAMPABAYBUCCANEERS':'BUCCANEERS',
 'TEN':'TITANS','TENNESSEETITANS':'TITANS','WAS':'COMMANDERS','WSH':'COMMANDERS','WASHINGTONCOMMANDERS':'COMMANDERS'
}

# Same narrow provider/display aliases already admitted into the market identity bridge.
NAME_ALIAS={
 ('FOYESADEOLUOKUN','JAGUARS'):'FOYEOLUOKUN',
 ('JOSHUAMETELLUS','VIKINGS'):'JOSHMETELLUS'
}

def fold(s):return unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode('ascii')
def cteam(s):
    raw=re.sub(r'[^A-Z0-9]','',fold(s).upper())
    return TEAM_ALIAS.get(raw,raw)
def cname(s):
    toks=re.findall(r'[A-Z0-9]+',fold(s).upper())
    while toks and toks[-1] in SUFFIXES:toks.pop()
    return ''.join(toks)
def alias_name(n,t):
    cn=cname(n);ct=cteam(t)
    return NAME_ALIAS.get((cn,ct),cn)
def rcsv(p):
    with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def consolidate_sections(sections):
    by=defaultdict(list)
    for s in sections:
        team=cteam(s.get('canonicalTeam'))
        if not team:continue
        cand=[x for x in (s.get('inactiveCandidates') or []) if cname(x)]
        if len(cand)>=2:
            by[team].append(set(cname(x) for x in cand))
    published={}
    conflicts={}
    for team,groups in by.items():
        # Multiple DOM representations are okay only if they agree materially.
        union=set().union(*groups)
        if len(groups)>1:
            inter=set.intersection(*groups)
            if len(inter)<min(2,len(union)):
                conflicts[team]=[sorted(x) for x in groups]
                continue
        published[team]=union
    return published,conflicts

def main():
    downloads=Path.home()/'Downloads'
    caps=sorted(downloads.glob('OMEGA_0190_NFL_OFFICIAL_INACTIVES_*.json'),
                key=lambda p:p.stat().st_mtime,reverse=True)
    if not caps:raise SystemExit('FAIL no OMEGA 0.19.0 official inactives capture found in ~/Downloads')
    src=caps[0];raw=src.read_bytes()
    try:data=json.loads(raw)
    except Exception as e:raise SystemExit(f'FAIL invalid capture JSON: {e}')
    if data.get('schemaVersion')!=EXPECTED_SCHEMA:raise SystemExit('FAIL wrong capture schema')
    url=str(data.get('sourceUrl') or '')
    if not re.match(r'^https://(?:www\.)?nfl\.com/',url,re.I):raise SystemExit(f'FAIL source is not nfl.com: {url}')
    if data.get('pageSaysCheckBackSoon') and not data.get('teamSections'):
        raise SystemExit('FAIL official NFL inactive lists are not published yet; no availability verification performed')

    published,conflicts=consolidate_sections(data.get('teamSections') or [])
    if not published:
        raise SystemExit('FAIL no trustworthy team inactive sections parsed from official NFL capture')

    root=Path('/Users/abbeyfelix/Developer/MODEL')
    ptr=root/'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_MARKET_COMPARISON'
    if not ptr.exists():raise SystemExit('FAIL no current OMEGA market comparison')
    runid=ptr.read_text().strip()
    # Current pointer may point into any comparison version; locate it.
    cands=list((root/'data/prospective/nfl/omega').glob(f'market_comparison_*/{runid}'))
    if len(cands)!=1:raise SystemExit(f'FAIL could not uniquely locate comparison run {runid}')
    cdir=cands[0]
    csvs=[p for p in cdir.glob('OMEGA_*_MARKET_COMPARISON.csv') if 'UNMATCHED' not in p.name]
    if len(csvs)!=1:raise SystemExit('FAIL current comparison CSV not unique')
    rows=rcsv(csvs[0])
    if not rows:raise SystemExit('FAIL current comparison has no rows')
    ledger_sha=rows[0].get('model_ledger_sha256')
    if ledger_sha!=EXPECTED_LEDGER_SHA:raise SystemExit(f'FAIL unexpected OMEGA-I ledger hash {ledger_sha}')

    out=[];counts=defaultdict(int)
    for r in rows:
        rr=dict(r)
        team=cteam(r.get('team') or r.get('market_player_team'))
        player=alias_name(r.get('player_name') or r.get('market_player_name'),team)
        if team in conflicts:
            status='UNRESOLVED_TEAM_SECTION_CONFLICT'
        elif team not in published:
            status='PENDING_OFFICIAL_INACTIVES'
        elif player in published[team]:
            status='INACTIVE'
        else:
            status='VERIFIED_ACTIVE'
        counts[status]+=1
        rr['official_inactives_source_url']=url
        rr['official_inactives_captured_at']=data.get('capturedAt')
        rr['availability_team']=team
        rr['availability_status']=status
        rr['availability_verified_active']='TRUE' if status=='VERIFIED_ACTIVE' else 'FALSE'
        settlement=str(rr.get('settlement_resolved') or '').upper()=='TRUE'
        rr['data_verified_ready']='TRUE' if status=='VERIFIED_ACTIVE' and settlement else 'FALSE'
        blockers=[]
        if status!='VERIFIED_ACTIVE':blockers.append(status)
        if not settlement:blockers.append('SETTLEMENT_UNRESOLVED')
        rr['data_gate_blockers']='|'.join(blockers)
        # Model is still under prospective validation; do not convert data readiness into a betting pick.
        rr['actionability']='PROSPECTIVE_RESEARCH_ONLY'
        out.append(rr)

    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    sid=f'{stamp}_{hashlib.sha256(raw).hexdigest()[:8]}'
    outdir=root/'data/prospective/nfl/omega/availability_overlay_0190'/sid
    outdir.mkdir(parents=True,exist_ok=False)
    fields=[]
    for r in out:
        for k in r:
            if k not in fields:fields.append(k)
    op=outdir/'OMEGA_0.19.0_AVAILABILITY_OVERLAY.csv'
    with op.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(out)
    (outdir/'NFL_OFFICIAL_INACTIVES_CAPTURE.json').write_bytes(raw)
    audit={
      'schemaVersion':'OMEGA_AVAILABILITY_GATE_0.19.0','generatedAt':now(),
      'sourceUrl':url,'sourceCapturedAt':data.get('capturedAt'),
      'omegaLedgerSha256':ledger_sha,'inputComparisonRun':runid,
      'rows':len(out),'teamSectionsPublished':sorted(published),
      'teamSectionConflicts':conflicts,'availabilityCounts':dict(counts),
      'dataVerifiedReadyRows':sum(r['data_verified_ready']=='TRUE' for r in out),
      'inactiveRows':sum(r['availability_status']=='INACTIVE' for r in out),
      'modelReadOnly':True,'marketReadOnly':True,'fuzzyMatchingUsed':False,
      'actionabilityStatus':'PROSPECTIVE_RESEARCH_ONLY'
    }
    (outdir/'OMEGA_0.19.0_AVAILABILITY_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
    oh=sha(op);(outdir/'OMEGA_0.19.0_AVAILABILITY_OVERLAY.sha256').write_text(oh+'\n')
    (root/'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_AVAILABILITY_OVERLAY').write_text(sid+'\n')

    handoff=downloads/'OMEGA_0190_OFFICIAL_INACTIVES_AVAILABILITY_HANDOFF.zip'
    if handoff.exists():handoff.unlink()
    with zipfile.ZipFile(handoff,'w',zipfile.ZIP_DEFLATED) as z:
        for p in (op,outdir/'OMEGA_0.19.0_AVAILABILITY_AUDIT.json',outdir/'NFL_OFFICIAL_INACTIVES_CAPTURE.json'):
            z.write(p,'OMEGA_0190_HANDOFF/'+p.name)

    print()
    print('OMEGA 0.19.0 — OFFICIAL NFL GAMEDAY AVAILABILITY GATE')
    print()
    print(f'PASS official source: {url}')
    print(f'PASS published team sections: {len(published)} · conflicts {len(conflicts)}')
    print('PASS availability counts:',json.dumps(dict(counts),sort_keys=True))
    print(f'PASS data-VERIFIED-ready rows: {audit["dataVerifiedReadyRows"]}/{len(out)}')
    print(f'PASS inactive rows: {audit["inactiveRows"]}')
    print('PASS OMEGA-I read-only · market snapshot read-only · fuzzy matching NO')
    print('STATUS: PROSPECTIVE_RESEARCH_ONLY — verified data readiness is not model promotion')
    print(f'PASS immutable overlay SHA256: {oh}')
    print('REPORT:',outdir/'OMEGA_0.19.0_AVAILABILITY_AUDIT.json')
    print('UPLOAD:',handoff)

if __name__=='__main__':raise SystemExit(main())

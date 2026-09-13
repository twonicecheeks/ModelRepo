#!/usr/bin/env python3
"""Normalize a user/provider tackle-market capture into an immutable raw snapshot.

This is storage only.  It refuses model probability/edge/EV fields so captured market
history cannot silently become a model-fitting artifact.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,os,shutil,tempfile

ALLOWED_MARKETS={'tackles_assists','solo_tackles','assists'}
FORBIDDEN={'model_probability','p_model','edge','ev','expected_value','recommended_bet','pick'}
FIELDS=[
    'captured_at','source','book','game_id','game_date','away_team','home_team',
    'player_id','player_name','player_team','opponent','market_kind','market_label',
    'line','over_odds_american','under_odds_american','one_sided_side','one_sided_odds_american',
    'settlement_scope','includes_special_teams','stat_correction_policy','source_event_id','notes'
]

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def clean(v):return '' if v is None else str(v).strip()

def read_rows(path):
    suf=path.suffix.lower()
    if suf=='.csv':
        with path.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
    if suf in {'.jsonl','.ndjson'}:
        return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    if suf=='.json':
        x=json.loads(path.read_text(encoding='utf-8'));return x if isinstance(x,list) else x.get('rows',[])
    raise ValueError('input must be .csv, .json, .jsonl, or .ndjson')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');ap.add_argument('--source',default='manual_or_provider_export');a=ap.parse_args()
    root=Path(a.root).resolve();inp=Path(a.input).expanduser().resolve();rows=read_rows(inp)
    if not rows:raise SystemExit('FAIL no market rows in input')
    cols=set().union(*(r.keys() for r in rows))
    bad=sorted(cols & FORBIDDEN)
    if bad:raise SystemExit('FAIL model-derived fields forbidden in raw market capture: '+', '.join(bad))
    normalized=[];captured_default=now()
    for i,r in enumerate(rows,1):
        kind=clean(r.get('market_kind')).lower()
        if kind not in ALLOWED_MARKETS:raise SystemExit(f'FAIL row {i} market_kind must be one of {sorted(ALLOWED_MARKETS)}')
        if not clean(r.get('book')):raise SystemExit(f'FAIL row {i} missing book')
        if not clean(r.get('player_name')) and not clean(r.get('player_id')):raise SystemExit(f'FAIL row {i} missing player identity')
        if clean(r.get('line'))=='':raise SystemExit(f'FAIL row {i} missing line')
        if not (clean(r.get('over_odds_american')) and clean(r.get('under_odds_american'))):
            if not (clean(r.get('one_sided_side')) and clean(r.get('one_sided_odds_american'))):
                raise SystemExit(f'FAIL row {i} needs two-sided prices or explicit one-sided side+price')
        x={k:clean(r.get(k)) for k in FIELDS};x['captured_at']=x['captured_at'] or captured_default;x['source']=x['source'] or a.source
        x['settlement_scope']=x['settlement_scope'] or 'UNKNOWN';x['includes_special_teams']=x['includes_special_teams'] or 'UNKNOWN';x['stat_correction_policy']=x['stat_correction_policy'] or 'UNKNOWN'
        normalized.append(x)
    raw=inp.read_bytes();digest=sha_bytes(raw);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');sid=f'{stamp}_{digest[:8]}'
    base=root/'data/raw/nfl/omega/market_snapshots';final=base/sid;st=base/('.'+sid+'.staging')
    base.mkdir(parents=True,exist_ok=True)
    if final.exists():raise SystemExit(f'FAIL immutable market snapshot already exists: {final}')
    st.mkdir(parents=True,exist_ok=False)
    try:
        shutil.copy2(inp,st/('source'+inp.suffix.lower()))
        with (st/'normalized_market_rows.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n');w.writeheader();w.writerows(normalized)
        manifest={'schemaVersion':'OMEGA_TACKLE_MARKET_LEDGER_0.1','snapshotId':sid,'createdAt':now(),'sourceFile':inp.name,'sourceSha256':digest,'rows':len(normalized),'marketKinds':sorted({r['market_kind'] for r in normalized}),'books':sorted({r['book'] for r in normalized}),'modelFieldsPresent':False,'oddsPapiRequests':0,'note':'Raw market capture only. No model probabilities, edges, or EV are permitted.'}
        (st/'MARKET_SNAPSHOT_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');os.replace(st,final)
        (root/'data/raw/nfl/omega/CURRENT_MARKET_SNAPSHOT').write_text(sid+'\n',encoding='utf-8')
    except Exception:
        shutil.rmtree(st,ignore_errors=True);raise
    print(f'PASS immutable OMEGA market snapshot: {sid}')
    print(f'PASS rows: {len(normalized)} · books: {", ".join(manifest["books"])}')
    print('PASS model fields absent · OddsPapi requests 0')
    print(final/'MARKET_SNAPSHOT_MANIFEST.json')
    return 0
if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
"""Validate and immutably store raw pregame availability/role state."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,os,shutil
FIELDS=['captured_at','source','source_priority','source_updated_at','source_record_id','game_id','season','week','game_date','team','opponent','player_id','player_name','position','roster_status','game_status','injury_designation','listed_starter','depth_position','depth_role','notes']
ENUMS={'source_priority':{'OFFICIAL_NFL','OFFICIAL_TEAM','AUTHORITATIVE_PROVIDER','SECONDARY_PROVIDER','MANUAL_VERIFIED'},'roster_status':{'ACTIVE_ROSTER','PRACTICE_SQUAD','IR','PUP','NFI','SUSPENDED','EXEMPT','FREE_AGENT','UNKNOWN'},'game_status':{'ACTIVE','INACTIVE','OUT','DOUBTFUL','QUESTIONABLE','PROBABLE','NOT_LISTED','UNKNOWN'},'listed_starter':{'TRUE','FALSE','UNKNOWN'},'depth_role':{'STARTER','BACKUP','ROTATIONAL','SPECIALIST','UNKNOWN'}}
FORBIDDEN_TOKENS=('odds','price','market','edge','expected_value','model_probability','predicted_xtc','actual_xtc','recommended_bet','pick')
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def parse_ts(s):
 x=str(s or '').strip().replace('Z','+00:00');dt=datetime.fromisoformat(x);return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
def rows(path):
 if path.suffix.lower()=='.csv':
  with path.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
 x=json.loads(path.read_text(encoding='utf-8'));return x if isinstance(x,list) else x.get('rows',[])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args();root=Path(a.root).resolve();p=Path(a.input).expanduser().resolve();rr=rows(p)
 if not rr:raise SystemExit('FAIL no pregame role rows')
 cols=set().union(*(r.keys() for r in rr)); bad=sorted(c for c in cols if any(t in c.lower() for t in FORBIDDEN_TOKENS))
 if bad:raise SystemExit('FAIL forbidden market/model-derived field(s): '+', '.join(bad))
 out=[];seen=set()
 for i,r in enumerate(rr,1):
  z={k:str(r.get(k) or '').strip() for k in FIELDS}
  for k in ('captured_at','source','source_priority','source_updated_at','game_id','season','week','team','player_id','player_name','roster_status','game_status','listed_starter','depth_role'):
   if not z[k]:raise SystemExit(f'FAIL row {i} missing {k}')
  for k,allowed in ENUMS.items():
   z[k]=z[k].upper()
   if z[k] not in allowed:raise SystemExit(f'FAIL row {i} {k}={z[k]!r} not in {sorted(allowed)}')
  try:parse_ts(z['captured_at']);parse_ts(z['source_updated_at']);int(z['season']);int(z['week'])
  except Exception as e:raise SystemExit(f'FAIL row {i} timestamp/season/week parse: {e}')
  key=(z['game_id'],z['player_id'],z['source'],z['source_record_id'],z['source_updated_at'])
  if key in seen:raise SystemExit(f'FAIL duplicate source row {i}: {key}')
  seen.add(key);out.append(z)
 digest=sha(p);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');sid=f'{stamp}_{digest[:8]}';base=root/'data/raw/nfl/omega/pregame_role_snapshots';final=base/sid;st=base/('.'+sid+'.staging');base.mkdir(parents=True,exist_ok=True)
 if final.exists():raise SystemExit(f'FAIL immutable snapshot exists: {final}')
 st.mkdir(parents=True,exist_ok=False)
 try:
  shutil.copy2(p,st/('source'+p.suffix.lower()))
  with (st/'normalized_pregame_role_rows.csv').open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n');w.writeheader();w.writerows(out)
  manifest={'schemaVersion':'OMEGA_PREGAME_ROLE_SNAPSHOT_0.14','snapshotId':sid,'createdAt':now(),'sourceFile':p.name,'sourceSha256':digest,'rows':len(out),'games':len({r['game_id'] for r in out}),'players':len({r['player_id'] for r in out}),'sources':sorted({r['source'] for r in out}),'marketFieldsPresent':False,'modelDerivedFieldsPresent':False,'networkRequests':0}
  (st/'PREGAME_ROLE_SNAPSHOT_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');os.replace(st,final)
  (root/'data/raw/nfl/omega/CURRENT_PREGAME_ROLE_SNAPSHOT').write_text(sid+'\n',encoding='utf-8')
 except Exception:
  shutil.rmtree(st,ignore_errors=True);raise
 print(f'PASS immutable OMEGA pregame role snapshot: {sid}');print(f"PASS rows {len(out)} · games {manifest['games']} · players {manifest['players']}");print('PASS market/model-derived fields absent · network requests 0');print(final/'PREGAME_ROLE_SNAPSHOT_MANIFEST.json')
 return 0
if __name__=='__main__':raise SystemExit(main())

#!/usr/bin/env python3
"""Capture immutable 2026 OMEGA pregame research state from public nflverse feeds.

This is explicitly a SECONDARY_PROVIDER layer. It is useful for prospective research
and candidate-universe construction, but it does not equal an authoritative game-day
inactive feed and therefore cannot by itself create VERIFIED Trust.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import argparse,csv,hashlib,json,os,shutil,subprocess,tempfile

SEASON=2026
URLS={
 'schedule':'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv',
 'weekly_rosters':'https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2026.csv',
 'injuries':'https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2026.csv',
 'depth_charts':'https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv',
 'players':'https://github.com/nflverse/nflverse-data/releases/download/players/players.csv',
}
DEF_POS={'DB','CB','S','FS','SS','SAF','NB','DB','LB','ILB','OLB','MLB','EDGE','ED','DL','DE','DT','NT'}

def nowdt(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def readcsv(p):
 with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def _parse_curl_headers(text):
 # curl --location may emit one HTTP header block per redirect. Use the final block.
 blocks=[]; cur=[]
 for line in text.replace('\r\n','\n').split('\n'):
  if line.startswith('HTTP/'):
   if cur: blocks.append(cur)
   cur=[line]
  elif cur:
   if line=='':
    blocks.append(cur); cur=[]
   else:
    cur.append(line)
 if cur: blocks.append(cur)
 block=blocks[-1] if blocks else []
 headers={}
 status=None
 if block:
  try: status=int(block[0].split()[1])
  except Exception: status=None
  for line in block[1:]:
   if ':' not in line: continue
   k,v=line.split(':',1); headers[k.strip().lower()]=v.strip()
 return status,headers

def download(url,p,required=True):
 # Python.org framework builds can lack a configured macOS CA bundle. Use the
 # system curl TLS stack instead; certificate verification remains ENABLED.
 curl=shutil.which('curl')
 if not curl:
  raise RuntimeError('system curl not found; refusing to disable TLS verification')
 p.parent.mkdir(parents=True,exist_ok=True)
 part=p.with_name(p.name+'.part')
 hdr=p.with_name(p.name+'.headers.part')
 for q in (part,hdr):
  try:q.unlink()
  except FileNotFoundError:pass
 cmd=[curl,'--fail','--location','--silent','--show-error',
      '--connect-timeout','20','--max-time','90','--retry','2','--retry-delay','1',
      '--user-agent','OMEGA-MODEL/0.16.1 research capture',
      '--dump-header',str(hdr),'--output',str(part),'--write-out','%{http_code}',url]
 r=subprocess.run(cmd,text=True,capture_output=True)
 if r.returncode!=0:
  for q in (part,hdr):
   try:q.unlink()
   except FileNotFoundError:pass
  msg=(r.stderr or r.stdout or f'curl exit {r.returncode}').strip()
  if required: raise RuntimeError(f'download failed for {url}: {msg}')
  return {'url':url,'error':msg,'optional':True,'transport':'system_curl_tls_verified'}
 if not part.exists() or part.stat().st_size==0:
  for q in (part,hdr):
   try:q.unlink()
   except FileNotFoundError:pass
  msg='download returned empty body'
  if required: raise RuntimeError(f'{msg}: {url}')
  return {'url':url,'error':msg,'optional':True,'transport':'system_curl_tls_verified'}
 raw_headers=hdr.read_text(errors='replace') if hdr.exists() else ''
 parsed_status,headers=_parse_curl_headers(raw_headers)
 try: http_status=int((r.stdout or '').strip()[-3:])
 except Exception: http_status=parsed_status or 200
 os.replace(part,p)
 try:hdr.unlink()
 except FileNotFoundError:pass
 return {'url':url,'httpStatus':http_status,'etag':headers.get('etag'),'lastModified':headers.get('last-modified'),'contentType':headers.get('content-type'),'transport':'system_curl_tls_verified','tlsVerificationDisabled':False}
def normteam(s):
 x=str(s or '').strip().upper(); return {'JAX':'JAC','LAR':'LA','STL':'LA','SD':'LAC','OAK':'LV'}.get(x,x)
def pg(pos,players_pg=''):
 q=str(players_pg or '').upper().strip(); p=str(pos or '').upper().strip()
 if q in {'DB','DL','LB'}: return q
 if p in {'CB','S','FS','SS','SAF','NB','DB'}: return 'DB'
 if p in {'LB','ILB','OLB','MLB'}: return 'LB'
 if p in {'DL','DE','DT','NT','EDGE','ED'}: return 'DL'
 return ''
def roster_status(raw):
 x=str(raw or '').upper().strip()
 return {'ACT':'ACTIVE_ROSTER','DEV':'PRACTICE_SQUAD','PUP':'PUP','SUS':'SUSPENDED','RSN':'NFI','EXE':'EXEMPT','CUT':'FREE_AGENT','UFA':'FREE_AGENT','RFA':'FREE_AGENT','TRC':'FREE_AGENT','TRD':'FREE_AGENT','TRT':'FREE_AGENT','RES':'IR'}.get(x,'UNKNOWN')
def game_status(raw):
 x=str(raw or '').strip().upper().replace(' ','_')
 if not x: return 'NOT_LISTED'
 if 'OUT'==x or x.endswith('_OUT'): return 'OUT'
 if 'DOUBT' in x: return 'DOUBTFUL'
 if 'QUESTION' in x: return 'QUESTIONABLE'
 if 'PROB' in x: return 'PROBABLE'
 return 'UNKNOWN'
def kickoff(r):
 gd=str(r.get('gameday') or '').strip(); gt=str(r.get('gametime') or '').strip()
 if not gd: return None
 if not gt: gt='00:00'
 try:return datetime.fromisoformat(gd+'T'+gt).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
 except Exception:return None
def latest_by(rows,key,tskey):
 out={}
 for r in rows:
  k=key(r)
  if not k or any(not x for x in (k if isinstance(k,tuple) else (k,))): continue
  t=str(r.get(tskey) or '')
  if k not in out or t>=str(out[k].get(tskey) or ''): out[k]=r
 return out

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL'); ap.add_argument('--week',type=int); a=ap.parse_args(); root=Path(a.root).resolve(); captured=nowdt()
 # Do not touch historical Phase1 pointers. This is a separate prospective source tree.
 stamp=captured.strftime('%Y%m%dT%H%M%SZ'); base=root/'data/raw/nfl/omega/prospective_2026_pregame'; st=base/('.'+stamp+'.staging'); st.mkdir(parents=True,exist_ok=False)
 meta={}; required={'schedule','weekly_rosters','injuries','players'}
 try:
  for name,url in URLS.items():
   p=st/(name+'.csv'); info=download(url,p,required=name in required); info['capturedAt']=iso(captured)
   if p.exists(): info.update({'sha256':sha(p),'bytes':p.stat().st_size})
   meta[name]=info
  schedules=[r for r in readcsv(st/'schedule.csv') if str(r.get('season') or '')==str(SEASON) and str(r.get('game_type') or '')=='REG']
  future=[]
  for r in schedules:
   ko=kickoff(r)
   if ko and ko>captured: future.append((ko,r))
  if not future: raise RuntimeError('no future 2026 REG games found in schedule')
  target_week=a.week or min(int(r.get('week') or 0) for _,r in future)
  games=[]
  for ko,r in future:
   if int(r.get('week') or 0)!=target_week: continue
   games.append({'game_id':str(r.get('game_id') or ''),'season':SEASON,'week':target_week,'kickoff_utc':iso(ko),'gameday':r.get('gameday',''),'gametime_et':r.get('gametime',''),'away_team':normteam(r.get('away_team')),'home_team':normteam(r.get('home_team'))})
  if not games: raise RuntimeError(f'no future target games for week {target_week}')
  gbyteam={}
  for g in games:
   gbyteam[g['away_team']]=(g,g['home_team']); gbyteam[g['home_team']]=(g,g['away_team'])
  players=readcsv(st/'players.csv'); pmeta={str(r.get('gsis_id') or '').strip():r for r in players if str(r.get('gsis_id') or '').strip()}
  rosters=[r for r in readcsv(st/'weekly_rosters.csv') if str(r.get('season') or '')==str(SEASON) and int(float(r.get('week') or 0))==target_week and str(r.get('game_type') or 'REG') in {'REG',''}]
  injuries=[r for r in readcsv(st/'injuries.csv') if str(r.get('season') or '')==str(SEASON) and int(float(r.get('week') or 0))==target_week and str(r.get('season_type') or 'REG') in {'REG',''}]
  inj=latest_by(injuries,lambda r:(normteam(r.get('team')),str(r.get('gsis_id') or '').strip()),'date_modified')
  depth=[]
  if (st/'depth_charts.csv').exists():
   depth=readcsv(st/'depth_charts.csv')
   # new 2025+ schema has dt; only use records captured in 2026 and not from the future.
   dd=[]
   for r in depth:
    ds=str(r.get('dt') or '')
    if ds.startswith('2026') and ds<=iso(captured): dd.append(r)
   depth=dd
  dmap=latest_by(depth,lambda r:(normteam(r.get('team')),str(r.get('gsis_id') or '').strip()),'dt')
  rows=[]
  for r in rosters:
   team=normteam(r.get('team'))
   if team not in gbyteam: continue
   pid=str(r.get('gsis_id') or '').strip()
   if not pid: continue
   pm=pmeta.get(pid,{})
   pos=str(r.get('position') or pm.get('position') or '')
   group=pg(pos,pm.get('position_group'))
   if group not in {'DB','DL','LB'}: continue
   g,opp=gbyteam[team]; ir=inj.get((team,pid),{}); dr=dmap.get((team,pid),{})
   rs=roster_status(r.get('status')); gs=game_status(ir.get('report_status'))
   try: rank=int(float(dr.get('pos_rank') or 0))
   except Exception: rank=0
   ls='TRUE' if rank==1 else ('FALSE' if rank>1 else 'UNKNOWN')
   role='STARTER' if rank==1 else ('BACKUP' if rank>1 else 'UNKNOWN')
   research_ready=(rs=='ACTIVE_ROSTER' and gs!='OUT')
   rows.append({
    'captured_at':iso(captured),'source':'nflverse_2026_composite','source_priority':'SECONDARY_PROVIDER','source_updated_at':str(ir.get('date_modified') or dr.get('dt') or iso(captured)),
    'game_id':g['game_id'],'season':SEASON,'week':target_week,'kickoff_utc':g['kickoff_utc'],'team':team,'opponent':opp,'player_id':pid,'player_name':str(r.get('full_name') or pm.get('display_name') or ''),'position':pos,'position_group':group,
    'roster_status_raw':str(r.get('status') or ''),'roster_status':rs,'injury_designation':str(ir.get('report_status') or ''),'injury_primary':str(ir.get('report_primary_injury') or ''),'practice_status':str(ir.get('practice_status') or ''),'game_status':gs,
    'depth_position':str(dr.get('pos_abb') or r.get('depth_chart_position') or ''),'depth_rank':rank or '','listed_starter':ls,'depth_role':role,
    'availability_authority':'SECONDARY_ONLY','research_ready':'TRUE' if research_ready else 'FALSE','verified_ready':'FALSE','verified_block_reason':'NO_AUTHORITATIVE_GAME_DAY_INACTIVE_SOURCE',
   })
  if not rows: raise RuntimeError('no defensive player rows in target future slate')
  fields=list(rows[0])
  with (st/'normalized_pregame_state.csv').open('w',newline='',encoding='utf-8') as f:
   cw=csv.DictWriter(f,fieldnames=fields,lineterminator='\n'); cw.writeheader(); cw.writerows(rows)
  with (st/'target_games.csv').open('w',newline='',encoding='utf-8') as f:
   cw=csv.DictWriter(f,fieldnames=list(games[0]),lineterminator='\n'); cw.writeheader(); cw.writerows(games)
  state_sha=sha(st/'normalized_pregame_state.csv'); sid=f'{stamp}_{state_sha[:8]}'; final=base/sid
  manifest={'schemaVersion':'OMEGA_2026_PREGAME_SOURCE_0.16','snapshotId':sid,'capturedAt':iso(captured),'season':SEASON,'targetWeek':target_week,'futureGames':len(games),'defensivePlayerRows':len(rows),'researchReadyRows':sum(r['research_ready']=='TRUE' for r in rows),'verifiedReadyRows':0,'sourceClass':'SECONDARY_PROVIDER','authoritativeGameDayInactiveFeed':False,'marketFieldsRead':0,'oddsPapiRequests':0,'sources':meta,'normalizedStateSha256':state_sha}
  (st/'PREGAME_SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
  os.replace(st,final); (root/'data/raw/nfl/omega/CURRENT_OMEGA_TACKLE_2026_PREGAME_SOURCE').write_text(sid+'\n')
 except Exception:
  shutil.rmtree(st,ignore_errors=True); raise
 print('OMEGA 0.16 — 2026 PREGAME SOURCE CAPTURE')
 print(f'PASS immutable snapshot: {sid}')
 print(f'PASS week {target_week} · future games {len(games)} · defensive player rows {len(rows)}')
 print(f"PASS research-ready {manifest['researchReadyRows']} · VERIFIED-ready 0 (fail-closed: no authoritative game-day inactive feed)")
 print('PASS market fields 0 · OddsPapi 0')
 print(f'MANIFEST: {final/"PREGAME_SOURCE_MANIFEST.json"}')
 return 0
if __name__=='__main__': raise SystemExit(main())

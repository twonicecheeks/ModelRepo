#!/usr/bin/env python3
"""Fail-closed readiness audit for raw OMEGA pregame role snapshots."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json
UNKNOWN={'','UNKNOWN'}
BLOCKING_GAME={'INACTIVE','OUT'};BLOCKING_ROSTER={'IR','PUP','NFI','SUSPENDED','FREE_AGENT'}
def parse_ts(s):
 x=str(s or '').strip().replace('Z','+00:00');dt=datetime.fromisoformat(x);return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');ap.add_argument('--snapshot');ap.add_argument('--targets',help='Optional CSV with game_id,player_id rows that must all resolve');ap.add_argument('--max-age-hours',type=float,default=24.0);a=ap.parse_args();root=Path(a.root).resolve()
 sid=a.snapshot or (root/'data/raw/nfl/omega/CURRENT_PREGAME_ROLE_SNAPSHOT').read_text().strip();d=root/'data/raw/nfl/omega/pregame_role_snapshots'/sid;p=d/'normalized_pregame_role_rows.csv'
 if not p.exists():raise SystemExit(f'FAIL snapshot rows missing: {p}')
 with p.open(newline='',encoding='utf-8') as f:rr=list(csv.DictReader(f))
 now=datetime.now(timezone.utc);latest={}
 for r in rr:
  k=(r['game_id'],r['player_id']);ts=parse_ts(r['source_updated_at']);cur=latest.get(k)
  rank={'OFFICIAL_NFL':5,'OFFICIAL_TEAM':4,'AUTHORITATIVE_PROVIDER':3,'SECONDARY_PROVIDER':2,'MANUAL_VERIFIED':1}.get(r['source_priority'],0)
  score=(ts,rank)
  if cur is None or score>(cur[0],cur[1]):latest[k]=(ts,rank,r)
 targets=[]
 if a.targets:
  with Path(a.targets).expanduser().open(newline='',encoding='utf-8-sig') as f:targets=[(x.get('game_id','').strip(),x.get('player_id','').strip()) for x in csv.DictReader(f)]
 else:targets=sorted(latest)
 failures=[];ready=0;blocked=0
 for k in targets:
  x=latest.get(k)
  if not x:failures.append((k,'MISSING'));continue
  ts,_,r=x;age=(now-ts.astimezone(timezone.utc)).total_seconds()/3600
  reasons=[]
  if age>a.max_age_hours:reasons.append(f'STALE_{age:.1f}H')
  for fld in ('roster_status','game_status','listed_starter','depth_role'):
   if r.get(fld,'') in UNKNOWN:reasons.append('UNRESOLVED_'+fld.upper())
  if r.get('roster_status') in BLOCKING_ROSTER or r.get('game_status') in BLOCKING_GAME:
   blocked+=1;continue
  if reasons:failures.append((k,';'.join(reasons)))
  else:ready+=1
 print('OMEGA 0.14 — PREGAME ROLE READINESS AUDIT')
 print(f'PASS snapshot {sid} · source rows {len(rr)} · unique player-games {len(latest)}')
 print(f'Targets: {len(targets)} · VERIFIED-ready: {ready} · known unavailable: {blocked} · unresolved/stale: {len(failures)}')
 if failures:
  for (g,pid),reason in failures[:40]:print(f'FAIL {g} {pid}: {reason}')
  raise SystemExit('FAIL pregame role gate unresolved/stale target(s); VERIFIED Trust prohibited')
 print('PASS pregame role gate resolved for all non-blocked targets')
 return 0
if __name__=='__main__':raise SystemExit(main())

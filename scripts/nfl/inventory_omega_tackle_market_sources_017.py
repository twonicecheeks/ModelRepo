#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,os,re
KEYS=('propsmadness','tackle','assist','player_prop','player-prop','market_snapshot')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args();root=Path(a.root).resolve()
 print('OMEGA 0.17 — LOCAL TACKLE-MARKET SOURCE INVENTORY (NO NETWORK)')
 print(f'ROOT: {root}')
 prov=root/'packages/providers/propsmadness'
 print(f'PropsMadness provider directory: {"YES" if prov.exists() else "NO"}')
 if prov.exists():
  fs=[p.relative_to(root) for p in prov.rglob('*') if p.is_file()]
  print(f'PropsMadness provider files: {len(fs)}')
  for p in fs[:30]:print('  '+str(p))
 cutoff=datetime.now(timezone.utc).timestamp()-14*86400;cands=[]
 for base in (root/'data',root/'artifacts',root/'tmp'):
  if not base.exists():continue
  for p in base.rglob('*'):
   if not p.is_file():continue
   try:
    if p.stat().st_mtime<cutoff or p.stat().st_size>20_000_000:continue
   except:continue
   s=str(p).lower()
   if any(k in s for k in KEYS):cands.append(p)
 print(f'Recent candidate market artifacts (14d): {len(cands)}')
 for p in sorted(cands,key=lambda x:x.stat().st_mtime,reverse=True)[:40]:
  print(f'  {p.relative_to(root)} · {p.stat().st_size} bytes')
 print('NETWORK REQUESTS: 0')
 print('END OMEGA 0.17 SOURCE INVENTORY')
 return 0
if __name__=='__main__':raise SystemExit(main())

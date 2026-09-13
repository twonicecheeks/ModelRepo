#!/usr/bin/env python3
"""Offline inventory of local NFL source/provider support relevant to live OMEGA roles."""
from pathlib import Path
import argparse,json,re
KEYS=('injur','roster','depth','inactive','active','starter','player','schedule','snap')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args();root=Path(a.root).resolve()
 print('OMEGA 0.14 — LOCAL LIVE-SOURCE INVENTORY (NO NETWORK)')
 print(f'ROOT: {root}')
 sidp=root/'data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT'
 if sidp.exists():
  sid=sidp.read_text().strip();mp=root/'data/raw/nfl/nflverse/snapshots'/sid/'SOURCE_MANIFEST.json'
  print(f'Current Phase1 snapshot: {sid}')
  if mp.exists():
   j=json.loads(mp.read_text()); assets=sorted({str(x.get('source')) for x in j.get('assets',[])})
   print('Frozen snapshot source kinds: '+', '.join(assets))
   live=[x for x in assets if any(k in x.lower() for k in KEYS)]
   print('Potential role/status-related source kinds: '+(', '.join(live) if live else 'NONE'))
 else: print('Current Phase1 snapshot pointer: MISSING')
 paths=[]
 for base in (root/'packages/providers',root/'packages/models/nfl',root/'scripts/nfl'):
  if not base.exists():continue
  for p in base.rglob('*'):
   if p.is_file() and p.suffix.lower() in {'.py','.js','.ts','.json','.md','.command'}:
    try:text=p.read_text(errors='ignore')
    except Exception:continue
    hits=sorted({k for k in KEYS if re.search(k,text,re.I)})
    if any(k in hits for k in ('injur','roster','depth','inactive','active','starter')):paths.append((str(p.relative_to(root)),hits))
 print(f'Local files mentioning availability/depth concepts: {len(paths)}')
 for p,h in paths[:80]:print(f'  {p} :: {", ".join(h)}')
 if len(paths)>80:print(f'  ... {len(paths)-80} more')
 print('NETWORK REQUESTS: 0')
 print('END OMEGA 0.14 SOURCE INVENTORY')
 return 0
if __name__=='__main__':raise SystemExit(main())

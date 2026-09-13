#!/usr/bin/env python3
"""Research-only fair T+A line ladder from the current OMEGA 0.15 distribution."""
from __future__ import annotations
import argparse,csv,json,sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--mean',type=float,required=True,help='Independent OMEGA xTC mean')
    ap.add_argument('--snap-share',type=float,required=True,help='H012 predicted snap share, not realized target snaps')
    ap.add_argument('--min-line',type=float,default=0.5)
    ap.add_argument('--max-line',type=float,default=14.5)
    ap.add_argument('--csv',default='')
    a=ap.parse_args();root=Path(a.root).resolve()
    sys.path.insert(0,str(root/'packages/models/nfl/omega'))
    import tackle_count_distribution as d
    ptr=root/'data/models/nfl/CURRENT_OMEGA_TACKLE_DISTRIBUTION'
    if not ptr.exists():raise SystemExit('FAIL OMEGA 0.15 distribution pointer missing')
    sid=ptr.read_text().strip();sp=root/'data/models/nfl/omega_tackle_015_distribution'/sid/'OMEGA_0.15_DISTRIBUTION_SPEC.json'
    if not sp.exists():raise SystemExit('FAIL OMEGA 0.15 distribution spec missing')
    s=json.loads(sp.read_text()); model=s['selectedArchitecture']; params=s['distribution']['productionResearchParamsFitThrough2024']
    tier=d.role_tier(a.snap_share)
    line=a.min_line;rows=[]
    while line<=a.max_line+1e-9:
        p=d.over_probability(line,a.mean,model,params,tier)
        rows.append({'line':round(line,1),'overProbability':p,'underProbability':1-p,'fairOverAmerican':d.fair_american(p),'fairUnderAmerican':d.fair_american(1-p)})
        line+=1.0
    print('OMEGA 0.15 FAIR T+A LADDER — RESEARCH ONLY')
    print(f'xTC mean {a.mean:.3f} · H012 predicted snap share {a.snap_share:.3f} · role {tier} · distribution {model}')
    print('line   P(over)   fair over   P(under)  fair under')
    for r in rows:
        print(f"{r['line']:>4.1f}   {r['overProbability']*100:>6.2f}%   {r['fairOverAmerican']:>9.0f}   {r['underProbability']*100:>7.2f}%   {r['fairUnderAmerican']:>10.0f}")
    print('STATUS: RESEARCH_ONLY — not VERIFIED Trust; sportsbook settlement/source gates remain open')
    if a.csv:
        p=Path(a.csv).expanduser();p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        print(f'CSV: {p}')
    return 0
if __name__=='__main__':raise SystemExit(main())

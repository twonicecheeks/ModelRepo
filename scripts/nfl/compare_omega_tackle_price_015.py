#!/usr/bin/env python3
"""Research-only downstream comparison of an independent OMEGA probability to a posted two-way price."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--mean',type=float,required=True)
    ap.add_argument('--snap-share',type=float,required=True)
    ap.add_argument('--line',type=float,required=True)
    ap.add_argument('--over-price',type=float,required=True)
    ap.add_argument('--under-price',type=float,required=True)
    a=ap.parse_args();root=Path(a.root).resolve();sys.path.insert(0,str(root/'packages/models/nfl/omega'))
    import tackle_count_distribution as d
    ptr=root/'data/models/nfl/CURRENT_OMEGA_TACKLE_DISTRIBUTION'
    if not ptr.exists():raise SystemExit('FAIL OMEGA 0.15 distribution pointer missing')
    sid=ptr.read_text().strip();sp=root/'data/models/nfl/omega_tackle_015_distribution'/sid/'OMEGA_0.15_DISTRIBUTION_SPEC.json'
    s=json.loads(sp.read_text());model=s['selectedArchitecture'];params=s['distribution']['productionResearchParamsFitThrough2024'];tier=d.role_tier(a.snap_share)
    po=d.over_probability(a.line,a.mean,model,params,tier);pu=1-po
    bo=d.american_break_even(a.over_price);bu=d.american_break_even(a.under_price);mo,mu=d.proportional_devig(a.over_price,a.under_price)
    print('OMEGA 0.15 PRICE COMPARISON — RESEARCH ONLY / DOWNSTREAM')
    print(f'xTC {a.mean:.3f} · line {a.line:.1f} · role {tier} · distribution {model}')
    print(f'OMEGA over {po*100:.2f}% · fair {d.fair_american(po):.0f} · posted {a.over_price:+.0f} · break-even {bo*100:.2f}% · ROI {d.expected_roi(po,a.over_price)*100:+.2f}%')
    print(f'OMEGA under {pu*100:.2f}% · fair {d.fair_american(pu):.0f} · posted {a.under_price:+.0f} · break-even {bu*100:.2f}% · ROI {d.expected_roi(pu,a.under_price)*100:+.2f}%')
    print(f'Proportional no-vig market opinion: over {mo*100:.2f}% / under {mu*100:.2f}%')
    print(f'Model-vs-no-vig over disagreement: {(po-mo)*100:+.2f} percentage points')
    print('IMPORTANT: posted break-even decides mechanical EV; de-vig market probability is a sanity check only and never enters OMEGA-I.')
    print('STATUS: RESEARCH_ONLY — settlement mapping, live role source, prospective calibration and CLV gates remain open')
    return 0
if __name__=='__main__':raise SystemExit(main())

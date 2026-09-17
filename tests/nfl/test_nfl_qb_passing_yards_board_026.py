#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))

import qb_passing_yards_market_025 as q25
import qb_passing_yards_board_026 as q26


def main() -> int:
    q=q26.parse_quote('Novig|249.5|-102|-102',q25)
    assert q['book']=='Novig' and q['line']==249.5 and q['overAmerican']==-102 and q['underAmerican']==-102
    q2=q26.parse_quote('Book X|250.5|NA|+105',q25)
    assert q2['overAmerican'] is None and q2['underAmerican']==105
    try:
        q26.parse_quote('Bad|250.0|-110|-110',q25)
        raise AssertionError('whole-number board line should fail')
    except ValueError:
        pass

    side=q25.market_side_summary(0.5141,-102,0.5)
    side=q26.add_probability_ci(side,[0.4948,0.5346],-102,q25)
    side['shadowDisposition']=q26.shadow_disposition(side)
    assert side['expectedRoiPct']>0
    assert side['expectedRoiPctCi95'][0]<0
    assert side['shadowDisposition']=='POINT_POSITIVE_SHADOW'

    robust=q25.market_side_summary(0.60,+110,0.5)
    robust=q26.add_probability_ci(robust,[0.56,0.64],110,q25)
    assert q26.shadow_disposition(robust)=='ROBUST_POSITIVE_SHADOW'

    neg=q25.market_side_summary(0.48,-110,0.5)
    neg=q26.add_probability_ci(neg,[0.45,0.51],-110,q25)
    assert q26.shadow_disposition(neg)=='NEGATIVE_EV_SHADOW'

    rows=[
        {'book':'A','line':249.5,'sides':{'OVER':side,'UNDER':neg}},
        {'book':'B','line':248.5,'sides':{'OVER':robust,'UNDER':neg}},
    ]
    best=q26.best_priced_side(rows)
    assert best is not None and best['book']=='B' and best['side']=='OVER'

    print('PASS NFL QB Model 0.2.6 board contracts · multi-book shadow only · no execution promotion')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

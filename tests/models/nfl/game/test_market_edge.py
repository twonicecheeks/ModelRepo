#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import market_edge as m
assert abs(m.american_to_implied(100)-.5)<1e-12
assert abs(m.american_to_implied(-110)-(110/210))<1e-12
p=m.two_way_no_vig(-110,-110)
assert abs(p-.5)<1e-12
r=m.compare_market(.55,-110,-110)
assert abs(r['edgeProbabilityPoints']-5.0)<1e-9
assert r['expectedROI']>0
print('PASS downstream NFL market-edge math')

#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import phase2d_hardening as h

# Calibration should recover near-identity on a simple internally consistent sample.
ys=[0,0,0,1,1,1,1,1]
ps=[.12,.22,.35,.55,.62,.72,.82,.9]
c=h.calibration_intercept_slope(ys,ps)
assert isinstance(c['intercept'],float) and isinstance(c['slope'],float)
assert c['slope']>0

d=h.brier_decomposition(ys,ps,bins=4)
assert d['uncertainty']>0 and d['reliability']>=0 and d['resolution']>=0

records=[]
for season in (2022,2023,2024):
    for week in range(1,5):
        for i in range(2):
            # challenger always closer to y than base
            y=(week+i+season)%2
            pb=.6 if y else .4
            pc=.75 if y else .25
            lr=h.loss_record(y,pb,pc); lr.update({'season':season,'week':week}); records.append(lr)
b=h.paired_block_bootstrap(records,reps=300,seed=7)
assert b['brierImprovement']['ci95Low']>0
assert b['logLossImprovement']['ci95Low']>0
print('PASS Phase2D hardening primitives')

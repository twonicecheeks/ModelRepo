"""Reproduce the sealed report in a temporary directory without replacing it."""
import json
import math
import sys
import tempfile
from pathlib import Path
from run_mlb_backtest import run,ROOT

def same(a,b):
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    if isinstance(a,float) or isinstance(b,float):return isinstance(a,(int,float)) and isinstance(b,(int,float)) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-10)
    return a==b

with tempfile.TemporaryDirectory() as temp:
    original=json.loads((ROOT/'audit/mlb/BACKTEST_REPORT.json').read_text())
    actual=run(Path(temp))
    if not same(actual,original):raise SystemExit('Packaged backtest differs from the fresh offline reproduction.')
    sealed=json.loads((ROOT/'audit/mlb/FROZEN_MODEL.json').read_text())
    reproduced=json.loads((Path(temp)/'FROZEN_MODEL.json').read_text())
    for key in ['usage','calibration','protocol_sha256','training_targets_through','model_version']:
        if not same(sealed[key],reproduced[key]):raise SystemExit('Frozen model differs: '+key)
print('PASS: report and frozen parameters reproduce (numeric tolerance 1e-10). Betting edge remains unverified.')

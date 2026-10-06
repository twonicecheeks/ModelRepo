"""Reproduce the sealed DELTA report in a temporary directory, preserving freezes."""
import json
import math
import tempfile
from pathlib import Path
from run_delta_backtest import ROOT, run


def same(a,b):
    if isinstance(a,dict):
        assert set(a)==set(b)
        for k,v in a.items():
            if k not in {'created_at','frozen_at'}:same(v,b[k])
    elif isinstance(a,list):
        assert len(a)==len(b)
        for x,y in zip(a,b):same(x,y)
    elif isinstance(a,float):assert math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-10),(a,b)
    else:assert a==b,(a,b)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        out=Path(tmp);run(out)
        for name in ['BACKTEST_REPORT.json','FROZEN_MODEL.json']:
            same(json.loads((ROOT/'audit/delta'/name).read_text()),json.loads((out/name).read_text()))
    print('PASS DELTA chronological replay, model parameters and source hashes; saved freeze unchanged.')


if __name__=='__main__':main()

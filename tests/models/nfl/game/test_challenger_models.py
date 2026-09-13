#!/usr/bin/env python3
import sys, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import challenger_models as cm

def test_simplex():
    w=cm.simplex_project([1.2,-.2,.4]); assert all(x>=0 for x in w); assert abs(sum(w)-1)<1e-9

def test_sparse_names():
    names=['rest_days_diff','missing__rest_days_diff','std_off_dropback_epa_diff','missing__std_off_dropback_epa_diff','std_off_rush_epa_diff']
    got=cm.sparse_passing_feature_names(names); assert 'std_off_dropback_epa_diff' in got; assert 'std_off_rush_epa_diff' not in got

def test_generic_logit_direction():
    xs=[];ys=[]
    for i in range(80):
        x=(float(i-40),0.0); xs.append(x); ys.append(1 if i>=40 else 0)
    m=cm.fit_generic_logit(xs,ys,['x','miss'],l2=.03)
    assert m.predict((10.0,0.0))>m.predict((-10.0,0.0))

def test_margin_probability():
    xs=[];marg=[]
    for i in range(100):
        z=(i-50)/5; xs.append((z,)); marg.append(2*z)
    m=cm.fit_ridge_margin(xs,marg,['x'],l2=.1)
    assert m.win_probability((5.0,))>.5; assert m.win_probability((-5.0,))<.5

def test_pool():
    rows=[];ys=[]
    for i in range(120):
        y=1 if i%2 else 0; ys.append(y)
        good=.75 if y else .25; weak=.56 if y else .44
        rows.append((good,weak,.5))
    p=cm.fit_logit_pool(rows,ys)
    assert abs(sum(p.weights)-1)<1e-9 and p.weights[0]>=p.weights[2]

def test_disagreement():
    assert cm.model_disagreement([.5,.5,.5])==0
    assert cm.model_disagreement([.2,.8])>0.2

if __name__=='__main__':
    for f in [test_simplex,test_sparse_names,test_generic_logit_direction,test_margin_probability,test_pool,test_disagreement]:f()
    print('PASS challenger model tests')

#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, math, sys
from pathlib import Path

HERE=Path(__file__).resolve().parents[2]
MOD=HERE/'packages/models/nfl/omega/tackle_count_distribution.py'
spec=importlib.util.spec_from_file_location('tackle_count_distribution',MOD)
d=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(d)

# Role tiers are based on predicted exposure only.
assert d.role_tier(0.0)=='LOW'
assert d.role_tier(0.349)=='LOW'
assert d.role_tier(0.35)=='ROTATIONAL'
assert d.role_tier(0.65)=='STARTER'
assert d.role_tier(0.85)=='EVERY_DOWN'

# Discrete probabilities must be coherent and line ladders monotone.
for model,params,tier in [
    ('POISSON',{},None),
    ('NB_GLOBAL',{'globalSize':5.0},None),
    ('NB_ROLE',{'globalSize':5.0,'size_EVERY_DOWN':8.0},'EVERY_DOWN'),
]:
    ps=[d.over_probability(x+0.5,7.2,model,params,tier) for x in range(0,15)]
    assert all(0<=p<=1 for p in ps)
    assert all(a>=b-1e-12 for a,b in zip(ps,ps[1:])),(model,ps)

# PMFs approximately sum to one over a generous support.
for model,params,tier in [('POISSON',{},None),('NB_GLOBAL',{'globalSize':3.0},None)]:
    s=sum(math.exp(d.logpmf(y,6.5,model,params,tier)) for y in range(0,80))
    assert abs(s-1.0)<1e-8,(model,s)

# NB2 variance exceeds Poisson when size is finite (checked via moments).
mu=6.0;k=3.0
probs=[math.exp(d.nb2_logpmf(y,mu,k)) for y in range(0,100)]
mean=sum(y*p for y,p in enumerate(probs)); var=sum((y-mean)**2*p for y,p in enumerate(probs))
assert abs(mean-mu)<1e-6,(mean,mu)
assert abs(var-(mu+mu*mu/k))<1e-5,(var,mu+mu*mu/k)

# Posted break-even and fair-price mechanics.
assert abs(d.american_break_even(-120)-120/220)<1e-12
assert abs(d.american_break_even(150)-100/250)<1e-12
assert abs(d.expected_roi(0.60,-120)-(0.60*(100/120)-0.40))<1e-12
po,pu=d.proportional_devig(-120,-102)
assert abs((po+pu)-1.0)<1e-12
assert po>0.5

# Overdispersed deterministic sample should not force Poisson-like size.
rows=[]
actual=[0,1,2,2,3,4,5,6,7,8,9,10,12,14,16,18]*30
for i,y in enumerate(actual):
    s=[0.2,0.5,0.75,0.92][i%4]
    rows.append({'predicted_xtc':6.5,'actual_xtc':y,'role_tier':d.role_tier(s)})
size=d.fit_global_size(rows)
assert size<500.0
for model in ('POISSON','NB_GLOBAL','NB_ROLE'):
    params=d.fit_params(rows,model)
    met=d.evaluate_rows(rows,model,params)
    assert math.isfinite(met['countNLL']) and math.isfinite(met['thresholdBrier'])

print('PASS OMEGA 0.15 distribution contracts')

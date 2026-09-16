#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'packages/models/nfl/game/state_exposure_interaction_research.py'
spec=importlib.util.spec_from_file_location('m',p)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

# Strict development boundary.
assert m.assert_development_only([2016,2024]) == (2016,2024)
try:
    m.assert_development_only([2025])
except ValueError as e:
    assert 'sealed 2025 holdout' in str(e)
else:
    raise AssertionError('2025 must stay sealed')

# Cross-sectional lagged pressure tiering.
prior={
    'A':{'dropbacks':100,'sacks':3},
    'B':{'dropbacks':100,'sacks':5},
    'C':{'dropbacks':100,'sacks':7},
    'D':{'dropbacks':100,'sacks':9},
    'E':{'dropbacks':10,'sacks':3},
}
tiers=m.assign_pressure_tiers(prior,min_prior_dropbacks=20)
assert tiers['A']['tier']=='LOW'
assert tiers['D']['tier']=='HIGH'
assert 'E' not in tiers

# Synthetic interaction: elite pass rush separates more in exposed states.
records=[]
def add(game,tier,exp,n,sacks):
    for i in range(n):
        records.append({'game_id':f'{game}_{i//10}','season':2024,'pressure_tier':tier,'exposure':exp,
                        'sack':1 if i<sacks else 0,'conversion':0,'epa':0.0})
add('lb','LOW','BASE',100,5)
add('le','LOW','ELEVATED_PLUS',100,7)
add('hb','HIGH','BASE',100,7)
add('he','HIGH','ELEVATED_PLUS',100,14)
add('mb','MID','BASE',100,6)
add('me','MID','ELEVATED_PLUS',100,10)
s=m.summarize_exposure_records(records)
assert round(s['interaction']['base_high_minus_low_sack_rate'],4)==0.02
assert round(s['interaction']['exposed_high_minus_low_sack_rate'],4)==0.07
assert round(s['interaction']['difference_in_differences'],4)==0.05

boot=m.cluster_bootstrap_interaction(records,reps=100,seed=1)
assert 'difference_in_differences' in boot['metrics']

print('PASS NFL State Intelligence 0.1.2 exposure x lagged pass-rush contracts · 2025 sealed')

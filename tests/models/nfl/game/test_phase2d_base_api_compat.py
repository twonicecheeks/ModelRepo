#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import research_model as rm

# The historical Phase2A model exposes predict_proba(), not predict().
assert hasattr(rm.LogisticModel, 'predict_proba')
assert not hasattr(rm.LogisticModel, 'predict')

# Exercise the real Phase2A fitter/API on a tiny schema-valid sample.
p=len(rm.expanded_feature_names())
x0=tuple(0.0 for _ in range(p))
x1=tuple((0.2 if i % 2 == 0 else 0.0) for i in range(p))
examples=[
    rm.Example('2019_01_A_B',2019,1,'A','B',x0,0),
    rm.Example('2019_02_A_B',2019,2,'A','B',x1,1),
    rm.Example('2019_03_A_B',2019,3,'A','B',x0,0),
    rm.Example('2019_04_A_B',2019,4,'A','B',x1,1),
]
model=rm.fit_logistic(examples,l2=0.3,max_iter=2)
prob=model.predict_proba(x0)
assert 0.0 < prob < 1.0

script=(ROOT/'scripts/nfl/build_phase2d_hardening.py').read_text()
assert 'model=rm.fit_logistic(train,l2=base_l2)' in script
assert 'pred_base[e.game_id]=model.predict_proba(e.x)' in script
assert 'pred_base[e.game_id]=model.predict(e.x)' not in script
print('PASS Phase2D.2 historical Phase2A LogisticModel API compatibility')

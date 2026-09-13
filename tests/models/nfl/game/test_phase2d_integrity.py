#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
hard=(ROOT/'scripts/nfl/build_phase2d_hardening.py').read_text()
safe=(ROOT/'scripts/nfl/build_phase2d_safe_context.py').read_text()
# Fitter must remain market-blind.
assert 'import market_edge' not in hard and 'from market_edge' not in hard
assert 'OddsPapi' not in hard or 'oddsPapiRequests' in hard
# Holdout branch must skip 2025 before parsing the binary target.
pos_skip=hard.index('if season>=2025: continue')
pos_label=hard.index('if r.get("home_win")')
assert pos_skip < pos_label
# Exact Phase2A parity must use the original Phase2A fitter, never a numerical surrogate.
assert 'model=rm.fit_logistic(train,l2=base_l2)' in hard
assert 'model.predict_proba(e.x)' in hard
assert 'pred_base[e.game_id]=model.predict(e.x)' not in hard
assert 'fit_phase2a_compatible_fast' not in hard
# Context feature claims must use one common Phase2C IRLS solver and include a solver-control base.
assert 'solver_controlled_base' in hard
assert 'model=pm.fit_fast_logit' in hard
assert 'solver_controlled_base_vs_full_targetweek' in hard
assert 'solver_controlled_base_vs_strict_lag' in hard
# Strict-lag builder may reuse snap counts but must not read weekly roster assets.
assert 'weekly_rosters' not in safe
assert 'target-week roster rows read: 0' in safe
# Existing immutable safe context must be verified/recovered rather than overwritten.
assert 'STRICT-LAG CONTEXT RECOVERY' in safe
assert 'restored CURRENT_PHASE2D_SAFE_CONTEXT pointer' in safe
print('PASS Phase2D.2 integrity / base-API / exact-parity / solver-control boundaries')

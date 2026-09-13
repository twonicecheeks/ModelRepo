# MODEL NFL 2.9.0 Phase 2F — Frozen Holdout Gate

Phase 2F is the transition from development to a one-shot untouched 2025 evaluation.
It does not add a new football hypothesis. It freezes the Phase 2E SAFE stage-blend
specification before any 2025 label scoring.

Frozen primary specification:
- strict-lag QB/personnel context only; no target-week roster;
- candidate `safe_no_last4_no_turnover_no_rush_epa`;
- L2 lambda 0.3 for SAFE and solver-controlled base;
- stage context weights Week 1 = 0.00, Weeks 2–4 = 1.00, Week 5+ = 0.75;
- final coefficient fit uses 2016–2024 REG only;
- 2025 never fits coefficients and never selects features/hyperparameters/stage weights;
- sportsbook/market fields are forbidden.

The holdout is split into three explicit operations: freeze spec, generate immutable
blind 2025 predictions, then score those predictions exactly once. Scoring writes a
persistent `HOLDOUT_2025_CONSUMED.json` marker and refuses a second evaluation.

2025 strict-lag personnel features require 2025 snap counts, but only prior games are
used for each target game (G-2 -> G-1). One nflverse snap-count request is allowed on
the blind-input build when the asset is not already cached. OddsPapi requests remain 0.

The precommitted verdict is STRONG_PASS, DIRECTIONAL_PASS, MIXED, or FAIL_BOTH based
only on Brier/log-loss direction and the paired week-block bootstrap. Whatever the
result, 2025 becomes consumed and cannot enter a later tuning loop.

# OMEGA 0.4 — H008 Tackle Opportunity Footprint

## Research question

OMEGA 0.3 showed that a scalar team xTO multiplier did not improve player tackle MAE, even though aggregate count calibration improved. H008 was pre-registered in OMEGA 0.1 and tests a different mechanism: **tackle-generating play topology changes which defenders receive credit**.

## Frozen upstream state

- OMEGA 0.2 total xTO model remains unchanged.
- OMEGA 0.2.2 H012 snap-share/exposure challenger remains frozen as the player exposure component.
- OMEGA 0.3 H011 global opportunity coupling remains rejected and is not blended into the baseline.

## Generative form

For play family `f`:

`predicted_family_opp_f = frozen_xTO * predicted_family_share_f`

`predicted_player_credit_f = predicted_family_opp_f * H012_snap_share * shrunk_player_family_credit_rate_f`

Then:

`xTC_H008 = sum_f(predicted_player_credit_f)`

Families are RUSH, COMPLETE_PASS, SCRAMBLE, SACK, and rare OTHER_PASS.

The family-share forecast is deliberately transparent: the normalized mean of the opponent offense's recent generated tackle-opportunity mix and the defense's recent allowed tackle-opportunity mix, with a strictly-prior league fallback.

## Chronology

2016 seeds history. Hyperparameter selection uses 2021–2023 chronological folds. 2024 is a diagnostic-directed confirmation set, not a pristine holdout. 2025 remains sealed.

## Promotion gate

H008 passes only if it improves overall and core DB/DL/LB MAE versus frozen H012, at least two of the three core positions improve, and the paired game-cluster bootstrap lower bound is above zero. A failed or mixed result may not be rescued through post-hoc family/position cherry-picking.

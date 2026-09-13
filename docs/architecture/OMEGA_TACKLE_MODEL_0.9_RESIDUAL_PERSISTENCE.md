# OMEGA Tackle Model 0.9 — H007 Residual Persistence

## Research question

After frozen H012 exposure and frozen H008 opportunity topology have produced a player tackle expectation, do individual defenders retain a strictly-lagged residual tendency that persists out of sample?

H007 was pre-registered in the OMEGA 0.1 hypothesis registry as **xT+A residual persistence**. It is tested only after H005 failed, and it does not rescue H002/H003/H005.

## Mechanism

For each defender appearance, define the frozen H008 residual:

`residual = actual standard-defensive T+A - H008 predicted T+A`

For a target game, use only the previous eight player residuals. The prior residual mean is shrunk toward zero:

`shrunk_residual = mean(last8 residuals) × n/(n + alpha_games)`

Then:

`H007 = max(0, H008 + gamma × shrunk_residual)`

`gamma=0` is explicitly present in the development grid. Therefore H007 can select the null and collapse exactly to H008.

## Chronology

- Frozen H008 parameters remain unchanged.
- H007 `(alpha_games, gamma)` are selected using 2021–2023 only.
- 2024 remains a diagnostic-directed confirmation set, not a pristine holdout.
- OMEGA 2025 remains sealed.

## Interpretation guard

A positive H007 result would demonstrate residual persistence, not identify its physical cause. The latent residual can reflect unmodeled alignment, tackling skill, teammate geometry, exposure miss, or other stable effects. H007 therefore remains a transparent random-intercept challenger and does not replace causal feature research.

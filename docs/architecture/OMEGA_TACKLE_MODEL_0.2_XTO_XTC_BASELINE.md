# OMEGA Tackle Model 0.2 — xTO/xTC Baseline

OMEGA 0.2 is the first fitted tackle research baseline. It is not a sportsbook model and does not generate prop probabilities.

## Causal decomposition

The baseline begins with two independently measurable quantities:

1. **xTO** — expected standard defensive scrimmage plays that produce at least one original-defense tackle credit.
2. **xTC** — expected player standard defensive tackle-credit units.

xTC is intentionally transparent:

`predicted team defensive snaps × lagged player snap share × position-shrunk lagged standard tackle-credit rate per defensive snap`

The model therefore separates team opportunity volume from player exposure and player credit conversion instead of regressing only on recent tackle totals.

## Chronology

- 2016: history seed only.
- 2017–2023: fit/development targets.
- Hyperparameters: selected with chronological 2021, 2022 and 2023 folds.
- 2024: untouched chronological validation for this 0.2 specification.
- 2025: OMEGA tackle holdout remains sealed and is never read.

## Market isolation

No sportsbook prices, prop lines, implied probabilities, closing lines, or OddsPapi inputs are read. No sportsbook settlement convention is assumed. This phase produces no Over/Under probability and no recommendation.

## What 0.2 is meant to answer

Does a causal, exposure-aware baseline predict tackle opportunity and player standard tackle credits better than simple lagged averages? If yes, future phases can test pre-registered additions such as tackle-funnel rigidity, topology, assist allocation, replacement-role convexity, and special-teams optionality. If no, the baseline must be repaired before complexity is added.

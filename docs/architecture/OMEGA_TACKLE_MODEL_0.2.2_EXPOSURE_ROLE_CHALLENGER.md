# OMEGA 0.2.2 — Exposure / Role Challenger

## Purpose

OMEGA 0.2.1 found that the 0.2 xTC residual moved strongly with player defensive-snap error (`corr ≈ +0.604`). The team xTO residual relationship was positive but materially smaller (`corr ≈ +0.218`). Following the preregistered gate, 0.2.2 tests **H012 exposure prediction only** before H011.

## Single mechanism under test

The 0.2 player model used a simple last-four-games snap-share mean. 0.2.2 replaces only that exposure estimate with a transparent strictly-lagged ridge model using prior role state: last 1/2/4/8 appearance snap shares, recent role volatility/range, role trend, prior-game count, position prior and coarse position group.

It does **not** change the team defensive-snap model, tackle-credit rate/shrinkage, xTO architecture, settlement logic, or any market input.

## Chronology

- 2016: history seed
- 2017–2023: exposure fit universe
- 2021–2023: chronological L2 selection folds
- 2024: diagnostic-directed confirmation. This is not described as a pristine new holdout because 0.2.1's 2024 diagnostics selected H012 as the next mechanism.
- 2025: sealed OMEGA tackle holdout; zero rows may be read.

## Promotion gate

H012 passes only when the selected pre-2024 fold model beats the last-four exposure baseline, 2024 improves snap-share MAE, player defensive-snap MAE and xTC MAE with all non-exposure components frozen, and the paired game-cluster bootstrap lower bound for xTC improvement versus OMEGA 0.2 is above zero.

H011 opportunity-density coupling remains deferred until this exposure question is resolved.

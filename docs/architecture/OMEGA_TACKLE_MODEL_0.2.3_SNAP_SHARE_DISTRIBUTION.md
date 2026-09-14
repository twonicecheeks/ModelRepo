# OMEGA Tackle Model 0.2.3 — Snap-Share Distribution Challenger

Status: **research challenger only**. Frozen OMEGA remains unchanged.

## Why this exists

OMEGA 0.2.1 diagnostics identified player exposure error as the dominant measured
source of xTC error. H012 / OMEGA 0.2.2 therefore replaced the simple recent-snap
baseline with a strictly lagged ridge point estimator. The 2026 Week 1 DAL–NYG
prospective experiment then showed that correcting stale role/exposure assumptions
materially improved aggregate T+A forecast error and Brier score, while also showing
that deterministic starter-to-snap mappings can overcorrect individual players.

The next requirement is therefore not another hand-assigned snap percentage. It is
a calibrated pregame distribution for defensive snap share.

## Target decomposition

This challenger forecasts:

`P(defensive snap share | player records at least one defensive snap, pregame info)`

Availability is intentionally separate. Official inactive status, no-play risk, and
whether a marginal roster player receives any defensive snap are different latent
mechanisms from conditional role/exposure. They must not be hidden inside one noisy
continuous snap-share model.

## Point location: unchanged H012

The distribution layer inherits the existing OMEGA 0.2.2 point model unchanged.
Its pregame features are strictly lagged:

- position prior snap share
- prior-game count / log count
- last-1, last-2, last-4 and last-8 snap share
- last-4 variability / minimum / maximum
- recent role-change deltas
- position group
- cold-start and one-prior-game indicators

No market information is admitted.

## Distribution family

Version 0.2.3 uses a **conditional empirical residual distribution** rather than a
Normal or Beta distribution. Defensive snap share is bounded [0,1], commonly piles
up near role boundaries and 100%, and can be asymmetric when roles are changing.
The empirical family preserves those properties with fewer shape assumptions.

For each calibration row:

1. fit H012 using only seasons before that target season;
2. generate a target-year point prediction;
3. store `actual_snap_share - predicted_snap_share`;
4. condition residual pools using only pregame state.

Pool hierarchy, most specific first:

1. position + history band + predicted role tier
2. position + predicted role tier
3. history band + predicted role tier
4. predicted role tier
5. position
6. global

A pool needs at least 80 observations; otherwise the next hierarchical fallback is
used. At prediction time the selected residuals are added to the point center and
clipped to [0,1]. No residual is selected using the target game's outcome.

## History bands

- `COLD_0`
- `THIN_1_2`
- `DEVELOPING_3_8`
- `ESTABLISHED_9_PLUS`

## Role tiers

The existing OMEGA role boundaries are preserved:

- LOW: < 35%
- ROTATIONAL: 35% to < 65%
- STARTER: 65% to < 85%
- EVERY_DOWN: >= 85%

The distribution emits both continuous quantiles and probabilities of each role tier.

## Chronology and leakage policy

- point-model L2 selection: existing pre-2024 H012 procedure
- empirical residual calibration: 2019–2023
- each calibration target-year point prediction is fit on 2017 through the prior year
- final H012 point fit for the diagnostic: 2017–2023
- 2024: diagnostic-directed confirmation only
- 2025: **sealed; zero rows read**
- 2026: prospective validation only

Because 2024 diagnostics influenced the decision to prioritize exposure research,
2024 must never be described as a pristine new holdout for this lineage.

## Distribution evaluation

The 2024 audit reports:

- snap-share point MAE / RMSE / bias
- empirical distribution mean MAE / RMSE / bias
- CRPS
- PIT deciles
- 50%, 80%, 90% interval coverage and mean width
- Brier score at 35%, 65%, and 85% exposure thresholds
- game-cluster bootstrap of CRPS improvement vs a separately calibrated last-4 distribution
- exposure-only xTC propagation through the unchanged team-snap and tackle-rate components

## Why the baseline also gets a distribution

It would be unfair to compare a probabilistic H012 model with a deterministic last-4
point. Therefore last-4 receives its own chronological empirical residual calibrator
with the same hierarchy and minimum-pool rules. Distribution skill must beat a
probabilistic baseline, not merely a point baseline.

## Next phase: current role-state location model

0.2.3 solves **uncertainty around the H012 location**. It does not by itself solve a
Week-1 location error such as a current starter being centered at 25% snaps.

The next challenger must add current, timestamped pregame role evidence to the
location model while leaving the distribution mechanics frozen. Candidate evidence:

- current depth-chart rank and slot
- first-string vs backup designation
- current-team continuity / team change
- rookie / no-NFL-history status
- within-position-room competition
- official inactive/availability status as a separate gate

nflverse publishes 2026 depth-chart parquet data with GSIS IDs, which makes a Python
adapter feasible without R. Historical 2016–2024 depth-chart data can be normalized
for effect estimation, but source/schema changes from 2025 onward must be explicit.
The 2025 outcomes remain sealed and may not be used to tune the adapter or role effect.

## Promotion rule

No production promotion follows from one diagnostic season or one prospective game.
A distribution/location challenger must demonstrate:

1. improved snap-share probabilistic calibration;
2. improved or non-degraded point exposure accuracy;
3. improved downstream xTC/T+A calibration;
4. prospective 2026 performance across multiple games and role states;
5. no market leakage and no retrospective role edits.

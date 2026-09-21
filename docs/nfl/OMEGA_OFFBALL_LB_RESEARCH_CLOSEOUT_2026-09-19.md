# OMEGA Off-Ball LB Research Closeout — 2026-09-19

Status: **CLOSED / RETAIN FROZEN OMEGA CONTROL**

This document closes the clean off-ball-linebacker tackle-exposure research sequence
that followed the DET@BUF diagnostic work. No challenger in this sequence is
authorized for production or prospective shadow. Frozen/current OMEGA remains the
control for off-ball LB tackle forecasts.

## Final decision

**Do not build OMEGA 0.45.**
**Do not mutate frozen OMEGA LB coefficients.**
**Do not add injury, depth-role, matchup-family, team-pool, or residual corrections
to production H012/H008 on the evidence collected here.**

The only retained infrastructure from this sequence is:
- OMEGA 0.36.3 LB/EDGE archetype classification for role/data hygiene.
- OMEGA 0.39 error-attribution audit as a diagnostic explaining where theoretical
  headroom exists.
- Source/timing audit artifacts that may be reused by future research.

## Evidence ledger

### OMEGA 0.36 — additive LB residual challenger
Result: **REJECTED**

Clean off-ball LB:
- control MAE 2.3750
- shadow MAE 2.3837
- control RMSE 3.0458
- shadow RMSE 3.0293
- bootstrap MAE improvement CI crossed / favored no improvement
- gate: RESEARCH_ONLY_NO_PROMOTION

Interpretation: additive residual correction did not improve count accuracy.

### OMEGA 0.37 — generative team-LB-pool / player-allocation model
Result: **DECISIVELY REJECTED**

Pooled:
- team LB pool MAE 2.5787 -> 2.7459
- allocation-share MAE 0.16036 -> 0.16764
- combined player MAE 2.3750 -> 2.5455
- RMSE 3.0458 -> 3.1757
- positive MAE seasons 0/4

Interpretation: team-pool decomposition made the forecast materially worse.

### OMEGA 0.38 — LB-room completeness audit
Result: **HYPOTHESIS REJECTED**

- explicit off-ball LB rows: 1,414
- high-confidence generic-LB additions: 0
- added actual LB tackle-credit share: 0%
- conclusion: EXPLICIT_ONLY_ROOM_NOT_MATERIALLY_INCOMPLETE

Interpretation: 0.37 was not failing because the clean explicit-LB room was missing a
material share of generic-LB tackle production.

### OMEGA 0.39 — error attribution oracle audit
Result: **DIAGNOSTIC HEADROOM CONFIRMED**

Pooled clean off-ball LB:
- baseline MAE 2.3750
- perfect team-family opportunity oracle gain +0.1528 MAE
- perfect player-snap oracle gain +0.4533 MAE
- perfect opportunity + snap oracle gain +0.6238 MAE

Joint oracle gain by season:
- 2021 +0.7295
- 2022 +0.5485
- 2023 +0.6251
- 2024 +0.5247

Largest family headroom:
- RUSH +0.3992
- COMPLETE_PASS +0.2713
- SCRAMBLE +0.0602
- SACK +0.0230

Interpretation: realized snap exposure and family opportunity explain substantial
historical error, but this is oracle information and cannot itself be used pregame.

### OMEGA 0.40 — realizable joint exposure/opportunity challenger
Result: **REJECTED**

Component changes:
- snap-share MAE 0.15150 -> 0.14779 (+0.00370)
- mean family-opportunity MAE 2.44453 -> 2.43772 (+0.00681)

Player xTC:
- control MAE 2.3750
- exposure-only MAE 2.3772
- opportunity-only MAE 2.3756
- joint MAE 2.3775
- joint RMSE improvement only +0.0027
- joint MAE bootstrap CI [-0.0136, +0.0078]
- positive joint-MAE seasons 2/4
- gate: RESEARCH_ONLY_NO_PROMOTION

Interpretation: the existing pregame feature sets recovered almost none of the 0.39
oracle headroom.

### OMEGA 0.41 — current-role / depth conflict audit
Result: **SIGNAL WEAK**

Depth coverage 93.4%.

Key conflict states:
- STARTER_CONFLICT n=159, mean actual-pred +0.0232, positive residual 51.6%
- BACKUP_CONFLICT n=46, mean actual-pred -0.0656, negative residual 39.1%

Both preregistered gates failed.

Interpretation: simple depth-chart disagreement with H012 is not a stable correction
signal.

### OMEGA 0.42 — exposure residual-structure audit
Result: **NO STRONG OBSERVABLE STRUCTURE**

Pooled:
- n=1,414
- snap MAE 0.15150
- mean actual-pred -0.00159
- material slices: NONE

Audited:
- H012 role band
- recent snap trend
- recent snap volatility
- prior-game history
- clean LB-room size
- teammate snap competition
- depth availability

Interpretation: current H012 pregame state does not reliably identify where the large
snap misses will occur.

### OMEGA 0.43.0 — historical injury/practice source timing
Result: **SOURCE PASSED**

2021-2024:
- GSIS coverage 100%
- schedule join >=99.7%
- date parse 100%
- after-gameday <=0.1%
- duplicate-extra <=0.03%

Only STRICT_PRIOR_DAY records were eligible downstream.
SAME_GAMEDAY remained quarantined.
The nflverse injury source ends after 2024 and is not a 2026 production provider.

### OMEGA 0.43.1 — strict-prior injury/practice signal audit
Result: **SIGNAL WEAK**

- pooled n=1,414
- QUESTIONABLE n=73, mean residual -0.0230
- PRACTICE_DNP n=8, mean residual -0.0853
- PRACTICE_LIMITED n=16, mean residual +0.0286
- PRACTICE_FULL n=147, mean residual +0.0133
- NOT_LISTED n=1,170, mean residual -0.0020
- material slices: NONE

Interpretation: injury/practice status was valid pregame information but did not
provide a stable enough off-ball-LB snap correction.

### OMEGA 0.44 — matchup-conditioned exposure signal audit
Result: **SIGNAL WEAK / RESEARCH STOP**

Pooled n=1,414:
- RUSH r +0.0223
- COMPLETE_PASS r -0.0230
- SCRAMBLE r -0.0042
- SACK r +0.0050
- OTHER_PASS r -0.0056
- PASS_FAMILY r -0.0210
- RUSH_MINUS_PASS r +0.0219
- supporting H012 role bands: NONE

Conclusion:
MATCHUP_CONDITIONED_EXPOSURE_SIGNAL_WEAK

Next gate:
STOP_CURRENT_LB_EXPOSURE_RESEARCH_AND_RETAIN_FROZEN_CONTROL

## What the sequence establishes

1. Off-ball LB remains the weakest major position group for count accuracy, but the
   first-order weakness is not solved by a generic residual model.

2. Perfect knowledge of target-game snap exposure would materially improve historical
   tackle forecasts. This does **not** imply current pregame data can forecast those
   snap deviations.

3. The tested realizable pregame signals did not recover that oracle headroom:
   historical usage, current depth rank/conflict, recent role state, LB-room
   competition, strict-prior injury/practice status, and predicted opponent play-family
   mix all failed the preregistered advancement gates.

4. Continued feature mining on the same information set has high overfitting risk.
   The appropriate action is to stop, retain the frozen control, and wait for a
   genuinely new pregame information source or a materially different modeling
   framework.

## Production state

- DL: frozen/current OMEGA control
- EDGE: frozen/current OMEGA control
- DB: frozen/current OMEGA control
- OFF-BALL LB: frozen/current OMEGA control
- LB/EDGE archetype classifier 0.36.3: retained for identity / role hygiene only
- 0.36 through 0.44 challengers: research evidence only
- frozen OMEGA mutation: **NO**
- 2025 holdout opened: **NO**
- 2026 outcomes used for fitting: **NO**
- market data used for fitting: **NO**

## Reopening rule

Do not reopen off-ball-LB exposure research merely by changing thresholds,
regularization, feature buckets, or combining previously rejected signals.

A new branch should require at least one of:
- a genuinely new timestamp-verifiable pregame role/availability source;
- formation/personnel-package projections available pregame;
- verified coordinator/depth-package information with historical archives;
- a materially different count-generating architecture with a preregistered mechanism;
- prospective evidence showing a systematic failure mode not represented in this
  development sequence.

Until then, frozen OMEGA is the correct control.

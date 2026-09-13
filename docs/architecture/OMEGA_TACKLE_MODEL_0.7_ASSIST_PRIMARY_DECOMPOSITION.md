# OMEGA Tackle Model 0.7 — H004 Assist / Primary Credit Decomposition

OMEGA 0.7 tests one pre-registered mechanism only: whether combined tackle credit is more predictable when official primary credits and assists are modeled as separate processes.

## Frozen champion entering 0.7

- H012 exposure / role forecast: frozen PASS.
- H008 tackle-opportunity footprint: frozen PASS and current T+A champion.
- H011 scalar opportunity coupling: rejected.
- H002 funnel rigidity: mixed / not promoted.
- H003 replacement-role convexity: rejected after development selected beta = 0.

## H004 definition

For standard defensive scrimmage events:

- `PRIMARY = SOLO + PRIMARY_WITH_ASSIST`
- `ASSIST = ASSIST`

OMEGA retains H008's predicted family opportunities and H012's predicted snap share. It estimates player family-specific primary and assist credit rates on the same opportunity-exposure denominator, but shrinks the two classes separately toward strictly-prior position-family priors.

`xTC_H004 = sum_family(pred_opp_family * predicted_snap_share * (shrunk_primary_rate + shrunk_assist_rate))`

Primary and assist shrinkage strengths are selected chronologically on 2021–2023 only. 2024 is diagnostic-directed confirmation, not a pristine holdout. OMEGA 2025 stays sealed.

## Why this is a useful test

If primary and assist credit are simply two labels for the same stable process, H004 should collapse back toward H008. If co-credit assists have different persistence/noise from primary credit, separate shrinkage may improve combined T+A while also creating a future foundation for solo-tackle and assists-only markets.

No sportsbook settlement convention is assumed in this phase. Market data remain downstream and absent.

# OMEGA 0.33 — Week 2 Prior-State Admission + Dual-Track Prospective Freeze

## Purpose

OMEGA 0.33 is the Week 2 operating bridge between the immutable frozen OMEGA control and the validated current-role point challenger. It does not refit or mutate frozen OMEGA.

The Week 2 forecast must be built from information available strictly before Week 2 kickoff. Completed 2026 Week 1 football, tackle and defensive-snap state may enter as prior history. Week 2 outcomes may not enter any feature, target, filter or row universe.

## Tracks

### CONTROL — frozen OMEGA H008 + H012

The control uses the exact serialized OMEGA mean models and frozen NB_ROLE probability parameters. Week 1 2026 results are admitted only as strictly-prior rolling state. Model coefficients remain fit through 2024 exactly as frozen.

The control remains independently scored. Nothing in the current-role layer silently overwrites it.

### ROLE_POINT — preferred exposure challenger

OMEGA 0.31 returned STRONG_CONFIRM for the exact serialized 0.2.7 RoleCorrectionModel on the component-level 2025 confirmatory test. OMEGA 0.32 then showed a positive fixed-mechanism T+A mean diagnostic when only snap-share location was changed.

For Week 2, the role point is therefore the preferred exposure challenger when current depth state is present and the row is not a backup conflict. The challenger changes only snap-share location and the resulting T+A mean; H008 opportunity, play-family shares and shrunk tackle rates remain frozen.

### Probability status

The full empirical snap-share distribution / 0.2.8 mixture remains RESEARCH ONLY and is not emitted as a promoted Week 2 track.

For prospective scoring only, OMEGA 0.33 may emit a ROLE_POINT probability shadow. That shadow changes the count mean to the role-point xTC but deliberately keeps the CONTROL H012 NB_ROLE dispersion tier fixed. This isolates the role-point mean change instead of introducing an unvalidated tier/dispersion change. The shadow is not a promoted probability model.

## Week 2 trust policy

- `ROLE_ALIGNED`: current-role point is preferred exposure challenger; control remains independently visible and scored.
- `STARTER_CONFLICT_REVIEW`: rank 1 with H012 < 0.65. The challenger remains in the predeclared Week 2 preferred universe, but the row carries an explicit warning because the 0.32 starter-conflict T+A subgroup worsened. No post-hoc removal.
- `REVIEW_BACKUP_CONFLICT`: rank 2+ with H012 >= 0.65. Challenger is retained for research but quarantined from preferred exposure use regardless of favorable 2025 post-holdout diagnostics.
- `NO_DEPTH_FALLBACK_H012`: missing current depth state. Role point must fall back exactly to H012.

Availability/no-play probability remains separate. Without an authoritative game-day inactive overlay, rows remain preliminary/research and `verified_ready` remains false.

## Strict prior-state admission gate

Before any Week 2 forecast is created:

1. Capture a fresh isolated 2026 results snapshot.
2. Prove every scheduled 2026 Week 1 REG game is complete.
3. Materialize only Week 1 2026 PBP rows from the results asset.
4. Capture/verify 2026 snap counts and materialize only Week 1 snap rows.
5. Reconstruct Week 1 standard defensive-scrimmage tackle events, H008 team opportunity state, family state, player snap history and player family-rate state.
6. Append Week 1 state after the complete 2025 prior state. No model fitting is permitted.
7. Capture fresh Week 2 roster/injury/depth state before the earliest Week 2 kickoff.
8. Require the captured game IDs to equal the complete 2026 Week 2 REG schedule. A partial slate after the first kickoff is prohibited.
9. For current Week 2 depth, use one exact latest TEAM snapshot as of capture; do not carry a stale player forward merely because that player had an older individual depth row.
10. Derive previous depth role for Week 2 from a depth snapshot strictly before each team’s Week 1 game day.

The freeze must fail closed if Week 1 is incomplete, Week 1 snap data is missing for a scheduled game, the Week 2 capture is not the full scheduled slate, role/depth coverage is suspicious, the Week 2 source was captured at/after kickoff, or packaging finishes at/after the earliest Week 2 kickoff.

## Frozen inputs

OMEGA 0.33 must load rather than refit:

- serialized OMEGA 0.12 `xTOModel`;
- serialized OMEGA 0.12 `H012ExposureModel`;
- frozen OMEGA 0.16 `NB_ROLE` parameters;
- exact serialized OMEGA 0.2.7 current-role correction model.

Required 0.31 gate: current valid component-level confirmatory result must be `STRONG_CONFIRM` with at least 80% depth coverage before ROLE_POINT can be labeled the preferred Week 2 exposure challenger.

## Immutable output

Each freeze is immutable and hash-manifested. Minimum outputs:

- `OMEGA_0.33_WEEK2_DUAL_TRACK.csv`
- `OMEGA_0.33_WEEK2_CONTROL_PROBABILITIES.csv`
- `OMEGA_0.33_WEEK2_ROLE_POINT_SHADOW_PROBABILITIES.csv`
- `OMEGA_0.33_WEEK2_MANIFEST.json`
- `OMEGA_OUTPUT_HASHES.json`

The manifest records source hashes, admitted 2026 weeks, scheduled/completed Week 1 game IDs, Week 1 PBP/snap coverage, role-source capture time, earliest Week 2 kickoff, packaging time, role-model lineage, trust-state counts and all integrity counters.

## Integrity contract

- frozen OMEGA writes: 0
- model refits: 0
- hyperparameter searches: 0
- Week 2 outcome rows materialized: 0
- market fields read: 0
- OddsPapi requests: 0
- full snap-mixture promotion: prohibited
- control and challenger both preserved for prospective scoring
- market comparison occurs only after this freeze

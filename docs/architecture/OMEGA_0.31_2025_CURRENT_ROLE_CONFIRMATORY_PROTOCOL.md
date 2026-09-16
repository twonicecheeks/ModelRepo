# OMEGA 0.31 — Sealed 2025 Current-Role Point Confirmatory Holdout

**Protocol frozen before this evaluator opens 2025 depth-chart or snap-share outcomes for the current-role component.**

## Scientific status

2025 was previously consumed by the project for the older OMEGA 0.13 tackle-count holdout. It is therefore **not a globally virgin season for the project or its human developers**. However, OMEGA 0.2.7 current-role development explicitly read zero 2025 exposure rows and zero 2025 depth-chart rows, and its serialized coefficients were fixed before this test. Accordingly, this is a **component-level confirmatory holdout for the current-role point correction**, not a claim of project-wide blind independence.

No 2025 result from this current-role confirmatory evaluation may be used to alter the frozen 0.2.7 coefficients before the verdict is recorded.

## Purpose

Determine whether the already-fitted OMEGA 0.2.7 current-role **point correction** generalizes to its sealed season strongly enough to change its Week 2 operational status. This is an exposure-model test only. Frozen OMEGA remains the control and is not modified.

## Immutable challenger

The challenger is the exact serialized `RoleCorrectionModel` produced by OMEGA 0.2.7. It was fit only on chronological 2019–2023 correction rows and validated on 2024. The evaluator MUST load that serialized model and MUST NOT refit, retune, select coefficients, alter features, or change clipping after any 2025 row is read.

The H012 anchor is the immutable OMEGA 0.12 blind-2025 `predicted_snap_share` ledger. That ledger was generated week-by-week before each target week's football outcomes were admitted. Expected source snapshot: `20260910T205221Z_58d8156a`; expected blind-ledger SHA256: `59c1a1726bb705661babe3f51fc408e389a25bece6a18df0fdf79065b08d036e`; expected universe: 10,524 conditional-player rows, 272 regular-season games, Weeks 1–18.

## Target

Defensive snap share **conditional on recording at least one defensive snap**, exactly matching the OMEGA 0.2.7 target. Availability/no-play probability is outside this confirmatory test.

## 2025 role inputs

Current weekly depth rank and depth position may be read from the nflverse 2025 weekly depth-chart file only after this protocol is frozen. Rank semantics must match historical development (`depth_team` 1/2/3+). GSIS ID is the identity key; no fuzzy player matching is allowed.

Previous depth state must be strictly earlier than the target week. Week 1 may use the latest 2024 depth state. Same-week or later depth state may not be used as a previous-state feature.

The `last4_snap_share_std` feature may use 2017–2024 history and prior 2025 weeks only. For each 2025 week, every forecast row must be formed before that week's realized snap shares are admitted to rolling state. The evaluator must verify the blind ledger's `prior_games` count against the reconstructed pregame history wherever possible and fail on systematic chronology drift.

## Primary comparison

For every immutable blind-ledger row:

- baseline = H012 blind `predicted_snap_share`
- challenger = frozen 0.2.7 role point prediction applied to that H012 center
- outcome = realized 2025 defensive snap share

Missing current depth state must use the model's frozen exact-H012 fallback (`correction = 0`).

Primary metrics:

- MAE
- RMSE
- bias (prediction minus actual)
- paired game-cluster bootstrap of MAE improvement, where positive means role point is better

Bootstrap is fixed at 10,000 replications with seed `310031`, clustered by `game_id`.

## Predeclared subgroup diagnostics

Report at minimum:

- depth-covered
- rank 1
- rank 2
- rank 3+
- promoted to rank 1
- demoted from rank 1
- Week 1
- Week 1 rank 1
- cold start
- cold-start rank 1
- starter conflict: rank 1 and H012 < 0.65
- backup conflict: rank 2+ and H012 >= 0.65
- DB / LB / DL
- large role disagreement: absolute role correction >= 0.15

Subgroup results are diagnostic unless explicitly included in the gates below. A gate subgroup requires at least 30 rows; otherwise it is `INSUFFICIENT_FOR_GATE`.

## Predeclared confirmatory verdict

Let improvement = H012 loss minus role-point loss, so positive is better.

`STRONG_CONFIRM` requires all of:

1. overall MAE improvement > 0;
2. overall RMSE improvement > 0;
3. game-cluster bootstrap 95% CI lower bound for MAE improvement > 0;
4. starter-conflict MAE improvement >= 0 if n >= 30;
5. Week-1 rank-1 MAE improvement >= 0 if n >= 30.

`DIRECTIONAL_CONFIRM` requires all of:

1. overall MAE improvement > 0;
2. overall RMSE improvement > 0;
3. bootstrap probability that MAE improvement is positive >= 0.90;
4. it does not satisfy `STRONG_CONFIRM`.

`FAIL` applies if overall MAE improvement <= 0 **and** overall RMSE improvement <= 0.

Otherwise verdict is `MIXED`.

Backup-conflict performance is deliberately not a promotion gate because 2024 already identified that subgroup as unsafe. `BACKUP_CONFLICT` remains quarantined for Week 2 regardless of the aggregate verdict; the 2025 result determines whether that quarantine should later be relaxed or strengthened.

## Week 2 mapping

- `STRONG_CONFIRM`: current-role point may become the preferred exposure challenger for depth-covered, non-backup-conflict rows, while frozen OMEGA remains an independently scored control for Week 2. No silent overwrite of frozen OMEGA.
- `DIRECTIONAL_CONFIRM`: current-role point remains parallel challenger; role-conflict quarantine stays active; gather Week 2 prospective evidence before promotion.
- `MIXED` or `FAIL`: current-role point remains research/shadow only; frozen OMEGA remains operational control; role conflicts continue to be quarantined for manual/source review rather than auto-corrected.

The full snap-share distribution mixture is **not** under test here and cannot be promoted by this holdout. OMEGA 0.2.8 mixture remains research-only after its DEN–KC prospective result.

## Integrity requirements

- The current-role component opens 2025 once for this confirmatory purpose.
- Model refits: 0.
- Hyperparameter searches after opening 2025: 0.
- Market fields read: 0.
- OddsPapi requests: 0.
- Frozen OMEGA writes: 0.
- OMEGA 0.2.7 artifact writes: 0.
- No target-week snap outcome may enter any target-week predictor.
- All output is immutable and hash-manifested.

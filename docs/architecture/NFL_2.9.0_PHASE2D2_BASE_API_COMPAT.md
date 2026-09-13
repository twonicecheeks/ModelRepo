# MODEL NFL 2.9.0 Phase 2D.2 — Base API Compatibility + Solver-Control Hardening

Status: historical development only. 2025 remains `HOLDOUT_NEVER_FIT` and is neither opened nor evaluated.

## Defect corrected

Phase 2D attempted to recreate the Phase 2A baseline with a NumPy/vectorized implementation of the original deterministic gradient loop and asserted exact metric parity. On the real snapshot its pooled Brier was `0.2272608247007569` versus the immutable Phase 2A report's `0.22724879787029012`. The difference is numerically small but violates the meaning of an exact lineage check.

Phase 2D.2 regenerates Phase 2A OOF predictions by calling the original `research_model.fit_logistic` routine on the same chronological folds. No numerical substitute is accepted for this historical parity gate.

## Solver-control experiment

A second baseline, `solver_controlled_base`, uses exactly the same deterministic Phase 2C IRLS optimizer, standardization/imputation rules, 2020–2021 L2 selection grid, and 2022–2024 evaluation protocol as the context models. QB/roster feature claims and bootstrap promotion logic are judged against this baseline.

This separates two questions:

1. Did a newer optimizer improve the old team model?
2. After controlling for optimizer and regularization procedure, do QB/roster features still improve prediction?

Only the second question is evidence that the new football context adds independent signal.

## Other hardening retained

- strict-lag QB/personnel provenance challenger;
- season-week block bootstrap for paired Brier/log-loss deltas;
- calibration intercept/slope and Brier decomposition;
- turnover, rush-EPA, last-4 and QB-change-proxy ablations;
- Week 1 / Weeks 1–4 / Week 5+ and QB/roster subgroup diagnostics;
- immutable 2022–2024 OOF ledger;
- downstream-only market edge arithmetic.

## Crash-safe immutable context recovery

If `phase2d_safe_context/<snapshot-id>` already exists, the builder verifies its audit, holdout boundary, target-week-roster boundary, market isolation and files, then atomically restores `CURRENT_PHASE2D_SAFE_CONTEXT`. It never overwrites the immutable directory.

## Holdout / market policy

2025 remains sealed. No historical/live sportsbook field enters feature engineering, regularization selection, fitting, calibration diagnostics or ablation selection. OddsPapi requests are 0. Market comparison remains downstream until the independent specification is frozen.

## Phase 2D.2 compatibility correction

The historical Phase2A `LogisticModel` exposes `predict_proba()`; Phase2D.1 incorrectly called `predict()` in the exact-parity path. Phase2D.2 uses the original public API and includes an automated regression that prevents this mismatch from returning. No model feature, label, market, or holdout policy changed in this patch.

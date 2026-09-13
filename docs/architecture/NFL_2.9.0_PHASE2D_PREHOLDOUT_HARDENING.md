# MODEL NFL 2.9.0 Phase 2D — Pre-Holdout Hardening

Status: historical development only. 2025 remains `HOLDOUT_NEVER_FIT` and is neither opened nor evaluated.

## Why Phase 2D exists

Phase 2C improved the exact Phase 2A baseline on 2022–2024 with QB and roster context, but target-week nflverse weekly-roster provenance does not prove a per-game archived pre-kickoff timestamp. Phase 2D therefore hardens the result rather than opening the holdout.

## Additions

- Persists the first immutable per-game OOF prediction ledger for 2022–2024.
- Reproduces the exact Phase 2A baseline predictions.
- Searches L2 `{0.03, 0.1, 0.3, 1, 3, 10}` on 2020–2021 only.
- Computes diagnostic calibration intercept/slope and Brier decomposition.
- Uses a deterministic season-week block bootstrap for paired Brier/log-loss improvement CIs.
- Runs turnover, rushing-EPA, last-4, and QB-change-proxy ablations.
- Reports Week 1, Weeks 1–4, Week 5+, QB-change, unresolved-QB and roster-continuity subgroups.
- Adds a strict-lag context challenger that never reads target-week roster state.

## Strict-lag challenger

For game G:

- QB state uses only the previous observed primary QB and that QB's strictly prior history.
- Personnel continuity uses snap-count retention from G-2 to G-1.
- Target-week roster membership is not read.
- Target-game PBP/snaps/outcomes are not read.

This challenger cannot know a new target-week starter or injury. That loss of information is intentional: it creates a clean temporal-provenance benchmark.

## Market edge boundary

`market_edge.py` is downstream-only arithmetic. It converts American prices to implied probabilities, removes two-way vig, and computes executable expected ROI after an independent model probability exists. It is not imported by the fitter.

No historical or live market price is used for Phase 2D feature engineering, fitting, regularization selection, ablation selection, or calibration diagnostics. Actual market-edge testing waits until the independent specification is frozen.

## Next gate

Review `PHASE2D_HARDENING.md`, especially bootstrap CIs, strict-lag performance, calibration and ablations. Only then decide whether the independent feature/source specification can be frozen before a single 2025 holdout evaluation.

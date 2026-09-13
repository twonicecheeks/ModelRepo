# NFL 2.9.0 Phase 2E — Safe Freeze Candidate

Status: PRE-HOLDOUT RESEARCH. NOT PRODUCTION.

## Evidence carried forward

Phase 2D.2 established that the solver change did not explain the Phase 2C gain: the solver-controlled base remained essentially identical to Phase 2A. Full target-week QB/roster context improved Brier and log loss with positive season-week block-bootstrap confidence intervals. Strict-lag context improved point estimates but did not clear the same uncertainty gate. The `no_last4` ablation was the best Phase 2D point estimate.

## Phase 2E design

Every Phase 2E context candidate removes the last-4 horizon. Turnover and rushing-EPA families are treated as explicit ablation candidates rather than removed by intuition. Candidate family and L2 are selected only from 2018–2021 walk-forward OOF scores. A season-stage blend (`week1`, `weeks2to4`, `week5plus`) between the solver-controlled base and context candidate is also chosen only from 2018–2021 OOF predictions using a fixed grid of context weights.

2022–2024 are paired evaluation folds. 2025 remains `HOLDOUT_NEVER_FIT` and is never read by this release.

Two branches remain physically distinct:

- SAFE: strict-lag QB and G-2→G-1 snap continuity; no target-week roster.
- FULL: target-week roster/QB proxy context; information upper bound only because exact historical pre-kickoff roster timestamp provenance remains unproven.

A robust SAFE stage blend is the only Phase 2E result eligible to advance to an explicit specification-freeze review. A robust FULL-only result is evidence that current-week availability matters, not permission to use an unproven historical source.

## Market boundary

No sportsbook variable enters candidate selection or model fitting. Market comparison remains downstream after an independent specification freeze and one-time 2025 evaluation.

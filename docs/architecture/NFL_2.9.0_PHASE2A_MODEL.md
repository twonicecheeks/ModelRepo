# MODEL NFL 2.9.0 Phase 2A — Historical Development Model

Status: **DEVELOPMENT ONLY — 2025 HOLDOUT UNTOUCHED — NOT PRODUCTION**

Phase 2A introduces the first fitted NFL game-probability research harness. It is deliberately downstream of the immutable nflverse Phase 1B normalization and upstream of any market comparison.

## Non-negotiable boundary

`nflverse pregame data -> independent historical probability research -> validation`

Sportsbook prices, OddsPapi, spreads, totals, and moneylines are forbidden from the feature matrix. Phase 2A makes zero OddsPapi requests and adds no NFL runtime wiring.

## Development split

- 2015: history seed only (provided by Phase 1B team metrics)
- 2016–2024: development candidates
- 2022–2024: chronological walk-forward validation folds for L2 selection
- 2025: **HOLDOUT_NEVER_FIT; not evaluated in Phase 2A**
- 2026: prospective only

The candidate fit is trained on 2016–2024 only after regularization is selected using development folds. It is explicitly `productionEligible=false`.

## Pre-registered feature family

The feature set is symmetric and interpretable. For each team metric it uses home-minus-away differentials at four pregame horizons:

- prior season
- current season-to-date (`std` in the Phase 1 feature contract)
- last 4 games
- last 8 games

Metrics:

- offensive dropback EPA
- offensive rush EPA
- offensive success rate
- CPOE
- sack rate allowed
- explosive pass rate
- explosive rush rate
- offensive turnover rate
- defensive dropback EPA allowed
- defensive rush EPA allowed
- defensive success rate allowed
- defensive sack rate generated
- defensive explosive pass rate allowed
- defensive explosive rush rate allowed
- defensive takeaway rate

Additional fields are rest-days differential, neutral-site state, and current-season games-available differential. Every base feature has an explicit missingness indicator. Missing numeric values are imputed using development-training means only.

No QB-value coefficient, injury adjustment, weather coefficient, or arbitrary Week-1 point value is introduced here. Those require separate validated providers and evidence.

## Models / baselines

1. Constant historical home-win-rate baseline, fitted inside each chronological fold.
2. Transparent online Elo-style diagnostic baseline (not used for model selection).
3. Standardized L2-regularized logistic regression implemented in pure Python for deterministic, dependency-light research.

Regularization candidates are `0.03, 0.1, 0.3`. Selection criterion is pooled chronological development log loss with Brier score secondary.

## Output

`scripts/nfl/build_phase2_development.command` consumes `CURRENT_PHASE1_SNAPSHOT` and creates an immutable directory:

`data/models/nfl/phase2a/<source-snapshot-id>/`

with:

- `MODEL_SPEC_CANDIDATE.json`
- `MODEL_SPEC_CANDIDATE.sha256`
- `DEVELOPMENT_VALIDATION_REPORT.json`
- `DEVELOPMENT_VALIDATION_REPORT.md`
- `PHASE2A_MANIFEST.json`

The candidate must be reviewed before any 2025 holdout evaluation. Phase 2A contains no command that evaluates the holdout.

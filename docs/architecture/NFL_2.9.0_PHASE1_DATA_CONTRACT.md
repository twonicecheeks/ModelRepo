# MODEL 2.9.0 NFL Phase 1 — nflverse Historical Data Contract

Status: **IMPLEMENTED / LOCALLY TESTED FOUNDATION — NOT A FITTED MODEL — NOT PRODUCTION**  
Date: 2026-09-08

## Purpose

Phase 1 establishes the data and identity rules before any NFL coefficients are fit. The MLB lesson is preserved:

**NFL DATA → INDEPENDENT PROBABILITY → MARKET COMPARISON → TRUST**

No OddsPapi request, sportsbook line, spread, total, or moneyline is needed to build this historical foundation.

## Canonical identity

- Game identity: nflverse `game_id`, formatted as `{season}_{week:02d}_{away_team}_{home_team}`.
- Player identity: nflverse `gsis_id`.
- Team identity: nflverse normalized team abbreviation.
- Names are display fields, not primary join keys.

## Core Phase 1 sources

1. **Schedules** — canonical games, kickoff/context, and postgame target fields. The same table contains historical betting columns; those columns are explicitly quarantined from predictive features.
2. **Play-by-play** — primary source for EPA, success, CPOE, sack, explosive-play, and turnover-propensity research.
3. **Players** — canonical `gsis_id` crosswalk.
4. **Weekly rosters** — historical team/player membership.

Supplemental but not required for the first historical builder: weekly team stats, depth charts, snap counts.

### Injury warning

nflverse's current availability documentation says its injury data source died after the 2024 season. Therefore nflverse injuries are **not** accepted as the future 2026 production injury source. We can use historical injury data for research where valid, but NFL production will need a separately validated current provider.

### Depth-chart warning

The depth-chart source/schema changed beginning in 2025 and became date-based. We therefore defer it until an explicit versioned normalization adapter exists; we will not silently concatenate incompatible schemas.

## Leakage policy

For a target game in season `S`, week `W`:

- Same-season team-performance inputs may use only games with week `< W`.
- Week 1 has no current-season team-performance data and is explicitly `EARLY_SEASON_PRIOR_HEAVY`.
- Prior-season summaries may be carried as named prior fields, never disguised as current-season observations.
- The target game's score/result/total/overtime are target/evaluation fields only.
- Schedule market columns (`home_moneyline`, `away_moneyline`, `spread_line`, spread odds, `total_line`, total odds) are forbidden from the independent feature object.
- 2025 is `HOLDOUT_NEVER_FIT`.
- 2026 is `PROSPECTIVE_ONLY`.

The Phase 1 regression suite mutates current-game scores, current-game market prices, and future team metrics and confirms that the current game's feature object does not change.

## Candidate feature families — not fitted weights

The foundation can materialize interpretable candidates such as:

- offensive/defensive EPA per dropback
- rushing EPA/play
- success rate
- CPOE
- sack rate allowed/generated
- explosive pass/rush rates
- turnover/takeaway propensity
- prior-season priors
- schedule rest/home/neutral-site context

Their presence in the research table does **not** mean they are approved model inputs. Feature selection, transformations, shrinkage, and coefficients must be decided chronologically on development seasons only, then frozen before the 2025 holdout is opened.

## Current code

- Provider contract: `packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json`
- Contract helpers: `packages/providers/nflverse/src/contract.py`
- Historical feature primitives: `packages/models/nfl/game/historical_feature_core.py`
- Provider contract test: `tests/providers/nflverse/test_contract.py`
- Leakage/core test: `tests/models/nfl/game/test_historical_feature_core.py`
- Phase audit: `scripts/nfl/audit_phase1_foundation.command`

## What Phase 1 deliberately does not do

- no fitted NFL probability model
- no arbitrary QB point adjustment
- no extension sport switch
- no NFL Trust board
- no OddsPapi calls
- no player-prop integration
- no production injury claims

The next step after this foundation is to download/version actual historical nflverse snapshots, materialize the leakage-safe game table, and audit row/field coverage before selecting a training window.

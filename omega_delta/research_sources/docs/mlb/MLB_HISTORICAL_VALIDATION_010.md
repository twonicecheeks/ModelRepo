# MLB Historical Validation 0.1.0

Status: **RESEARCH / READ-ONLY**

This layer evaluates historical MLB Moneyline and pitcher-strikeout predictions without mutating the production model, refitting coefficients, or making market/API calls.

## Why this exists

The MLB production system needs two distinct audits:

1. **Probability quality** — is the independent model calibrated and predictive?
2. **Betting quality** — when a historical executable price exists, did the model create CLV and realized ROI?

Those questions must remain separate.

## Required validation rules

- Historical rows must contain only information that was available before first pitch.
- Future games may never enter rolling features.
- A model version must be frozen before its holdout is opened.
- Regular season and postseason are reported separately.
- Market prices remain downstream of independent model probability.
- No coefficient changes are allowed from this evaluator.

## Ledger contract

Common fields:

- `game_id`
- `game_date`
- `season`
- `season_type`: `REG` or `POST`
- `market_type`: `ML` or `K`
- `model_probability`
- optional `model_variant`, `stage`, `thesis`, `trust`, `research_confidence`

Moneyline rows:

- `actual_win`: 0 or 1 for the modeled selection
- optional `selection_team`
- optional `market_probability` (prefer no-vig sharp probability)
- optional `market_odds`
- optional `closing_odds`

Pitcher-K rows:

- `pitcher`
- `side`: `OVER` or `UNDER`
- `line`
- `xk`
- `actual_k`
- optional `market_probability`
- optional `market_odds`
- optional `closing_odds`
- optional `closing_line`

## Metrics

Probability:

- Brier score
- log loss
- probability bias
- fixed-bin calibration / ECE
- directional accuracy (secondary)

K forecast:

- xK bias
- xK MAE
- xK RMSE

Market:

- one-unit-risked ROI
- cumulative profit
- maximum drawdown
- raw implied CLV when entry and close are present
- beat-close rate
- model-vs-market probability edge when a no-vig market probability is supplied

`raw_implied_clv` is deliberately labeled raw. A selected-side close by itself still contains vig. Prefer a paired/no-vig close for final research conclusions.

## Postseason design

Do **not** assume the postseason needs an entirely separate model.

The initial bakeoff should compare:

- `PRODUCTION_BASE`: frozen regular-season production model, unchanged.
- `POST_USAGE`: same probability engine with postseason-specific pregame workload/bullpen exposure inputs.
- `POST_RECAL`: same core model plus a postseason calibration layer fit only on earlier postseason seasons.
- `POST_SEPARATE`: fully separate postseason challenger. This remains research-only unless it wins chronologically out of sample.

The evaluator supports paired variant comparison on identical game/target rows.

### Postseason features to test, not assume

For ML:

- expected starter batters faced / pitches / innings
- bullpen share of expected innings
- bullpen rest and recent high-leverage workload
- off-day schedule and series travel
- starter short rest
- rotation slot / ace concentration
- elimination-game or clinching-game state only if available pregame
- lineup platoon optimization and bench depth

For K:

- starter expected batters faced
- expected pitch count
- opener/bulk semantics
- short-rest state
- opponent lineup K profile
- pitcher/batter quality composition
- bullpen-game probability

The most important distinction is **opportunity vs rate**. Postseason strikeout rates can be high while starter strikeout props are simultaneously hurt by shorter starter exposure.

## Walk-forward standard

Recommended first study window:

- Development: 2015–2022
- Validation: 2023
- Holdout: 2024
- Confirmatory holdout: 2025
- 2026: prospective only

For a stronger regime test, run leave-one-postseason-out / expanding-window validation:

- train through 2018 -> test 2019 postseason
- train through 2019 -> test 2020 postseason
- ...
- train through 2024 -> test 2025 postseason

Never tune on the postseason being reported as holdout.

## Historical data layers

### Layer A — outcomes

Free/public sources can establish:

- final game result
- actual starting pitcher
- actual pitcher strikeouts
- innings/pitches/batters faced
- postseason round / game identity

### Layer B — pregame features

This is the hard part. The replay must reconstruct the same information that existed before the game. Rolling stats must be cut off before first pitch.

Current production ML also uses a current-game starter workload anchor. A historical replay must not substitute realized innings or pitch count. If historical workload-market data are unavailable, report that run as **CORE MODEL / WORKLOAD-PROXY**, not an exact production replay.

### Layer C — historical markets

ML calibration can be tested without prices, but authentic ROI/CLV needs historical market snapshots.

K xK calibration can be tested without historical prop odds, but authentic K ROI/CLV requires historical strikeout lines and prices. Do not fabricate a K market from the actual result or from the model xK.

## Command

```zsh
zsh scripts/mlb/audit_mlb_historical_validation_010.command /path/to/ledger.jsonl "label"
```

The command runs the regression test first, then writes an immutable audit under:

```
data/models/mlb/historical_validation_010/<run_id>/
```

and updates:

```
data/models/mlb/CURRENT_HISTORICAL_VALIDATION_010
```

## Next development gate

1. Inventory current MLB production entrypoints and persisted snapshots.
2. Build immutable historical outcome targets.
3. Build the leakage-safe production-model replay adapter.
4. Run regular-season baseline.
5. Run postseason split.
6. Add `POST_USAGE` challenger first.
7. Only after paired out-of-sample evidence, decide whether a distinct postseason model is justified.


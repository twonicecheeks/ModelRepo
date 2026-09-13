# MODEL active-runtime specification — 3.2.0 target

**Status:** IMPLEMENTED + LOCAL/SYNTHETIC TESTED in prepared source; live provider verification on the user Mac is required after install.

Canonical Chrome source: `/Users/abbeyfelix/Developer/MODEL/apps/chrome-extension/src`  
Canonical local market-service source: `/Users/abbeyfelix/Developer/MODEL/services/market-service/src/model_service.py`  
Managed service runtime: `~/Library/Application Support/MODEL/service/model_service.py`

## Current runtime versions

- Chrome extension: **3.2.0 — Personnel & Matchup Impact**
- Local market service: **2.3.7**
- Trust layer: **3.0.0**
- Data Pipeline: **1.13.0**
- Structured K engine: **1.4**
- K lineage: `mlb-k-v0.8.3-sample-shrinkage-workload-2026-09-07`
- Structured ML engine: **1.3**
- ML lineage: `mlb-moneyline-v0.8.0-offense-strength-2026-09-06`
- Slate Radar: **1.7 — PRELINEUP_ACTIVE_ROSTER_PROXY**
- Research Confirmation Engine: **RCE-0.5 — HARDENED / NON-MUTATING**
- MLB Public Research provider: **0.5.0**
- NFL Public Research provider: **0.4.0**
- Matchup Center: **1.4.0**
- Workspace shell: **1.0**

## Production MLB boundary

The MLB K and ML prediction engines, coefficients, model lineages, Trust thresholds, and target-market separation are unchanged from 3.0.0. Public research remains observational and never mutates K xK, K probability, ML run projection, ML probability, Trust state, or Trust thresholds.

## Matchup Center 1.1

MLB matchup cards now expand across the Workspace and surface the game outlook, current/prior Trust market context, starting-pitcher and K detail, offense/recent form, bullpen context, independent ML projection, sourced material research, and bottom-line diagnostics.

NFL Matchup Center now combines:

- ESPN weekly scoreboard and public market context.
- ESPN per-game summary detail for named injuries/availability, QB context, optional pregame team statistics, weather/venue, and predictor values when ESPN provides them.
- Google News RSS with the existing freshness/relevance classifier.
- Existing OMEGA tackle probabilities/market comparisons through a local **read-only** bridge.

Neutral research is visually de-emphasized. REVIEW/WATCH cards surface the named player or direct topic instead of only a generic warning.

## OMEGA read-only bridge

Local service **2.3.7** adds `GET /v1/nfl/omega/current`. The endpoint reads the current local OMEGA tackle prospective probability ledger and market-comparison ledger, groups them by matchup, and returns a compact display payload.

The endpoint:

- makes **0 OddsPapi requests**;
- does not write to OMEGA data;
- does not rebuild or reweight OMEGA;
- does not create NFL game-side probabilities;
- fails closed to `NOT_AVAILABLE` when current ledgers or the MODEL repository cannot be found.

The existing OddsPapi free-plan policy remains game-market-only for MLB with player-prop requests disabled.

- Matchup Intelligence: **0.2.0** — non-mutating game-level edge ranking; NFL output is public/research context only.

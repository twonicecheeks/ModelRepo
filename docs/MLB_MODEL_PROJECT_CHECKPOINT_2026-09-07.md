# MLB MODEL — Project Checkpoint / New-Thread Handoff
Checkpoint date: 2026-09-07

## Canonical environment
Project root:
`/Users/abbeyfelix/Developer/MODEL`

Chrome must load ONLY:
`/Users/abbeyfelix/Developer/MODEL/apps/chrome-extension/src`

Stable structure:
- `apps/chrome-extension/src/`
- `services/market-service/src/`
- `packages/providers/propsmadness/`
- `packages/providers/mlb_official/`
- `packages/providers/baseball_savant/`
- `packages/providers/oddspapi/`
- `packages/models/mlb/k/`
- `packages/core/`
- `tests/`
- `releases/`
- `archive/migrations/`

Permanent cleanup rule:
**replacement verified -> obsolete implementation removed/quarantined -> active tree cleaned immediately.**
Do not accumulate patch cruft or active versioned runtime folders.

## Current target release
MODEL **2.4.7 — PropsMadness K Market Fallback / OddsPapi Quota Protection**

Important: 2.4.7 still needs its first live post-install Trust audit to be confirmed.

Current K lineage:
`mlb-k-v0.8.2-independent-target-market-2026-09-06`

Current moneyline lineage:
`mlb-moneyline-v0.8.0-offense-strength-2026-09-06`

## Hard OddsPapi constraint
User's OddsPapi plan:
- Free
- 250 requests/month
- NO player props

Therefore:
- Never design OddsPapi player-prop discovery for this account.
- Never spend OddsPapi quota probing pitcher props.
- Reserve OddsPapi for supported game markets.
- K-only workflows must consume **0 OddsPapi requests**.
- Always call it OddsPapi, never "Odds API."

## Current K architecture
PropsMadness provides:
- Strikeouts
- Pitcher Outs
- Earned Runs
- Hits Allowed
- Pitcher Walks
- recent arrays
- season averages
- pitcher grade
- opponent ordinal rankings
- current local K line and prices

MLB Official provides:
- canonical `gamePk`
- official starters
- official MLB player IDs
- official 9-man batting orders

Baseball Savant provides actual pitcher/hitter:
- K%
- Whiff%
- Swing%
- BB%

Derived:
- Contact% = 100 - Whiff%
- SwStr% = Swing% × Whiff%

The Structured K model builds an **independent expected-K distribution**.

CRITICAL:
The target K market has **0 weight** in expected K.
Confirmed fields:
- `targetKMarketWeight: 0`
- `distributionIndependentOfTargetKLine: true`
- `targetKMarketExcludedFromExpectedK: true`
- `marketSeparation: TARGET_K_MARKET_EXCLUDED_FROM_EXPECTED_K`

Only after expected K exists does PropsMadness supply the current K line/price for:
- model P
- local no-vig P when both sides exist
- edge
- fair odds
- listed-price EV

If only one side is priced:
- calculate side-specific EV
- do NOT fabricate a no-vig probability
- WATCH only

## K model mechanics
Workload uses structured Outs / ER / Hits / Walks to estimate expected batters faced.

Pitcher skill + actual official opposing lineup skill produce matchup K%.

Current independent blend:
- Structural: ~70.5128%
- Recent K: ~19.2308%
- Season K/start: ~10.2564%
- Target K market: 0%

Distribution uses overdispersed Poisson-style logic.

Calibration state:
`PROSPECTIVE_INPUT_MIGRATION`

Do not promote to fully validated until forward testing supports it.

## PropsMadness direct structured endpoints
- `/api/offer/mlb/matches`
- `/api/team-rankings/mlb/season/current/all/by-season`
- `/api/offer/mlb/explore/player-strikeouts`
- `/api/offer/mlb/explore/player-pitcher-outs`
- `/api/offer/mlb/explore/player-earned-runs`
- `/api/offer/mlb/explore/player-hits-allowed`
- `/api/offer/mlb/explore/player-walks`

Direct table/API ingestion replaced old pitcher-profile hydration.

Do not return to the old profile-by-profile hydration path unless a needed field is proven unavailable elsewhere.

## Opponent rankings rule
PropsMadness opponent rankings are ordinal 1–30 context only, including:
K, Whiff, Contact, Chase, BB, Pitches/PA, xwOBA, HardHit.

Never convert a rank such as `#8 K%` into an invented raw percentage.

## Moneyline architecture
Current lineage:
`mlb-moneyline-v0.8.0-offense-strength-2026-09-06`

Offense component uses PA-shrunk/weighted:
- wRC+
- ISO
- xSLG
- xwOBA
- BB%
- K%
with top-of-order weighting.

Offense factor roughly clamps 0.86–1.14.
Legacy matchup-offense adjustment was reduced to ~35% to limit double-counting.

MAJOR LIMITATION:
Moneyline still depends partly on legacy PMV1Engine/live-board logic.

Desired next architecture:
PropsMadness structured data
+ MLB Official gamePk/starters/lineups
+ Savant offense/pitcher data
+ bullpen inputs
-> STRUCTURED ML BOARD
-> independent ML probability
-> OddsPapi supported game-market truth
-> Trust

Once parity is proven:
- remove PMV1Engine as production ML source
- physically delete old Hydrate/Batch scanner/parser runtime from `popup.js`
- clean active tree

## OddsPapi game-market policy
OddsPapi is for supported GAME markets only.

Current intended whole-slate refresh books:
- Pinnacle
- Circa
- FanDuel

Expected normal cost:
~3 OddsPapi requests for the entire MLB slate, not per game.
An uncached identity lookup may occasionally add one.

Future: add a visible monthly quota ledger, e.g.
`OddsPapi 73 / 250 used · 177 remaining`

## Static popup/control plane
Popup lifecycle/remount bugs were solved with static hosts in `popup.html`.

Do NOT reintroduce bootstrap/remount observer hacks.

Old Batch Workflow UI remains hidden/quarantined until the remaining legacy runtime can be physically deleted after structured ML migration.

## Current production buttons

### 1. SYNC + BUILD K BOARD
Builds current Structured K data:
- PropsMadness: 5 pitcher markets + matches + rankings = 7 requests
- MLB schedule = 1 request
- Savant current/prior pitchers + batters = 4 requests
- optional MLB boxscore fallback per missing lineup
- OddsPapi = 0

### 2. COPY K BOARD
Copies Structured K output only.
Has copy-success confirmation.

### 3. COPY DATA AUDIT
Copies full pipeline/resource diagnostic.
Has copy-success confirmation.

### 4. CLEAR CURRENT CACHE
Clears current structured working caches only.
Does not delete historical ledgers/snapshots.

### 5. REFRESH K EDGES · 0 API
Uses stored K board + PropsMadness current K market reference.
OddsPapi requests = 0.

### 6. REFRESH ML + ALL · ~3 API
Refreshes supported OddsPapi game-market data and ML/all Trust outputs.
No player props.

### 7. COPY TRUST AUDIT
Copies final Trust audit.
Successful copy visibly shows `COPIED ✓` with persistent confirmation.

## Important recent release history
2.4.0: Structured K integrated.
2.4.1: target K market removed from expected K.
2.4.2–2.4.6: OddsPapi player-prop bridge/discovery/diagnostics attempts.
These are obsolete for this account because the free OddsPapi plan has no player props.
Do not resurrect them.
2.4.7: correct K market architecture using PropsMadness + zero OddsPapi K calls; also fixed null numeric parsing so null cannot silently become 0.

## Remaining problems / priorities

### P0
1. **Live verify 2.4.7**
Run:
- SYNC + BUILD K BOARD
- REFRESH K EDGES · 0 API
- COPY TRUST AUDIT

Confirm:
- K-only refresh mode
- 0 OddsPapi requests
- model probability
- local no-vig probability where possible
- edge / EV
- no OddsPapi prop dependency

2. **Structured moneyline migration**
This is the next major architecture task.

3. **Delete legacy Hydrate/Batch runtime after ML parity**
Do not regex-delete prematurely.
Correct order:
structured ML replacement -> parity test -> physical deletion -> active-tree cleanup.

### P1
4. Build K forward validation:
- expected K
- P over/under
- market line
- price
- closing line/price if available
- actual K
- CLV
- Brier
- log loss
- calibration
- ROI
- version
- buckets / workload types

5. Empirically calibrate K blend and dispersion.

6. Explicit pitcher-role model:
STARTER / OPENER / BULK / UNKNOWN.

7. Investigate whether raw PropsMadness contains multiple sportsbook quotes and, if so, build a multi-book PropsMadness K consensus.

8. Build rigorous moneyline evaluation:
Brier, log loss, calibration, CLV, ROI, edge buckets, favorites/underdogs, offense-factor attribution, bullpen contribution, model-version comparisons.

### P2
9. Automate unattended daily workflow:
morning snapshot -> starter confirmation -> lineup monitoring -> automatic structured refresh -> final pregame board -> save results.

10. Add OddsPapi monthly quota ledger and guardrails.

11. Optional clearly labeled PRELIMINARY pre-lineup mode, never treated as final/actionable.

12. Final UI cleanup after legacy runtime removal:
DATA / K MODEL / ML MODEL / TRUST / HISTORY.

### P3
NFL and CFB are planned only.
Do not start until MLB K, MLB ML, evaluation, and unattended workflow are stable.

## Immediate next sequence
1. Live-test 2.4.7.
2. Confirm K Trust uses PropsMadness and 0 OddsPapi requests.
3. Begin structured moneyline migration.
4. Verify structured ML parity.
5. Physically delete legacy Hydrate/Batch scanner/parser runtime.
6. Build forward-validation/evaluation framework.
7. Automate daily workflow.
8. Add OddsPapi quota ledger.
9. Only then consider NFL/CFB.

## Instructions for a new ChatGPT thread
Attach this file and say:

> Continue the MLB MODEL project from this checkpoint. Treat this file as the current source of truth. Do not resurrect obsolete OddsPapi player-prop work. First confirm where we left off, then continue with the Immediate next sequence.

If the actual installed extension version differs from this checkpoint, report the installed version before modifying anything.

## Non-negotiable assistant behavior
1. Preserve canonical root and stable folder responsibilities.
2. Never forget OddsPapi free-plan constraints.
3. Never call OddsPapi "Odds API."
4. Distinguish implemented/tested from live-verified.
5. Diagnose before patching.
6. Clean obsolete code once replacements are verified.
7. Do not resurrect memory-heavy pitcher-page hydration without proof it is necessary.
8. Target market stays downstream of model probability.
9. Fail closed on questionable identity/data.
10. Every release should provide ZIP, SHA-256, tests/audit, support upgrade from current state, use canonical root, and avoid active versioned runtime clutter.

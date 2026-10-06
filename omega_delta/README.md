# OMEGA 2.1.3 with DELTA 0.1

Local sports research app with an integrated DELTA postseason strikeout model, MLB playoff board, and reproducible historical comparisons. **MLB betting edge is not verified.** Starter K prediction error improved; the moneyline challengers did not improve accuracy. Read MLB_BACKTEST_REPORT.md for the results and limitations.

## Open on your Mac

1. Quit any running OMEGA server with Ctrl+C in its terminal.
2. Unzip OMEGA_DELTA_0.1.3.zip and keep the OMEGA_DELTA_0.1.3 folder together.
3. Double-click Start_OMEGA.command. If macOS blocks it, open Terminal in this folder and run `zsh Start_OMEGA.command`.
4. Open the local address shown in Terminal, normally http://127.0.0.1:8741.

Python 3.10 or newer is required. MLB inference and offline reproduction also require Node 18 or newer. No pip install or npm install is needed. The launcher uses the existing MODEL Python environment when available.

Version 2 reuses your Version 1 records at `~/Library/Application Support/OMEGA Next/omega.sqlite3`. The first launch saves a consistent `omega.pre-v2.sqlite3` copy before initializing the MLB board. Export a current database backup from Data & provenance when desired. A second server is blocked by the existing process lock. To use an isolated workspace, launch with `--data-dir /your/chosen/folder`.

## DELTA workflow

Open **DELTA model** in the MLB sidebar. Refresh a future game in **Playoff board** to save the exact lineup, V2 comparison, DELTA PA and beta-binomial distributions, parameters and source receipts. DELTA appears in the playoff forecast and quote tables. Imported K quotes receive DELTA probabilities, integer push mass, fair odds and EV alongside V2.

The DELTA screen shows hitter-by-hitter K probabilities, workload distribution, chances of exceeding 18 and 27 BF, outcome percentiles, a line/price calculator, source coverage, and a 10,000-draw simulation control. The calculator is illustrative and does not create a quote or bet. Simulations reuse the saved model and profiles, rather than any newer inputs.

Read **DELTA validation**, DELTA_MODEL_STATUS.md and DELTA_RESEARCH_0.1.3.md: the initial PA challenger does not improve V2 on the same 775-start development sample. It is a separate research model, with no promotion. The default automatic path has overall-rate log-5 matchup probabilities and learned prior-season workload uncertainty; conditional hook hazards, hierarchical splits, physical residuals, and arsenal matchups are documented research contracts that require timestamped historical fitting.

The proposed blanket 1.04 October K multiplier and 19-batter hard cap were run as a separate reproducible counterfactual (`tools/evaluate_delta_escalator.py`). The multiplier worsened all reported scores; the cap reduced DELTA's MAE slightly while worsening distribution scores, and all variants still trailed V2. They are absent from live inference. The report is `audit/delta/POSTSEASON_ESCALATOR_EXPERIMENT.json`.

Advanced input JSON can supply sourced platoon rates, pitch traits, arsenal/hitter pitch-type metrics, count-transition probabilities, context and externally fitted feature/hook models. Missing fields receive no automatic multiplier. Importing a profile never changes an old forecast: refresh before first pitch for a new snapshot. DELTA_INPUTS.md documents the contract.

For optional public pitch histories, `tools/delta_sources.py export-players` fetches the confirmed starter and nine hitters through pybaseball, limited to regular-season games by default. The broader `export-statcast` and your own Baseball Savant pitch CSVs remain supported. `tools/export_delta_pbp.R` exports official game play-by-play through baseballr. The cutoff-safe converter verifies batch hashes and writes `DELTA_PROFILE.json` for the DELTA import control, with coverage and separate pitch/PBP research rows. Read DELTA_DATA_SOURCES.md for commands and boundaries: observed splits can enter a new forecast, but pitch traits, count outcomes and manager events need historical fitting before they can add a predictive adjustment. These wrappers are optional and are not installed by OMEGA.

Use **Grade official DELTA counts** to grade saved forecasts without needing a quote. It chooses the latest locally received pre-first-pitch forecast once per game/pitcher, checks the official starting-pitcher identity, keeps missing K ungraded, and records results without refitting. Predictions received after first pitch are excluded even if their source timestamp claims to be pregame.

For historical market benchmarking, use `tools/evaluate_delta_market.py` with an operator-supplied CSV that matches `game_id` and pitcher MLBAM ID to the exact PMFs in `audit/delta/PREDICTIONS.jsonl`. The audit de-vigs two-way prices, handles whole-line pushes, reports opening-price hypothetical ROI, and measures same-line price CLV. It is documented in DELTA_MARKET_BACKTEST.md and remains development evidence until a contemporaneous pregame receipt ledger exists.

The first launch also saves omega.pre-delta-0.1.sqlite3 in the existing data folder; all records continue to use the same database.

## MLB workflow

Open Playoff board, choose the game date, and refresh. The 2026 candidate is frozen; a different season requires revalidation. The collector uses public MLB, Baseball Savant and FanGraphs data. It records every source and saves the input, model identity and forecast before first pitch. No paid market API is called by MLB collection. Both official batting orders, starters and player skill must resolve before a forecast appears. Games that have started are visibly marked and never treated as new pregame opportunities.

The board displays the recovered baseline and research candidates side by side. The current-game workload-anchor guard is implemented in inference; the built-in public collector uses history-based workloads. This release does not connect PropsMadness current-game supporting markets automatically.

Download the MLB quote CSV template from the board. Use MLB gamePk as game_id; ML selections use a canonical team code, such as LAD; K selections require the MLB pitcher ID, exact line and OVER/UNDER. Use American odds, an explicit book/source, UTC capture timestamp and FULL_GAME settlement. Quotes must follow the saved forecast and precede first pitch. Whole K lines include pushes. The board compares V2, DELTA PA and baseline EV; these are research estimates. Imported prices do not establish authenticated entry evidence.

Grade official finals to journal quote outcomes. Scratched pitchers do not inherit the new starter's result. Quotes remain research records; the app does not place wagers or promote a model based on quote returns.

## Reproduce the backtest

Double-click Verify_OMEGA.command, or run `zsh Verify_OMEGA.command` in Terminal. This checks the app and reproduces the complete report and frozen parameters in a temporary directory, without replacing the active candidate.

Actual normalized inference inputs, targets and baseline ledger are in seed/mlb. The full report, frozen parameters and row-level forward predictions are in audit/mlb. Original project source comes from twonicecheeks/ModelRepo at commit 58741f87df8df48e0a42fb36c4bbcbd5a3511c9f. The research builder has an additional input-export hook; model formulas are preserved. The new Python candidate layer is app/mlb_model.py.

For a complete public-source reconstruction, unpack research_sources/MLB_PUBLIC_CACHE.zip into research_sources so that its data/ folder sits alongside packages/ and scripts/. The archive contains actual response payloads and acquisition manifests. Then use the original acquisition/replay scripts with `--root` pointing at that research_sources folder. No reacquisition is needed for the packaged offline backtest.

## Other views

The eight existing NFL, scenario, market, ticket, Polymarket, validation and provenance views remain available. Their existing provider configuration is retained. Optional NFL capture continues to use the existing explicit configuration and call budgets; the MLB collector does not use OddsPapi or The Odds API.

Software checks and historical prediction improvements are separate from profitability verification. This release deliberately leaves the MLB candidates in research until prices and independent outcomes support the edge gates.

# OMEGA Version 2 — MLB playoff backtest

**Verdict: betting edge NOT VERIFIED.** Version 2 integrates new playoff workload and moneyline candidates. The strikeout candidate improves historical prediction error. The moneyline candidates do not improve probability accuracy. No positive-profit claim or model promotion is supported by this run.

## Actual historical evidence

MLB official results cover **440 completed postseason games from 2015–2025**. The recovered engines successfully reproduce 426 games and 852 starter strikeout distributions. Fourteen games are blocked for missing player or historical ruleset data; their identities and reasons are included in the full JSON report.

The paired strikeout comparison contains 775 starts from 2016–2025. The moneyline exposure comparison contains 426 games. Calibration requires at least 60 earlier-season games, leaving 356 paired tests from 2017–2025.

| Starter strikeouts — 775 paired starts | Recovered baseline | V2 playoff candidate |
|---|---:|---:|
| Mean absolute error | 2.1103 | 2.0048 |
| Root mean square error | 2.5872 | 2.4839 |
| Bias, predicted minus actual | +0.8082 | +0.3894 |
| Distribution log loss | 2.3632 | 2.3195 |
| Ranked probability score | 1.4466 | 1.3913 |

MAE improves **5.0%**. Candidate minus baseline MAE is -0.1054. The 95% interval is [-0.1401, -0.0729] when resampling complete series, and [-0.1430, -0.0698] when resampling complete seasons. The calculation uses 2,000 draws with a fixed seed. These intervals describe this development sample, without adjusting for earlier mechanism selection.

| Moneyline probability test | Paired games | Baseline Brier | Candidate Brier | Baseline log loss | Candidate log loss |
|---|---:|---:|---:|---:|---:|
| Short-start exposure | 426 | 0.24863 | 0.24950 | 0.69047 | 0.69229 |
| Exposure + prior-year calibration | 356 | 0.24909 | 0.25066 | 0.69135 | 0.69457 |

Lower scores are better. Both moneyline changes worsen the average. The calibrated change in Brier is +0.00157, with a 95% series interval [-0.00225, 0.00594]. It does not establish improvement. A constant 50% prediction has Brier 0.25 and log loss 0.69315; the calibrated candidate also fails to beat that reference on this paired sample.

## What changed

Starter exposure uses a matched-pitcher postseason outs / late-regular-season outs ratio. The reference window is each pitcher's last 45 regular-season days, requiring at least three starts. Each pitcher-season has equal weight. The current year's postseason outcomes never enter its fitted ratio. The 2026 freeze uses 399 matched pitcher-seasons and an outs factor of **0.832369942196532**. This is a new fit, distinct from the earlier study's different regular-season control cohort.

The K candidate adjusts outs, recomputes batters faced, then retains the recovered pitcher/lineup K skill and historical blend weights. The target strikeout line and price do not determine its expected mean. Current-game workload anchors and explicit manager plans keep their existing leash.

The moneyline candidate permits starts shorter than the recovered engine's 3.5-inning floor. It changes the starter/bullpen innings split while retaining run-rate, park and home-field terms. A second candidate fits an intercept and slope using only earlier postseasons, with a fixed ridge prior (0,1), penalty 1 and minimum 60 training games. Both candidates remain visible for research and are not promoted.

## What prevents an edge claim

- No accepted historical executable entry-price pairs for moneylines or starter K markets. ROI, closing-line value, and performance against market probabilities remain **unmeasured**, rather than zero.
- The inspected SBR-derived archive was excluded: 260 official playoff games failed its date/team identity join, and 180 had no dated record. None were repaired by guessing or matching winners.
- Historical workloads are reconstructed from regular-season logs. Original timestamped current-game Outs/ER/H/BB market packages are unavailable.
- Historical batting orders are recovered from completed-game identities. The feature receipt for an original pregame decision is unavailable. Season-end public skill and park data are reconstructed.
- These seasons were already inspected in prior playoff research. Chronological fitting prevents same-year parameter leakage, but does not turn previously used data into independent confirmation.

The protocol requires genuine pregame book/price/time records, correct identity and settlement, at least 100 qualifying flat-unit wagers across three postseasons, a positive 95% series-cluster ROI lower bound, probability-score improvement over the market, and independent confirmation after the freeze. Those gates have not passed.

## Sensitivity checks

The full report includes every season, 2020 separately, 2020 excluded, and 2022 onward. The K improvement remains visible without 2020 and in the recent format. Every challenger is reported; no profit-maximizing threshold, book or test season was selected after observing results. The fixed research selection threshold is 2% modeled EV with flat one-unit staking; no wager simulation is reported without accepted prices.

## Version 2 workflow and verification

The app has a live official playoff board, a historical backtest view, saved source/forecast receipts, exact game/pitcher quote imports, integer-line push probabilities, and official-final research grading. Imported prices remain unverified. Repeated quotes are not counted as independent wagers. Four actual upcoming games were found on September 30, 2026; all were correctly blocked pending confirmed batting orders and starters.

The existing football views and records remain available. Local verification passed 64 backend checks and ten UI template checks. A ready-state input assembly test reproduces a real historical ML/K projection exactly, and blocks a started game. Other checks mutate future labels, target K lines and prices, enforce pregame timing and exact pitcher identity, and preserve previous snapshots after collection failure. Full visual browser testing was not completed in this environment.

Run `Verify_OMEGA.command` to rerun software checks and reproduce the sealed report offline from the included actual inputs. The parameter comparison permits a 1e-10 numeric tolerance and ignores the new reproduction timestamp; it does not replace the active freeze. The package contains the public raw-data checkpoint, pinned source modules, normalized inputs, outcome targets, folds, predictions, hashes and full report.

**Evidence supports a better historical starter K projection. It does not yet support a verified profitable MLB betting model.**

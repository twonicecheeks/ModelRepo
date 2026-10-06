# MLB model status and DELTA integration — October 6, 2026

DELTA 0.1 is integrated into OMEGA 2.1.3 as a separate MLB postseason research model. The app adds DELTA model and DELTA validation navigation, saved forecasts, hitter-by-hitter probabilities, workload distributions, count probability curves, sourced advanced inputs, reproducible simulation, quote comparison, and official-final starter grading. The initial PA challenger has not improved the existing V2 playoff candidate. Its advanced pitch and manager layers have not been historically validated.

OMEGA 2.1.3 includes optional pybaseball/Statcast CSV and baseballr play-by-play exporters and a cutoff-checked converter. Its targeted mode fetches one starter and the nine confirmed hitters for regular-season games, and the converter verifies batch manifests. It produces exact-ID advanced profiles, source hashes, a coverage report, and separate normalized pitch/game-event rows. Measured hand splits can enter a **new** forecast after import and pregame refresh; pitch traits and PBP event data are still unfitted. No new pitch data were included in the sealed 775-start result. See DELTA_DATA_SOURCES.md for the source roles, commands and timing policy.

DELTA 0.1.3 adds opt-in research contracts for conditional end-of-PA hook hazards, odds-based hierarchical platoon shrinkage, ridge residual features, final-two-confirmed-start velocity measurement, and arsenal-to-lineup whiff summaries. These reports carry source vintages and explicit missing statuses; they do not overwrite the scored PMF. The hazard and residual trainers reject 2026 targets and write `UNVALIDATED_RESEARCH_NO_PROMOTION` artifacts. See DELTA_RESEARCH_0.1.3.md for the table schemas and prospective freeze procedure.

## What the current MLB models produce

| Component | Output and evidence |
|---|---|
| Recovered regular-season K engine 1.4 | Expected starter strikeouts, workload components and a five-component Poisson-mixture count curve. Shrunk pitcher/lineup K, whiff, swinging-strike and contact metrics drive matchup efficiency. Current target K line/price weight is zero; supporting workload markets can be used by the original extension. |
| Recovered moneyline engine 1.3 | Starter/bullpen run expectations, lineup offense strength, park/home adjustments and team win probabilities. Probability accuracy and market edge are separate questions. |
| OMEGA V2 playoff K candidate | Adjusts regular-season-history outs, recomputes BF and preserves the recovered K skill/history blend. The 2026 history outs factor is 0.832369942196532. Current-game anchors and explicit manager plans keep their existing leash. This is not a universal 16.8% K reduction. |
| V2 moneyline challengers | Remove the short-start innings floor and optionally apply prior-year probability calibration. Both remain research because historical probability scores worsened. |
| DELTA PA | A distinct, finite workload-mixture distribution with individual hitter K probabilities; exact probabilities for over, under and integer pushes. |
| DELTA beta-binomial | A workload-mixture comparison using shared efficiency uncertainty. It averages hitter rates conditional on BF, so it does not retain all PA heterogeneity. |
| OMEGA integration | Saves exact input/model/profile snapshots; shows model comparisons; records user-supplied prices separately; simulates saved inputs; grades actual starters independently of whether a quote was captured. |

The standalone public OMEGA collector uses history workload proxies and requires both official batting orders and starters. It does not automatically connect the original extension's current-game Outs/ER/H/BB package. No new OddsPapi player-prop requests or paid market collection were added.

## Where the historical K projections improved and failed

This is the same paired development sample: **775 starter outings from 2016–2025**, with 2015 used as a warm-up. The underlying V2 archive covers 440 official postseason games, 426 successfully replayed games and 852 baseline starter distributions. These are different denominators.

| Model | MAE, K | RMSE, K | Bias, prediction minus actual | Distribution log loss | Ranked probability score |
|---|---:|---:|---:|---:|---:|
| Recovered baseline | 2.1103 | 2.5872 | +0.8082 | 2.3632 | 1.4466 |
| V2 playoff candidate | **2.0048** | **2.4839** | **+0.3894** | **2.3195** | **1.3913** |
| DELTA PA 0.1 | 2.0560 | 2.5510 | +0.4633 | 2.3429 | 1.4313 |
| DELTA beta-binomial 0.1 | 2.0560 | 2.5510 | +0.4633 | 2.3376 | 1.4286 |

Lower errors and distribution scores are better. V2 reduced baseline MAE by about 5.0%, and reduced signed overprediction by about 0.419 K. It still overpredicts on average and has approximately two strikeouts of mean absolute error. The new DELTA proxy reduces error relative to the old baseline but loses to V2 by about 0.0512 K in MAE. Its beta-binomial comparison slightly improves DELTA's distribution score, while both DELTA variants remain worse than V2 on this aggregate sample. Better architecture alone is not evidence of better forecasts.

The full DELTA report contains season-specific results, 2020 excluded, 2022 onward, paired differences and series/season bootstrap intervals. All comparisons are reported; no variant is promoted. Reconstructed historical features and previously inspected test years make this development evidence, not an untouched prospective holdout. This release does not establish current regular-season live accuracy from a new contemporaneous prediction ledger.

## Check of the proposed 4% escalator and 19-BF hook ceiling

The proposed fixed multiplier and hard cap were scored on the same 775 archived starts, with DELTA's other inputs and season-specific frozen parameters held fixed. This is a previously inspected development sample, so it cannot validate a newly selected adjustment. The full reproducible experiment is in `audit/delta/POSTSEASON_ESCALATOR_EXPERIMENT.json` and `tools/evaluate_delta_escalator.py`.

| Variant | K MAE ↓ | Distribution log loss ↓ | Ranked probability score ↓ |
|---|---:|---:|---:|
| V2 reference | **2.0048** | **2.3195** | **1.3913** |
| DELTA current | 2.0560 | 2.3429 | 1.4313 |
| DELTA with 1.04 per-PA multiplier | 2.1033 | 2.3623 | 1.4582 |
| DELTA with 19-BF hard cap | 2.0454 | 2.4166 | 1.4606 |
| DELTA with both | 2.0299 | 2.3962 | 1.4432 |

Of these 775 starters, **455 actually faced more than 19 batters** (512 exceeded 18; 37 exceeded 27). The 4% multiplier worsens all three scores. The cap slightly reduces MAE by truncating a model that overpredicts on average, but substantially worsens the distribution scores and makes common workloads impossible. Both together remain worse than V2 on every displayed score. Neither is applied to the frozen forecast. Workload plans, umpire effects and weather remain candidates for fitting only after timestamped pregame and event-level histories exist.

## Moneyline accuracy

| Comparison | Games | Baseline Brier | Challenger Brier | Baseline log loss | Challenger log loss |
|---|---:|---:|---:|---:|---:|
| Short-start exposure | 426 | 0.24863 | 0.24950 | 0.69047 | 0.69229 |
| Exposure + prior-year calibration | 356 | 0.24909 | 0.25066 | 0.69135 | 0.69457 |

Both challengers worsened the mean probability scores. The calibrated candidate also fails to beat the constant 50% reference on this paired sample. DELTA 0.1 concerns starter strikeouts and does not replace the MLB moneyline forecaster. Authentic historical entry-price pairs are missing, so ROI, CLV and a profitable betting edge remain unmeasured. OMEGA now includes an offline market-audit layer (`tools/evaluate_delta_market.py`) and a CSV contract, but it produces development evidence only after an operator supplies matched lines. It does not change DELTA probabilities or promote a model from closing prices.

## DELTA mathematics and actual fitting

For pitcher p, batter b and league prior l, the initial matchup probability is:

`logit(q_i) = logit(K_p) + logit(K_b) - logit(K_l) + prior-season efficiency intercept`

The rational Log-5 function in the suggested script is algebraically the same matchup calculation. The script's `sum(p*(1-p))` gives variance conditional on a fixed number of independent plate appearances; it omits uncertainty in batters faced and in shared efficiency. DELTA already mixes an explicit BF distribution and calculates the full PA PMF, with a separate beta-binomial comparison. Importing SciPy or NumPy does not itself change the fitted probabilities.

Rates have declared sample shrinkage. Exact hand-specific rates are used only when sourced. Without them, the screen shows Missing. The automatic 0.1 collector does not fabricate a platoon split from a player's overall K rate.

With a saved BF distribution and independently estimated hitter probabilities:

`E[K] = sum_i P(BF >= i) * q_i`

An exact Poisson-binomial recursion calculates the full conditional K distribution for each BF, then mixes over workload. Maximum K is bounded by BF support. Repeating the original nine-player order is the historical proxy; substitutions and dynamic pinch hitters need additional input histories.

The optional beta-binomial uses alpha=q*c and beta=(1-q)*c, with q the mean PA probability conditional on BF. For fixed n and q, its variance is `n*q*(1-q)*(n+c)/(1+c)`: it adds dispersion relative to binomial. It is not an automatic cure for underdispersion, and it is not the general distribution for different independent batter probabilities.

BF residual shape is learned from earlier-season actual BF divided by the V2 expected BF, and centered to retain the V2 workload mean. K outcomes do not fit this workload shape. A scalar efficiency intercept is fitted using earlier-season K/BF. Beta concentration is selected from the declared prior-only grid 5, 20, 100, 500, 5000. Test-season and future labels cannot change that season's fitted parameters. The 2026 artifact is frozen on historical training through 2025.

The default workload mixture assumes conditional independence between efficiency and removal. DELTA also implements an optional pitch-count kernel and a dynamic hook simulation, but absent event-level training histories these remain imported, unvalidated model/scenario inputs. They are not included in the 775-start historical accuracy claim.

## Attachment requirements: implementation versus validation

| Requested layer | DELTA 0.1 implementation | Evidence still needed |
|---|---|---|
| Log-5, exact order, conditional distributions, KSplit-style perspective | Exact PA recursion and workload mixtures; per-hitter display | Pregame splits and substitution histories |
| Beta-binomial | Prior-fitted dispersion comparison, integer push mass | Independent confirmation of distribution calibration |
| 10,000-draw Monte Carlo | Seeded PA/pitch simulation of the saved snapshot | Future outcome calibration |
| Stuff+/PitchingBot, location/command and physical traits | Separate sourced fields and externally fitted feature-model contract | Actual historical features and fitted predictive coefficients |
| CSW, whiff, chase, arsenal-to-lineup matchup | Input fields, weighted pitch-type metrics and optional count model | Historical pitch/count and matchup records; denominators and sample shrinkage |
| Platoon and reverse splits | Uses exact provided rates and hand identity, including switch hitters | Timestamped measured splits; no inferred split percentages |
| Short hook, TTO, runners/runs, pitch count, leverage, bullpen and series | Empirical BF shape; optional state-dependent hook scenario replacing BF draw | Event-level removal decisions, personnel availability, score-state trajectories and trained hazards |
| Umpire, park/weather, maximum effort and familiarity | Sourced context/features; neutral when absent or unfitted | Pregame observations and independently fitted residual effects |
| Postseason escalator and lineup compression | Actual order and exposure modeled explicitly; no blanket boost or penalty | Residual tests avoiding double counting player selection and bullpen usage |
| OMEGA interface | DELTA pages, forecast/price columns, snapshots, simulation, count grading and public-source preparation guide | Native Mac launch and visual browser execution in the user's environment |

The source claims in the attachment were treated as research hypotheses, not established coefficient values. A universal October boost, universal velocity increase, cross-league unfamiliarity reward, fixed 60% hook change or universal 18–21 BF ceiling would inject unsupported numbers. Modern interleague play also makes league membership an inadequate measure of actual familiarity.

## Verification and use

The package includes 100 backend tests, 12-view UI template checks, market-audit edge-case tests, analytical distribution checks, V2 sealed-report reproduction and DELTA replay reproduction. The original V2 engines, frozen parameters and historical data remain preserved. The source converter was exercised on synthetic Statcast/baseballr fixtures and both pybaseball exporters were tested with stubs. A live pybaseball retrieval and the R wrapper were not run in this environment. Verification logs live under audit/delta. The cloud browser could not open the localhost QA server (ERR_BLOCKED_BY_CLIENT); that is not a passed visual browser test. Native macOS execution was not performed.

Quit the running OMEGA server, extract the new folder, and double-click Start_OMEGA.command, or run `zsh Start_OMEGA.command` from that folder. Open DELTA model. Existing OMEGA records use the same data path; first launch also saves a consistent pre-DELTA database copy. Run Verify_OMEGA.command to repeat software checks and sealed historical replays without replacing the active freezes.

The standalone OMEGA release was recovered from OMEGA_V2.zip because its app source is outside the inspected GitHub branch history. This new release has not been pushed to twonicecheeks/ModelRepo. The package contains the implementation, parameters, row-level results and complete documentation needed to review and preserve it.

Primary mathematical/context references checked October 6, 2026: [SciPy beta-binomial definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betabinom.html), [FanGraphs Stuff+/Location+/Pitching+ primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/), and [FanGraphs postseason strikeout composition analysis](https://blogs.fangraphs.com/why-do-the-playoffs-have-so-many-strikeouts/). These establish definitions and context; they do not validate DELTA's coefficients.

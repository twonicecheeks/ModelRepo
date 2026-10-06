# DELTA advanced inputs

The automatic 0.1 path uses the saved official order, public overall K rates, and V2's guarded postseason workload mean. Advanced inputs are optional research profiles. They do not constitute a fitted, validated replacement model merely because their fields are present.

Download the blank JSON template from DELTA model. Supply a `profiles` array. Each profile needs exact `game_id` (MLB gamePk), `player_id` (MLBAM pitcher), `source`, `observed_at`, and official `start_at`, with timezone-qualified timestamps. Import before first pitch. Source-reported timestamps and externally supplied coefficients are unverified; the app records local receipt independently.

The optional `tools/delta_sources.py prepare` command builds this profile from locally exported pybaseball/Baseball Savant pitch CSVs, including SHA-verified `--statcast-dir` batches. Separate normalized baseballr game events can be included. See DELTA_DATA_SOURCES.md. It does not generate a count model or feature/hook coefficients.

## Input units and structure

| Field | Contract |
|---|---|
| pitcher.hand | L or R |
| hitters | Object keyed by exact MLBAM hitter IDs; the forecast uses the actual starting nine |
| hitter.hand | L, R or S; a switch hitter bats opposite the pitcher's hand |
| pitcher.splits / hitter.splits | L/R objects containing K in percentage points (0–100) and pa as sample exposure. Pitcher splits refer to batter hand; hitter splits refer to pitcher hand. Reverse splits are retained. |
| pitcher.arsenal | Array of pitch_type and usage (fraction); usage must sum to one. Physical fields may include velocity (mph), vertical_break/horizontal_break (inches), release_height/extension (feet). Match units to the fitted model's documented training units. |
| hitter.pitch_types | Objects keyed by pitch_type with whiff_pct, chase_pct in percentage points and run_value_per100. Weighted matchup features require complete pitch-type coverage. |
| pitcher physical/discipline fields | stuff_plus, pitchingbot_stuff, location_plus, command_plus, csw_pct, whiff_pct, chase_pct, velocity, vertical_break, horizontal_break, release_height, extension |
| context | umpire_called_strike_residual, temperature_f, wind_mph, air_density, park_k_factor, familiarity_pa, series_game, elimination_game, bullpen_available, rest_days, velocity_change, postseason_environment; units/reference must match the supplied model |
| bf_pmf | Optional array of `{bf: integer, probability: fraction}`; nonnegative probabilities sum to one. It replaces the history workload distribution, permitting opener and manager-plan support. No second postseason multiplier is applied. |
| feature_model | source, training_end_at, intercept, coefficients, optional reference/scale objects. Effect is `intercept + sum(coef*(value-reference)/scale)` on log-odds. All required feature values must exist. A captured Stuff+ value alone receives no fabricated K coefficient. |

Overall rates are shrunk toward the declared .225 league prior with 180 pitcher BF and 120 hitter PA prior exposure. Actual splits shrink toward the player's overall estimate. The historical efficiency intercept is fitted on earlier postseasons only. This is an initial research specification, not a claim that those shrinkage amounts or league prior are optimal in every era.

Location/command and physical pitch quality remain distinct fields. Imported pitch-model probabilities must come from a sourced model or clearly declared scenario; DELTA does not synthesize Stuff+, PitchingBot, umpire labels, or observed weather.

## Pitch counts

Each `hitters[MLBAM_ID].count_probabilities` object supplies all 12 counts from `0-0` through `3-2`. Every cell has exactly five fields: `ball`, `called_strike`, `whiff`, `foul`, `in_play`, each a probability fraction. Cells must sum to one; the two-strike foul probability must permit termination.

The exact absorbing recursion starts at 0–0. Four balls end the PA without a strikeout. Three called/swinging strikes end it in a strikeout. A two-strike foul stays in the same state; a ball in play ends it without a strikeout. Rare events such as HBP, interference and dropped-third-strike advancement are not separately represented in this initial kernel. The Monte Carlo routine samples the same transitions and tracks pitches.

A count model replaces the log-5/efficiency adjustment for that hitter. A count model and physical feature adjustment cannot be stacked in one profile. This prevents blindly counting the same pitch-quality signal twice. Count probabilities may be derived upstream from an arsenal mixture, count-specific locations and hitter discipline; 0.1 does not train that upstream model from absent pitch histories.

## Dynamic hook scenarios

`hook_model` needs source, training_end_at, intercept, coefficients, max_bf and max_pitches. Coefficients can use bf, outs, pitch_count, tto (zero-based trip: 0,1,2...), baserunners, runs, leverage, bullpen_available and elimination_game. Hazard is evaluated after each PA on the logit scale. Every starting hitter must have a count model. A conditional `contact_outcomes` object needs OUT, 1B, 2B, 3B and HR probabilities summing to one. Leverage, bullpen availability and elimination context must exist if coefficients require them.

The dynamic simulation replaces the independent BF mixture. It does not add a second short-hook penalty on top of the learned workload distribution. It uses simplified deterministic base advancement, no runner movement on contact outs, and externally supplied leverage. It is a scenario tool, not a historically fitted manager or full-game simulator. Max pitch count is checked after the PA.

The exact PA distribution displayed on the board still uses the saved independent BF distribution; a dynamic hook run is a separately labelled simulation record. It does not silently replace the board or price-comparison forecast. Integrating a historically validated conditional-hook engine into the scored forecast remains a promotion step.

## Saved records and use

Import advanced profiles, then refresh Playoff board before first pitch. Each forecast records its parameter fingerprint and original profile snapshot. Importing new profiles does not rewrite old forecasts. Simulations read the profile and parameters stored with the selected snapshot, preserving reproducibility after later imports.

Quote prices and outcomes are separate. Target K line/odds do not set the DELTA distribution. Whole lines have three outcomes: win, loss and push. Price comparisons use the saved PA distribution; beta-binomial remains an explicitly available comparison.

Historical market lines are an external audit input, not a model feature. Use `examples/DELTA_MARKET_TEMPLATE.csv` and `tools/evaluate_delta_market.py`. The tool de-vigs opening/closing two-way prices, uses opening prices for a hypothetical edge/ROI rule, uses closing prices for probability benchmarking, and reports price-only CLV only when the line is unchanged. It refuses post-first-pitch captures, mismatched official strikeouts, duplicate joins and unsupported settlement definitions.

The missing advanced histories require acquisition and chronological fitting: pitch/count and arsenal matchups; actual platoon exposures; verified pregame manager plans and bullpen availability; event-level removal decisions with pitch count, score, baserunners and leverage; and timestamped umpire/weather/series context. No universal +1–2 mph, 1.03–1.05 October boost, fixed 60% hook increase or 18–21 BF ceiling is inserted in place of that evidence.

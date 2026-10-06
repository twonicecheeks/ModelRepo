# DELTA public pitch and play-by-play inputs

OMEGA now includes an **optional, operator-run** acquisition and normalization path. It does not poll sites, install packages, collect current markets, or change the frozen DELTA 0.1 model. Generated profiles can be imported through the existing **DELTA model → Import advanced JSON** control. No Statcast pitch archive was bundled with the original V2 historical cache, so the sealed 775-start comparison remains based on its original inputs.

## Source roles

| Source | Appropriate use | Current connector |
|---|---|---|
| [pybaseball `statcast_pitcher` and `statcast_batter`](https://github.com/jldbc/pybaseball/blob/master/docs/statcast_pitcher.md) / [Baseball Savant CSV](https://baseballsavant.mlb.com/csv-docs) | Measured pitch type, velocity, spin, movement, release traits, observed PA strikeouts and actual hand splits. The public export has one row per pitch and source `game_pk`/MLBAM IDs. | `tools/delta_sources.py export-players` fetches one confirmed starter and nine batters (regular-season games by default); broader `export-statcast` and your own Savant CSV remain supported. |
| [baseballr `mlb_pbp(game_pk)`](https://billpetti.github.io/baseballr/reference/mlb_pbp.html) | Per-game event order, pre-pitch count/outs, score, personnel and optional reconstructed pre-pitch base state. These are candidates for later hook/rolling-history fitting. | `tools/export_delta_pbp.R` exports CSVs; `prepare --pbp` writes separate normalized PBP events. |
| [Retrosheet CSV/event downloads](https://www.retrosheet.org/downloads/csvoverview.html) | Independent game/play outcomes and long-horizon backtest checks, with its required attribution when those data are used. | Research source; not yet connected to DELTA's pitch profile generator. |
| Lahman season tables | Player/season and identifier context, not a substitute for pitch sequences. | No automatic feed. Exact MLBAM IDs remain required; no name matching. |
| FanGraphs leaderboards/projections | A potential licensed/sourced baseline if obtained with permission and historical capture times. Proprietary projections are not reconstructed from the public pitch feed. | Existing OMEGA collector has its own public data adapter; this path does not scrape premium pages or import unlabeled projections. |

The research rows and profiles include source names and SHA-256 receipts. The converter uses **whole-game dates before first pitch, and excludes both the current and previous UTC date at local receipt**. A game dated yesterday may still have been running after midnight UTC; a date-only Statcast record cannot prove the final pitch was available at receipt. This conservative rule can omit some valid recent games. A source-reported timestamp can be supplied, but OMEGA also records its independent local import time.

## On your Mac

From the extracted OMEGA folder, use a separate Python environment in which optional `pybaseball` and its dependencies actually install (OMEGA itself needs neither `pip` nor R). For example, with a compatible `python3` on your Mac:

```sh
python3 -m venv "$HOME/Desktop/delta-data-env"
"$HOME/Desktop/delta-data-env/bin/python" -m pip install pybaseball
```

If installation is incompatible with your Python version, a manually saved Baseball Savant pitch CSV is a valid input to `prepare`. With a confirmed starting pitcher and nine official hitters, the focused query fetches each player once for a range of at most 32 complete prior days. Replace these example IDs; the default includes regular-season game type `R` only. It saves CSVs and a hashed manifest in a new folder:

```sh
"$HOME/Desktop/delta-data-env/bin/python" tools/delta_sources.py export-players \
  --start 2026-09-01 --end 2026-09-30 \
  --pitcher-id 123456 \
  --lineup 100001,100002,100003,100004,100005,100006,100007,100008,100009 \
  --out "$HOME/Desktop/delta-starter-lineup-sep2026"
```

Repeat month-sized batches into distinct folders to build a longer prior-history sample. `prepare --statcast-dir` verifies each manifest hash and removes duplicate pitches across the starter and batter exports. `--include-postseason` is an explicit option when earlier postseason games are part of a documented training window. `export-statcast --start YYYY-MM-DD --end YYYY-MM-DD --out NEW_FOLDER` is available for broader three-day-window exports, or save a CSV from Savant's public pitch search. Do not use an aggregated leaderboard CSV as pitch rows. For optional game logs, after installing `baseballr` in R, export completed MLB `game_pk` values:

```sh
Rscript tools/export_delta_pbp.R "$HOME/Desktop/delta-pbp-games" 123456 123457
```

Replace the example IDs below with an **upcoming** MLB gamePk, its confirmed starting-pitcher MLBAM ID, the same official nine MLBAM lineup IDs in order, and the official timezone-qualified first-pitch timestamp. Repeat `--statcast-dir` for more verified batches, `--statcast` for individual CSVs, or `--pbp` for more local baseballr files.

```sh
python3 tools/delta_sources.py prepare \
  --statcast-dir "$HOME/Desktop/delta-starter-lineup-sep2026" \
  --pbp "$HOME/Desktop/delta-pbp-games/pbp_123456.csv" \
  --game-id 999999 --pitcher-id 123456 \
  --lineup 100001,100002,100003,100004,100005,100006,100007,100008,100009 \
  --start-at '2026-10-09T20:00:00-04:00' \
  --out "$HOME/Desktop/delta-prep-next-game"
```

Import `DELTA_PROFILE.json` from the new output directory in OMEGA, then refresh **Playoff board** before first pitch. The saved forecast records the source profile. The folder also includes `COVERAGE.json`, `PITCH_EVENTS.jsonl`, and `PBP_EVENTS.jsonl`. The JSONL files retain explicit missing values and unrecognized pitch descriptions for audit and future chronological model fitting. They are **research rows**, not trained model parameters. If a source date has no earlier pitcher history, inconsistent duplicates, or invalid identities, the converter fails without publishing an output folder.

This workflow produces one saved pregame probability distribution using the final order; it does not require a live pitch stream. The `pitcher_stats(2026)` spelling in the proposed snippet is not an exported pybaseball function; its documented player-season function is `pitching_stats(2026)`. `batting_stats_bref(2026)` returns individual batter season stats rather than a confirmed lineup, and its date range extends into November. For DELTA's cutoff-safe baseline, the pitch CSVs and official MLBAM lineup identities have a clearer audit trail than a season-to-date aggregate retrieved after the game.

## Optional DELTA 0.1.3 research inputs

`prepare` accepts `--research-priors PATH` and `--starter-games PATH`. The prior
JSON must contain an explicit `source`, a timezone-qualified `training_end_at`
before the profile receipt, `league_k`, hand-specific league rates, player
overall K rates, prior exposures, and pitch-type league whiff priors. The
result is written to `RESEARCH_MATCHUPS.json` with the prior file hash and is
labeled unfitted. The starter-game JSON must contain `source`,
`observed_at`, and confirmed regular-season `game_pks`; without it the final-two
start velocity report remains `MISSING_CONFIRMED_START_IDENTITIES`.

For the workload trainer and residual contract, use the schemas and cutoff
rules in `DELTA_RESEARCH_0.1.3.md`. The normalized `PBP_EVENTS.jsonl` rows are
candidate data for those tables; they are not silently treated as a removal
label, because the decision-time score, pitch count, leverage and manager
availability must be reconstructed first.

## What these measurements actually do

The profile supplies observed pitcher/batter splits, pitcher arsenal usage and physical traits, simple measured CSW/whiff/chase rates, and hitter pitch-type whiff/chase rates when denominators are at least 20. `pfx_x` and `pfx_z` are converted from Savant feet to DELTA inches; release extension stays in feet. Split sample sizes travel with their K percentages, so DELTA shrinks them rather than treating a tiny sample as a certain rate. Batter hand is inferred only after observing both pitcher hands: opposite batting sides imply switch-hitting, a consistent side implies L or R. One-sided histories leave batter hand missing. Missing pitch measurements remain missing.

The default forecast **can use the measured splits**. Arsenal, physical and discipline fields only affect the result when a separately fitted, timestamped `feature_model` is supplied. The converter does not invent Stuff+, PitchingBot, count-transition probabilities, pitch-type run values, or manager-hook coefficients. The separate baseballr events are not yet fitted into a conditional removal hazard. Published DELTA accuracy numbers do not include these new inputs. A responsible next experiment would fit on earlier games/seasons, score held-out postseason starts against the existing V2 reference, inspect calibration/coverage, and only then consider promotion.

## Source and version cautions

Savant's `events` field labels a completed plate appearance, while `description` labels an individual pitch. The converter keeps unrecognized pitch descriptions out of categorical event inference and reports them in `COVERAGE.json`. Bunts, automatic calls, HBP and other uncommon states are not forced into the five-event DELTA count kernel. Location and tracking definitions change over time, including the 2026 ABS plate-coordinate definition; season-aware fitting is necessary before treating those columns as uniform.

This tool does not bypass access controls or reproduce paid/proprietary projections. Follow the source's published conditions for any data you acquire and redistribute. Retrosheet requires prominent credit in work based on its downloads; this release contains no Retrosheet data.

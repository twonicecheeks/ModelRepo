# DELTA 0.1.3 research contracts

This release adds the requested research paths while keeping the scored DELTA
0.1.0 engine and its frozen 775-start result unchanged. The new paths require
timestamped historical inputs and fitted coefficients. They are opt-in reports
or scenario calculations until their season-wise out-of-sample scores pass the
same gates as the existing model.

## 1. Conditional workload and hook hazard

`tools/train_delta_research.py --task hook` fits a ridge-penalized logistic
end-of-PA removal hazard from a complete person-period table. The required
columns are:

```text
season,game_pk,game_start_at,state_at,pa_index,censored,target,bf,pitch_count,runs_allowed,strikeouts,leverage
```

Each game must have sequential PA rows. `state_at` is after that PA, and the
state variables cannot decrease. `target=1` identifies the observed removal;
the final row may instead be `censored=1` when removal was not observed. The
trainer accepts only 2016–2025 targets and rejects a 2026 row. Runs must be
visible at the decision time; official earned-run assignment made later is not
an eligible feature.

`app.delta_research.conditional_k_matrix()` then performs a forward recursion
over supplied PA outcome kernels. Every kernel row contains `probability`,
`k`, `pitches`, `runs_allowed`, and `leverage_after`. The hook model is called
after each PA, so a high pitch count or an adverse run state can shorten the
workload distribution. The recursion has a bounded state guard and reports the
mass that reaches its explicit support boundary. It does not silently replace
the model's workload with a fixed 19-BF cap.

The engine is still a scenario contract because the package has no bundled
event-level removal histories or fitted coefficients for this layer.

## 2. Hierarchical platoon shrinkage

`app.delta_research.platoon_posterior()` returns a posterior K rate and
uncertainty for a player/hand cell. It uses the player's overall rate as the
center and applies the league hand effect as an **odds shift**:

```text
logit(prior_hand_rate) = logit(player_overall_rate)
                         + logit(league_hand_rate)
                         - logit(league_overall_rate)
```

The proposed percentage-times-percentage formula has incompatible units and is
not used. A missing cell is labeled `ESTIMATED_LEAGUE_HAND_PRIOR`; an observed
cell is labeled `SHRUNK_OBSERVED` and carries its posterior standard deviation.
No estimate is presented as a measured player split. The optional
`research_matchups()` report requires an earlier-vintage source and a known
batter/pitcher hand; it does not alter the scored DELTA PMF.

## 3. Feature-model contract and final-two-start measurement

`tools/train_delta_research.py --task residual` fits a ridge-logit residual
around a supplied pre-feature `baseline_logit`. Required residual columns are:

```text
season,game_pk,game_start_at,state_at,pa_index,censored,target,baseline_logit,feature_observed_at,<feature names>
```

`feature_observed_at` must precede first pitch. Feature names are restricted to
the frozen contract in `app.delta_model.FEATURES`; the output is labeled
`UNVALIDATED_RESEARCH_NO_PROMOTION` and is never auto-imported. This removes
the fixed 1.04 escalator from the research path. The residual trainer can use
physical changes, but it cannot turn a velocity change into a K coefficient
without prior-year fitting and held-out scoring.

`four_seam_trend()` compares the final two **confirmed regular-season starts**
with earlier qualified starts. It reports the measured velocity change and
requires a sourced list of confirmed starter `game_pk` values. It does not
assume that the final two pitcher appearances were starts and does not convert
1.5 mph into Stuff+ automatically.

## 4. Arsenal-to-lineup descriptive matrix

`arsenal_whiff()` weights the pitcher's measured usage by the hitter's
pitch-type whiffs per swing. Each pitch type carries observed swings and
whiffs, a sourced league prior, and a posterior estimate. Missing hitter pitch
types remain an explicitly labeled league-prior estimate. The result is
`DESCRIPTIVE_UNFITTED`; pitch usage and whiff differences do not enter DELTA's
forecast until a historical residual contract is fitted.

## 5. Future-only holdout

Run:

```sh
python3 tools/delta_prospective.py freeze \
  --out audit/delta/PROSPECTIVE_2026_FREEZE.json
python3 tools/delta_prospective.py audit \
  --freeze audit/delta/PROSPECTIVE_2026_FREEZE.json \
  --db "$HOME/Library/Application Support/OMEGA Next/omega.sqlite3" \
  --out audit/delta/PROSPECTIVE_2026_AUDIT_0.1.3.json
```

The freeze is immutable. The audit reads the SQLite snapshots read-only and
keeps only complete DELTA forecasts whose local receipt and capture occurred
after the freeze and before first pitch in a 2026 game. It chooses the latest
locally received eligible forecast once per game and pitcher, and joins an
official final when OMEGA has recorded one. No 2026 outcome can be used to
refit the alpha/beta grid, workload intercept, hook coefficients, or feature
residuals. Missing prices and unauthenticated quotes remain unscored for ROI
and CLV.

## Promotion gate

For each new layer, compare against the frozen V2/DELTA reference by season and
series. Require a pregame timestamp audit, distribution log loss/RPS, mean error,
calibration, and enough independent games before considering promotion. A
closing market line can benchmark a saved forecast, but it is not a substitute
for the pregame forecast receipt or evidence that a wager was executable.

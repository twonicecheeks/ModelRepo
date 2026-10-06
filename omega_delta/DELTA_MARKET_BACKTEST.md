# DELTA market benchmarking

`tools/evaluate_delta_market.py` is an offline audit layer for matching a
historical strikeout market file to the exact DELTA distributions in
`audit/delta/PREDICTIONS.jsonl`. It does not refit DELTA, read a current line,
or call a sportsbook or odds provider.

## What it measures

The tool uses the opening quote for a hypothetical decision and realized return
per unit. It uses the closing quote for the model-versus-market probability
benchmark. Two-way prices are de-vigged before probability comparisons. The
model expected return still uses the quoted price and retains the model's push
probability.

Whole-number K lines have three outcomes. A push is excluded from binary Brier
and log-loss comparisons and is settled at zero return. Half-lines have no
push. A price-only CLV value is reported only when the opening and closing
lines are identical; a line move is labeled `LINE_MOVED_UNSCORABLE` rather
than converted using an invented run-to-probability rule.

## Historical CSV contract

Start with `examples/DELTA_MARKET_TEMPLATE.csv`. Each matched row needs:

```text
game_id,player_id,market_type,book,line,opening_line,opening_over_odds,opening_under_odds,closing_line,closing_over_odds,closing_under_odds,game_start_at,captured_at,closing_captured_at,actual_k,source,settlement_definition
```

`game_id` and `player_id` must match the DELTA prediction artifact. `game_start_at`
and each supplied capture timestamp require an explicit timezone, and market
captures must precede first pitch. Use `FULL_GAME` for `settlement_definition`.
`actual_k` may be omitted when it agrees with the sealed prediction artifact;
including it makes the join auditable. Both opening prices must be supplied
together or omitted together. Closing prices are required.

The bundled prediction file contains exact `baseline`, `v2`, `delta_pa`, and
`delta_beta` PMFs. It is a reconstructed 2016–2025 development artifact, so a
market result from it cannot be described as a prospective pregame ledger.

## Run an audit

```sh
python3 tools/evaluate_delta_market.py \
  --market-csv "$HOME/Desktop/delta-market-lines.csv" \
  --variant delta_pa \
  --edge-threshold 0.05 \
  --out audit/delta/MARKET_AUDIT_0.1.3.json
```

The report includes matched and push counts, model and de-vigged market Brier
score/log loss, hypothetical opening-price ROI, expected ROI, and same-line
CLV. `--variant v2` or `--variant delta_beta` can be run separately against
the same matched lines.

## Interpretation rules

An edge threshold is a selection rule, not evidence that the model is correct.
Closing prices are a benchmark and cannot be reused as the price at which a
historical wager was placed. ROI is hypothetical unless a contemporaneous
pregame receipt proves that a bet was executable. Aggregate results should be
reviewed by season, series, book, and line availability; the command does not
promote a variant automatically.

For a genuine 2026 prospective test, save the DELTA forecast and the captured
opening quote before first pitch, preserve the local receipt timestamp, and
append the final official strikeout result later. The separate prospective
freeze in `audit/delta/PROSPECTIVE_2026_FREEZE.json` remains the eligibility
boundary.

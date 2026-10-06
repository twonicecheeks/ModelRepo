# OMEGA DELTA 0.1.3 in ModelRepo

The complete OMEGA/DELTA release now lives in the repository under
`omega_delta/`. It is a self-contained runnable package rather than a partial
copy of selected source files. This preserves the release's app, interface,
tests, frozen parameters, normalized replay inputs, audit reports, source
connectors, attribution notes and public-source cache together.

## Run it on macOS

```sh
cd omega_delta
zsh Start_OMEGA.command
```

Python 3.10 or newer and Node 18 or newer are required. The package does not
install dependencies automatically. `Verify_OMEGA.command` runs the backend,
UI, V2 replay and DELTA replay checks.

## Important paths

| Path | Purpose |
|---|---|
| `omega_delta/app/delta_model.py` | Frozen DELTA 0.1.0 scored engine |
| `omega_delta/app/delta_research.py` | Conditional workload, platoon and arsenal research calculations |
| `omega_delta/tools/train_delta_research.py` | Historical hook/residual fitting contracts |
| `omega_delta/tools/delta_prospective.py` | Immutable 2026 future-only freeze and audit |
| `omega_delta/tools/evaluate_delta_market.py` | Historical market-line ROI, probability scores and CLV audit |
| `omega_delta/audit/delta/` | Frozen parameters, predictions, results and verification logs |
| `omega_delta/seed/mlb/` | Normalized historical MLB replay inputs and outcomes |
| `omega_delta/research_sources/` | Public-source adapters, scripts, documentation and offline cache |
| `omega_delta/web/` | OMEGA interface |

The 775-start development comparison remains unchanged: V2 has K MAE 2.0048,
DELTA PA has 2.0560, and DELTA beta-binomial has 2.0560. The new research
layers are stored and testable but have not been promoted into the frozen
forecast.

## Market-line audit

Fill `omega_delta/examples/DELTA_MARKET_TEMPLATE.csv` with matched historical
opening and closing prices, then run:

```sh
python3 tools/evaluate_delta_market.py \
  --market-csv "$HOME/Desktop/delta-market-lines.csv" \
  --variant delta_pa \
  --edge-threshold 0.05 \
  --out audit/delta/MARKET_AUDIT_0.1.3.json
```

This layer uses closing prices for benchmarking and opening prices for a
hypothetical execution audit. It handles pushes and leaves line moves
unscored for price-only CLV. It does not refit or automatically promote DELTA.

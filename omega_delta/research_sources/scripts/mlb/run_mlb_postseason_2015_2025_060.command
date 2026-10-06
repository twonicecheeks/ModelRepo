#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

echo "== MLB 2015-2025 postseason study regressions =="
python3 tests/mlb/test_mlb_historical_validation_010.py
node tests/mlb/test_mlb_production_replay_adapter_020.js
python3 tests/mlb/test_mlb_historical_outcomes_030.py
python3 tests/mlb/test_mlb_postseason_priors_040.py
node tests/mlb/test_mlb_postseason_replay_050.js

echo
echo "== Acquire 2015-2025 postseason outcomes =="
zsh scripts/mlb/acquire_mlb_postseason_outcomes_030.command 2015-2025

echo
echo "== Replay 2015-2025 postseason history proxy =="
zsh scripts/mlb/run_mlb_postseason_replay_050.command

echo
echo "PASS MLB 2015-2025 postseason study 0.6.0"


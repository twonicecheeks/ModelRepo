#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

echo "== MLB postseason replay regression =="
python3 tests/mlb/test_mlb_historical_validation_010.py
node tests/mlb/test_mlb_production_replay_adapter_020.js
python3 tests/mlb/test_mlb_historical_outcomes_030.py
python3 tests/mlb/test_mlb_postseason_priors_040.py
node tests/mlb/test_mlb_postseason_replay_050.js

echo
echo "== Acquire leakage-safe postseason priors =="
zsh scripts/mlb/acquire_mlb_postseason_priors_040.command

echo
echo "== Build postseason history-proxy replay =="
node scripts/mlb/build_mlb_postseason_replay_050.js --root "$ROOT"

REPLAY_DIR="$(cat "$ROOT/data/models/mlb/CURRENT_POSTSEASON_REPLAY_050")"
LEDGER="$ROOT/$REPLAY_DIR/MLB_POSTSEASON_HISTORY_PROXY_LEDGER.jsonl"

echo
echo "== Audit replay ledger =="
python3 scripts/mlb/audit_mlb_historical_validation_010.py \
  "$LEDGER" \
  --root "$ROOT" \
  --label "POST_HISTORY_PROXY"

echo
echo "PASS MLB postseason history-proxy pipeline 0.5.1"
echo "Replay ledger: $LEDGER"

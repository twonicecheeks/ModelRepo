#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "usage: zsh scripts/mlb/run_mlb_historical_backtest_020.command <pregame_snapshots.jsonl> [label]"
  exit 2
fi

INPUT="$1"
LABEL="${2:-historical-replay}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)_$$"
OUT_DIR="$ROOT/data/models/mlb/historical_runs/$RUN_ID"
LEDGER="$OUT_DIR/MLB_PRODUCTION_REPLAY_LEDGER.jsonl"
mkdir -p "$OUT_DIR"

echo "== MLB historical validation regression =="
python3 tests/mlb/test_mlb_historical_validation_010.py
node tests/mlb/test_mlb_production_replay_adapter_020.js

echo
echo "== Exact production replay =="
node scripts/mlb/replay_mlb_historical_inputs_020.js \
  --root "$ROOT" \
  --input "$INPUT" \
  --output "$LEDGER"

echo
echo "== Historical audit =="
python3 scripts/mlb/audit_mlb_historical_validation_010.py \
  "$LEDGER" \
  --root "$ROOT" \
  --label "$LABEL"

echo
echo "PASS MLB historical backtest 0.2.0"
echo "Replay ledger: $LEDGER"

#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "usage: zsh scripts/mlb/audit_mlb_historical_validation_010.command <ledger.jsonl> [label]"
  exit 2
fi

LEDGER="$1"
LABEL="${2:-}"

python3 tests/mlb/test_mlb_historical_validation_010.py
exec python3 scripts/mlb/audit_mlb_historical_validation_010.py "$LEDGER" --root "$ROOT" --label "$LABEL"


#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

SEASONS="${1:-2015-2025}"

python3 tests/mlb/test_mlb_historical_outcomes_030.py
exec python3 scripts/mlb/acquire_mlb_historical_outcomes_030.py \
  --root "$ROOT" \
  --seasons "$SEASONS" \
  --scope postseason \
  --workers "${MODEL_MLB_OUTCOME_WORKERS:-4}"


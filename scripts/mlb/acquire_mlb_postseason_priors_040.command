#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

python3 tests/mlb/test_mlb_postseason_priors_040.py

exec python3 scripts/mlb/acquire_mlb_postseason_priors_040.py \
  --root "$ROOT" \
  --workers "${MODEL_MLB_PRIOR_WORKERS:-4}"

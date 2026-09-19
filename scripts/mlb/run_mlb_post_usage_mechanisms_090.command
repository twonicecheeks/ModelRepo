#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

echo "== MLB POST_USAGE mechanism bakeoff regression =="
python3 tests/mlb/test_mlb_post_usage_mechanisms_090.py

echo
echo "== Evaluate postseason usage mechanisms =="
python3 scripts/mlb/evaluate_mlb_post_usage_mechanisms_090.py --root "$ROOT"

echo
echo "PASS MLB POST_USAGE mechanism bakeoff 0.9.0"

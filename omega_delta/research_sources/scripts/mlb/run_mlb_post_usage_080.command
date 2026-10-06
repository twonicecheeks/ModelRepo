#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

echo "== MLB POST_USAGE OOS challenger regression =="
python3 tests/mlb/test_mlb_post_usage_080.py

echo
echo "== Evaluate chronological postseason usage challenger =="
python3 scripts/mlb/evaluate_mlb_post_usage_080.py --root "$ROOT"

echo
echo "PASS MLB POST_USAGE OOS challenger 0.8.0"


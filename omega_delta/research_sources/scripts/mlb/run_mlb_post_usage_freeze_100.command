#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

echo "== MLB POST_USAGE 2026 freeze regression =="
python3 tests/mlb/test_mlb_post_usage_freeze_100.py

echo
echo "== Explicitly freeze POST_USAGE_OUTS for 2026 prospective validation =="
python3 scripts/mlb/freeze_mlb_post_usage_100.py \
  --root "$ROOT" \
  --confirm POST_USAGE_OUTS_2026_FREEZE

echo
echo "PASS MLB POST_USAGE 2026 freeze 1.0.0"


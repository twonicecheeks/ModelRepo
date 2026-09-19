#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

echo "== MLB REG-vs-POST K control regressions =="
python3 tests/mlb/test_mlb_historical_validation_010.py
node tests/mlb/test_mlb_production_replay_adapter_020.js
python3 tests/mlb/test_mlb_historical_outcomes_030.py
python3 tests/mlb/test_mlb_postseason_priors_040.py
node tests/mlb/test_mlb_postseason_replay_050.js
python3 tests/mlb/test_mlb_regular_control_070.py
node tests/mlb/test_mlb_regular_k_control_071.js

echo
echo "== Refresh postseason replay with latest historical reconciliation =="
zsh scripts/mlb/run_mlb_postseason_replay_050.command

echo
echo "== Acquire late-regular-season control cohort =="
python3 scripts/mlb/acquire_mlb_regular_control_070.py \
  --root "$ROOT" \
  --window-days "${MODEL_MLB_CONTROL_WINDOW_DAYS:-7}" \
  --workers "${MODEL_MLB_CONTROL_WORKERS:-4}"

echo
echo "== Build late-regular-season K xK control =="
node scripts/mlb/build_mlb_regular_k_control_071.js --root "$ROOT"

REG_DIR="$(cat "$ROOT/data/models/mlb/CURRENT_REGULAR_CONTROL_K_071")"
REG_LEDGER="$ROOT/$REG_DIR/MLB_REGULAR_CONTROL_K_LEDGER.jsonl"

echo
echo "== Audit regular-season K control =="
python3 scripts/mlb/audit_mlb_historical_validation_010.py \
  "$REG_LEDGER" \
  --root "$ROOT" \
  --label "REG_LATE_HISTORY_PROXY"

echo
echo "== Assemble REG-vs-POST K ledger =="
python3 scripts/mlb/assemble_mlb_reg_post_k_072.py --root "$ROOT"

COMBINED_DIR="$(cat "$ROOT/data/models/mlb/CURRENT_REG_POST_K_072")"
COMBINED_LEDGER="$ROOT/$COMBINED_DIR/MLB_REG_POST_K_XK_LEDGER.jsonl"

echo
echo "== Audit REG-vs-POST K regime =="
python3 scripts/mlb/audit_mlb_historical_validation_010.py \
  "$COMBINED_LEDGER" \
  --root "$ROOT" \
  --label "REG_VS_POST_K_2026_RESEARCH"

echo
echo "PASS MLB REG-vs-POST K control study 0.7.4"
echo "Regular ledger: $REG_LEDGER"
echo "Combined ledger: $COMBINED_LEDGER"

#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
python3 tests/nfl/test_nfl_state_mechanism_research_011.py
exec python3 scripts/nfl/analyze_nfl_early_down_mechanism_011.py \
  --root "$ROOT" \
  --seasons "${MODEL_NFL_M04_DEVELOPMENT_SEASONS:-2016-2024}" \
  --bootstrap-reps "${MODEL_NFL_M04_BOOTSTRAP_REPS:-1000}"

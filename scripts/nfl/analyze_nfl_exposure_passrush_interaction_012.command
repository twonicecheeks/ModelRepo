#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
python3 tests/nfl/test_nfl_state_exposure_interaction_012.py
exec python3 scripts/nfl/analyze_nfl_exposure_passrush_interaction_012.py \
  --root "$ROOT" \
  --seasons "${MODEL_NFL_M05_DEVELOPMENT_SEASONS:-2016-2024}" \
  --min-prior-dropbacks "${MODEL_NFL_M05_MIN_PRIOR_DROPBACKS:-20}" \
  --bootstrap-reps "${MODEL_NFL_M05_BOOTSTRAP_REPS:-1000}"

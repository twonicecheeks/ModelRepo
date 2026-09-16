#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
python3 tests/nfl/test_nfl_state_component_persistence_013.py
exec python3 scripts/nfl/analyze_nfl_state_component_persistence_013.py \
  --root "$ROOT" \
  --seasons "${MODEL_NFL_STATE_PERSISTENCE_SEASONS:-2016-2024}" \
  --min-prior-third-downs "${MODEL_NFL_STATE_PERSISTENCE_MIN_PRIOR_THIRD_DOWNS:-20}" \
  --min-prior-exposed-dropbacks "${MODEL_NFL_STATE_PERSISTENCE_MIN_PRIOR_EXPOSED_DROPBACKS:-20}" \
  --bootstrap-reps "${MODEL_NFL_STATE_PERSISTENCE_BOOTSTRAP_REPS:-1000}"

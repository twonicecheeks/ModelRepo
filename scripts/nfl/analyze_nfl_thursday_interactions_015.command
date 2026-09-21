#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
python3 tests/nfl/test_nfl_thursday_interaction_research_015.py
exec python3 scripts/nfl/analyze_nfl_thursday_interactions_015.py   --root "$ROOT"   --seasons "${MODEL_NFL_THURSDAY_INTERACTION_SEASONS:-2016-2024}"

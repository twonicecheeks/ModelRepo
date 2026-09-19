#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
cd "$ROOT"
if [[ ! -x "$PY" ]]; then
  zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
fi
"$PY" tests/nfl/test_omega_position_specific_challenger_0360.py
exec "$PY" scripts/nfl/analyze_omega_position_specific_challenger_0360.py   --root "$ROOT"   --evaluation-seasons "${MODEL_OMEGA_POSITION_EVAL_SEASONS:-2021,2022,2023,2024}"   --bootstrap-reps "${MODEL_OMEGA_POSITION_BOOTSTRAP_REPS:-1000}"

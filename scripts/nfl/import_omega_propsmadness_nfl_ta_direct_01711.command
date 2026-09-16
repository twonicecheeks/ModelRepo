#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
cd "$ROOT"
if [[ ! -x "$PY" ]]; then
  zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command"
fi
"$PY" "$ROOT/scripts/nfl/check_phase1b_dependencies.py"
"$PY" -m py_compile \
  "$ROOT/scripts/nfl/import_omega_propsmadness_nfl_ta_direct_01711.py" \
  "$ROOT/scripts/nfl/compare_omega_week2_dual_track_market_0341.py"
"$PY" "$ROOT/scripts/nfl/import_omega_propsmadness_nfl_ta_direct_01711.py"

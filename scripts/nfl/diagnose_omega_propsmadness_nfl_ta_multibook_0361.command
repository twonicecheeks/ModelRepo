#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
cd "$ROOT"
if [[ ! -x "$PY" ]]; then
  zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command"
fi
"$PY" "$ROOT/scripts/nfl/check_phase1b_dependencies.py"
"$PY" "$ROOT/scripts/nfl/diagnose_omega_propsmadness_nfl_ta_multibook_0361.py"

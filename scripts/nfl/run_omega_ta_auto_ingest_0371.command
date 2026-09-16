#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
cd "$ROOT"
if [[ ! -x "$PY" ]]; then
  zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command"
fi
"$PY" "$ROOT/scripts/nfl/check_phase1b_dependencies.py" >/dev/null
"$PY" "$ROOT/scripts/nfl/process_omega_ta_auto_capture_0371.py"

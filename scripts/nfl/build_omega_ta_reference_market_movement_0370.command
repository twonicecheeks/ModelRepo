#!/bin/zsh
set -euo pipefail

ROOT="/Users/abbeyfelix/Developer/MODEL"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
SCRIPT="$ROOT/scripts/nfl/build_omega_ta_reference_market_movement_0370.py"

cd "$ROOT"

if [[ ! -x "$PY" ]]; then
  zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command"
fi

[[ -x "$PY" ]] || { echo "FAIL missing phase1b python after bootstrap: $PY"; exit 1; }
[[ -f "$SCRIPT" ]] || { echo "FAIL missing OMEGA 0.37 script: $SCRIPT"; exit 1; }

"$PY" "$ROOT/scripts/nfl/check_phase1b_dependencies.py"
"$PY" -m py_compile "$SCRIPT"
"$PY" "$SCRIPT" --root "$ROOT"

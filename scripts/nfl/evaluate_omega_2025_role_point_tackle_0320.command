#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
SCRIPT="$ROOT/scripts/nfl/evaluate_omega_2025_role_point_tackle_0320.py"

cd "$ROOT"
if [[ ! -x "$PY" ]]; then
  zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command"
fi
"$PY" "$ROOT/scripts/nfl/check_phase1b_dependencies.py"

echo
echo "===== OMEGA 0.32 FIXED ROLE-POINT -> T+A DIAGNOSTIC ====="
"$PY" "$SCRIPT" --root "$ROOT"

#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
BOOTSTRAP="$ROOT/scripts/nfl/bootstrap_phase1_python.command"
CHECK="$ROOT/scripts/nfl/check_phase1b_dependencies.py"

cd "$ROOT"

# Parquet inspection requires the project's pinned pyarrow environment. Never
# install research dependencies into the user's global/system Python.
if [[ ! -x "$VENV/bin/python" ]] || ! "$VENV/bin/python" "$CHECK" --quiet; then
  echo "OMEGA 0.26 — preparing isolated NFL Python environment..."
  zsh "$BOOTSTRAP" >/dev/null
fi

"$VENV/bin/python" "$CHECK"
"$VENV/bin/python" scripts/nfl/inspect_omega_depth_chart_history_0260.py "$@"

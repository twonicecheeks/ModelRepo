#!/bin/zsh
set -euo pipefail
CODE_ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL-NFL-039}"
DATA_ROOT="${MODEL_DATA_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
PY="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}/bin/python"
[[ -x "$PY" ]] || { zsh "$DATA_ROOT/scripts/nfl/bootstrap_phase1_python.command" >/dev/null; }
[[ -x "$PY" ]] || { echo "FAIL pinned NFL Python missing: $PY" >&2; exit 1; }
exec env MODEL_DATA_ROOT_OVERRIDE="$DATA_ROOT" "$PY" "$CODE_ROOT/scripts/nfl/build_nfl_qb_week2_verified_starters_0243.py"

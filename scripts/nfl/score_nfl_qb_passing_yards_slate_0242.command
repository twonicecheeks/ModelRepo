#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="${0:A:h}"
CODE_ROOT="${MODEL_ROOT_OVERRIDE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
DATA_ROOT="${MODEL_DATA_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
[[ -x "$PY" ]] || { zsh "$DATA_ROOT/scripts/nfl/bootstrap_phase2c_python.command" >/dev/null; }
[[ -x "$PY" ]] || { echo "FAIL Phase1B/Phase2C Python env missing" >&2; exit 1; }
"$PY" "$CODE_ROOT/tests/nfl/test_nfl_qb_passing_yards_slate_0242.py"
exec "$PY" "$CODE_ROOT/scripts/nfl/score_nfl_qb_passing_yards_slate_0242.py" \
  --code-root "$CODE_ROOT" \
  --data-root "$DATA_ROOT" \
  --python "$PY" \
  "$@"

#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="${0:A:h}"
CODE_ROOT="${MODEL_ROOT_OVERRIDE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
DATA_ROOT="${MODEL_DATA_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
[[ -x "$PY" ]] || { zsh "$DATA_ROOT/scripts/nfl/bootstrap_phase1_python.command" >/dev/null; }
[[ -x "$PY" ]] || { echo "FAIL pinned NFL Python unavailable: $PY" >&2; exit 1; }
"$PY" "$CODE_ROOT/tests/nfl/test_nfl_qb_passing_yards_market_025.py"
"$PY" "$CODE_ROOT/tests/nfl/test_nfl_qb_passing_yards_board_026.py"
exec "$PY" "$CODE_ROOT/scripts/nfl/evaluate_nfl_qb_passing_yards_market_slate_0261.py"   --code-root "$CODE_ROOT"   --data-root "$DATA_ROOT"   "$@"

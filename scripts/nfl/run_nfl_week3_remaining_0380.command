#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="${0:A:h}"
CODE_ROOT="${MODEL_ROOT_OVERRIDE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
DATA_ROOT="${MODEL_DATA_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
[[ -x "$PY" ]] || { echo "FAIL pinned NFL Python missing: $PY" >&2; exit 1; }
mkdir -p "$DATA_ROOT/logs/nfl"
LOG="$DATA_ROOT/logs/nfl/week3_remaining_$(date -u +%Y%m%dT%H%M%SZ).log"
"$PY" -u "$CODE_ROOT/scripts/nfl/run_nfl_week3_remaining_0380.py" \
  --code-root "$CODE_ROOT" --data-root "$DATA_ROOT" "$@" 2>&1 | tee "$LOG"
echo "LOG: $LOG"

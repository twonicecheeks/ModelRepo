#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"

if [[ ! -x "$VENV/bin/python" ]]; then
  zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command"
fi

exec "$VENV/bin/python" "$ROOT/scripts/nfl/build_nfl_state_intelligence_010.py" --root "$ROOT" "$@"

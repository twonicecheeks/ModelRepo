#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || { echo "FAIL isolated NFL Python missing"; exit 1; }
exec "$PY" "$ROOT/scripts/nfl/build_phase2f_blind_2025.py" --root "$ROOT"

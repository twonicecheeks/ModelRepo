#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
zsh scripts/nfl/bootstrap_phase2c_python.command >/dev/null
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || { echo "FAIL Phase1B Python env missing"; exit 1; }
exec "$PY" scripts/nfl/build_phase2c_model.py --root "$ROOT"

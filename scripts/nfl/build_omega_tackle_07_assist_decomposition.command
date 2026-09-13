#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || PY=python3
cd "$ROOT"
exec "$PY" scripts/nfl/build_omega_tackle_07_assist_decomposition.py --root "$ROOT"

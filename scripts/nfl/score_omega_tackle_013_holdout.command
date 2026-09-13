#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || PY=python3
cd "$ROOT"
exec "$PY" scripts/nfl/score_omega_tackle_013_holdout.py --root "$ROOT"

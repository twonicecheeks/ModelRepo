#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
zsh scripts/nfl/bootstrap_phase2c_python.command >/dev/null
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || { echo "FAIL Phase1B/Phase2C Python env missing"; exit 1; }
"$PY" tests/nfl/test_nfl_qb_passing_yards_shadow_ledger_027.py
exec "$PY" scripts/nfl/capture_nfl_qb_passing_yards_shadow_027.py --root "$ROOT" "$@"

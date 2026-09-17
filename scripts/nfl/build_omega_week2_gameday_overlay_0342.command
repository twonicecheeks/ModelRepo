#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || { echo "FAIL pinned NFL Python unavailable: $PY" >&2; exit 1; }
"$PY" tests/nfl/test_omega_week2_gameday_overlay_0342.py
exec "$PY" scripts/nfl/build_omega_week2_gameday_overlay_0342.py --root "$ROOT" "$@"

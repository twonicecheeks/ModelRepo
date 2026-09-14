#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
cd "$ROOT"

if [[ ! -x "$VENV/bin/python" ]] || ! "$VENV/bin/python" scripts/nfl/check_phase1b_dependencies.py --quiet; then
  zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
fi

"$VENV/bin/python" -m py_compile \
  packages/models/nfl/omega/current_role_snap_distribution_challenger.py \
  scripts/nfl/build_omega_tackle_027_current_role_snap_distribution.py \
  tests/models/nfl/omega/test_current_role_snap_distribution_challenger.py

"$VENV/bin/python" tests/models/nfl/omega/test_current_role_snap_distribution_challenger.py
"$VENV/bin/python" scripts/nfl/build_omega_tackle_027_current_role_snap_distribution.py --root "$ROOT"

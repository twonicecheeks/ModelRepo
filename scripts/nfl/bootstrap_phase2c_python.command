#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
"$PY" -m pip install --disable-pip-version-check -q -r requirements/nfl-phase2c.txt
"$PY" scripts/nfl/check_phase1b_dependencies.py
"$PY" scripts/nfl/check_phase2c_dependencies.py

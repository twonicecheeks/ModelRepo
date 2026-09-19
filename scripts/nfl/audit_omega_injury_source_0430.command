#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="${0:A:h}"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT="${MODEL_ROOT_OVERRIDE:-$REPO_ROOT}"
DATA_ROOT="${MODEL_DATA_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
cd "$ROOT"

if [[ ! -x "$PY" ]]; then
  zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
fi

"$PY" scripts/nfl/check_phase1b_dependencies.py
"$PY" tests/nfl/test_omega_injury_source_audit_0430.py

exec "$PY" scripts/nfl/audit_omega_injury_source_0430.py \
  --root "$DATA_ROOT" \
  --years "${MODEL_OMEGA_INJURY_AUDIT_YEARS:-2019,2020,2021,2022,2023,2024}"

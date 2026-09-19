#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
cd "$ROOT"

if [[ ! -x "$PY" ]]; then
  zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
fi

"$PY" scripts/nfl/check_phase1b_dependencies.py
"$PY" tests/nfl/test_omega_lb_edge_archetype_0363.py
"$PY" tests/nfl/test_omega_lb_error_audit_0390.py

exec "$PY" scripts/nfl/audit_omega_offball_lb_error_0390.py   --root "$ROOT"   --evaluation-seasons "${MODEL_OMEGA_LB_039_AUDIT_SEASONS:-2021,2022,2023,2024}"

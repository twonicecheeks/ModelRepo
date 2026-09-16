#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
PY="$ROOT/scripts/nfl/diagnose_omega_propsmadness_nfl_ta_route_probe_0362.py"
[[ -f "$PY" ]] || { echo "FAIL missing diagnostic: $PY"; exit 1; }
python3 "$PY"

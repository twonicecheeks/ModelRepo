#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
python3 "$ROOT/scripts/nfl/import_omega_propsmadness_nfl_ta_probe_0174.py" "$@"

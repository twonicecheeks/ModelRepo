#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
python3 "$ROOT/scripts/nfl/inventory_omega_live_sources_014.py" --root "$ROOT"

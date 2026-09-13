#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
python3 "$ROOT/scripts/nfl/price_omega_tackle_ladder_015.py" --root "$ROOT" "$@"

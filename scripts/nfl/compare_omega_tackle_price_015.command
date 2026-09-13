#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
python3 "$ROOT/scripts/nfl/compare_omega_tackle_price_015.py" --root "$ROOT" "$@"

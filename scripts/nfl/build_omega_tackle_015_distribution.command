#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
python3 "$ROOT/scripts/nfl/build_omega_tackle_015_distribution.py" --root "$ROOT"

#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
python3 "$ROOT/scripts/nfl/init_omega_tackle_pregame_role_014.py" --root "$ROOT"

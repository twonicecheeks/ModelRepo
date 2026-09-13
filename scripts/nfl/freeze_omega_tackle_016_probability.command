#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
exec python3 "$ROOT/scripts/nfl/freeze_omega_tackle_016_probability.py" --root "$ROOT" "$@"

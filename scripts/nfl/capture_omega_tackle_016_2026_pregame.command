#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
exec python3 "$ROOT/scripts/nfl/capture_omega_tackle_016_2026_pregame.py" --root "$ROOT" "$@"

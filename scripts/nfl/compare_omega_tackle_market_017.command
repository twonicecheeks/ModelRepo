#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
PINNED="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
PY="python3"
[[ -x "$PINNED" ]] && PY="$PINNED"
"$PY" "$ROOT/scripts/nfl/compare_omega_tackle_market_017.py" --root "$ROOT" "$@"

#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
PINNED="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
PY="python3"; [[ -x "$PINNED" ]] && PY="$PINNED"
exec "$PY" "$ROOT/scripts/nfl/discover_omega_propsmadness_adapter_0171.py" --root "$ROOT" "$@"

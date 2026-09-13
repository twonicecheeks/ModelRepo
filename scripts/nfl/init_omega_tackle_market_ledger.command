#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || PY=python3
exec "$PY" "$ROOT/scripts/nfl/init_omega_tackle_market_ledger.py" --root "$ROOT"

#!/bin/zsh
set -euo pipefail
if (( $# < 1 )); then echo "usage: zsh scripts/nfl/append_omega_tackle_market_snapshot.command <capture.csv|json|jsonl>"; exit 2; fi
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || PY=python3
exec "$PY" "$ROOT/scripts/nfl/append_omega_tackle_market_snapshot.py" "$1" --root "$ROOT"

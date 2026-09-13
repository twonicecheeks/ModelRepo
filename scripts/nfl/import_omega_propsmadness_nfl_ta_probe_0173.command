#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
PY="$ROOT/scripts/nfl/import_omega_propsmadness_nfl_ta_probe_0173.py"
NFLPY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
if [[ -x "$NFLPY" ]]; then exec "$NFLPY" "$PY" --root "$ROOT" "$@"; fi
exec python3 "$PY" --root "$ROOT" "$@"

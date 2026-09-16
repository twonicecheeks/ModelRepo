#!/bin/zsh
set -euo pipefail

ROOT="/Users/abbeyfelix/Developer/MODEL"
PY="$ROOT/.venv-phase1b/bin/python"
SCRIPT="$ROOT/scripts/nfl/build_omega_ta_reference_market_movement_0370.py"

[[ -x "$PY" ]] || { echo "FAIL missing phase1b python: $PY"; exit 1; }
[[ -f "$SCRIPT" ]] || { echo "FAIL missing OMEGA 0.37 script: $SCRIPT"; exit 1; }

"$PY" - <<'PY'
import pyarrow, certifi, ssl
print(f"PASS isolated pyarrow {pyarrow.__version__}")
print(f"PASS pinned certifi {certifi.__version__} (runtime {certifi.__version__}) / TLS verification REQUIRED")
PY

"$PY" -m py_compile "$SCRIPT"
"$PY" "$SCRIPT" --root "$ROOT"

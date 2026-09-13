#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"
"$PY" "$ROOT/tests/models/nfl/game/test_phase2f_holdout.py"
"$PY" "$ROOT/tests/models/nfl/game/test_phase2f_integrity.py"
echo "AUDIT PASS — NFL Phase 2F frozen holdout gate"

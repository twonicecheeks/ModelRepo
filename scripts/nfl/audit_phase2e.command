#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PY" ]] || { echo "FAIL isolated NFL python missing"; exit 1; }
"$PY" tests/models/nfl/game/test_phase2e_freeze.py
"$PY" tests/models/nfl/game/test_phase2e_integrity.py
"$PY" tests/models/nfl/game/test_phase2d_hardening.py
"$PY" tests/models/nfl/game/test_phase2d_integrity.py
"$PY" tests/models/nfl/game/test_phase2d_base_api_compat.py
"$PY" tests/models/nfl/game/test_market_edge.py
echo "PASS Phase2E local audit · 2025 sealed · market isolation preserved"

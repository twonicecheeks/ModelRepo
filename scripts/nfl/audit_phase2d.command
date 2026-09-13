#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
PYBIN="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
[[ -x "$PYBIN" ]] || PYBIN=python3
"$PYBIN" tests/models/nfl/game/test_phase2d_safe_context.py
"$PYBIN" tests/models/nfl/game/test_phase2d_hardening.py
"$PYBIN" tests/models/nfl/game/test_market_edge.py
"$PYBIN" tests/models/nfl/game/test_phase2d_integrity.py
"$PYBIN" tests/models/nfl/game/test_phase2d_base_api_compat.py
"$PYBIN" - <<'PY'
from pathlib import Path
paths=['packages/models/nfl/game/phase2d_hardening.py','packages/models/nfl/game/market_edge.py','scripts/nfl/build_phase2d_safe_context.py','scripts/nfl/build_phase2d_hardening.py']
for p in paths: compile(Path(p).read_text(),p,'exec')
# Hard physical boundary: model hardening source may not import market_edge.
s=Path('scripts/nfl/build_phase2d_hardening.py').read_text()
assert 'import market_edge' not in s and 'from market_edge' not in s
print('PASS Phase2D.2 source compile / market isolation')
PY
echo "AUDIT PASS — NFL Phase 2D.2 base-API compatibility + solver-control hardening"

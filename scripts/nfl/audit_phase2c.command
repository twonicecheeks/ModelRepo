#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
python3 tests/models/nfl/game/test_phase2c_context.py
python3 tests/models/nfl/game/test_phase2c_model.py
python3 tests/models/nfl/game/test_phase2c_integrity.py
python3 - <<'PY'
from pathlib import Path
r=Path('.')
for p in ['packages/models/nfl/game/phase2c_context.py','packages/models/nfl/game/phase2c_model.py','scripts/nfl/build_phase2c_context.py','scripts/nfl/build_phase2c_model.py']:
    compile((r/p).read_text(),p,'exec')
print('PASS Phase2C source compile')
PY
print "AUDIT PASS — NFL Phase 2C QB / roster transition research"

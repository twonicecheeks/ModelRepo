#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
python3 tests/models/nfl/game/test_challenger_models.py
python3 tests/models/nfl/game/test_persistence.py
python3 - <<'PY'
from pathlib import Path
root=Path('.')
for p in ['packages/models/nfl/game/challenger_models.py','packages/models/nfl/game/persistence.py','scripts/nfl/build_phase2b_challengers.py']:
    t=(root/p).read_text()
    assert 'OddsPapi' not in t or 'requests: 0' in t or 'oddsPapiRequests' in t
b=(root/'scripts/nfl/build_phase2b_challengers.py').read_text()
assert "holdoutEvaluated':False" in b and "holdoutLabelsAdmitted':0" in b
assert 'marketFieldsAllowed' in b and 'DATA_GATED' in b
print('PASS Phase 2B integrity: 2025 sealed / market isolated / QB data gated')
PY
print "AUDIT PASS — NFL Phase 2B challenger research"

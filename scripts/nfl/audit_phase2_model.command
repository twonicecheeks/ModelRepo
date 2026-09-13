#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

echo "MODEL NFL 2.9.0 PHASE 2A MODEL AUDIT"
echo "Root: $ROOT"

test -f packages/models/nfl/game/research_model.py
test -f scripts/nfl/build_phase2_development.py
test -f scripts/nfl/build_phase2_development.command
test -f tests/models/nfl/game/test_research_model.py
test -f docs/architecture/NFL_2.9.0_PHASE2A_MODEL.md

grep -q 'DEVELOPMENT_ONLY_HOLDOUT_UNTOUCHED' packages/models/nfl/game/research_model.py
grep -q 'HOLDOUT_SEASON = 2025' packages/models/nfl/game/research_model.py
grep -q 'marketFieldsAllowed.*False' scripts/nfl/build_phase2_development.py
grep -q 'holdoutEvaluated.*False' scripts/nfl/build_phase2_development.py
grep -q 'oddsPapiRequests.*0' scripts/nfl/build_phase2_development.py

python3 tests/models/nfl/game/test_research_model.py
python3 tests/providers/nflverse/test_contract.py >/dev/null
python3 tests/providers/nflverse/test_dependency_versions.py >/dev/null
python3 tests/providers/nflverse/test_snapshot.py >/dev/null
python3 tests/providers/nflverse/test_normalize.py >/dev/null

echo "PASS Phase 2A model: fixed pregame differential feature set / L2 logistic / chronological development validation"
echo "PASS 2025 holdout boundary: excluded from model selection and candidate fitting"
echo "PASS market isolation: sportsbook fields remain forbidden; OddsPapi 0"

python3 - <<'PY'
import json
from pathlib import Path
root=Path('.')
m=json.loads((root/'apps/chrome-extension/src/manifest.json').read_text())
assert m['version']=='3.0.0', m
svc=(root/'services/market-service/src/model_service.py').read_text()
assert 'VERSION = "2.3.6"' in svc
print('PASS MLB production runtime remains frozen at extension 3.0.0 / service 2.3.6')
PY

if grep -R -n -E 'sportId[^0-9]*14|tournamentId[^0-9]*31|moneyline[^0-9]*141' \
  apps/chrome-extension/src services/market-service/src 2>/dev/null >/tmp/model_nfl_phase2a_market_hits.$$; then
  cat /tmp/model_nfl_phase2a_market_hits.$$
  rm -f /tmp/model_nfl_phase2a_market_hits.$$
  echo "FAIL NFL market runtime wiring appeared during Phase 2A"
  exit 1
fi
rm -f /tmp/model_nfl_phase2a_market_hits.$$

echo "PASS no NFL production/OddsPapi runtime wiring"
echo "AUDIT PASS — NFL 2.9.0 Phase 2A historical development model foundation"

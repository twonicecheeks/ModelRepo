#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
if [[ -n "${MODEL_ROOT_OVERRIDE:-}" ]]; then ROOT="$MODEL_ROOT_OVERRIDE"; fi
cd "$ROOT"

echo "MODEL NFL 2.9.0 PHASE 1 FOUNDATION AUDIT"
echo "Root: $ROOT"

test -f packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json
test -f packages/providers/nflverse/src/contract.py
test -f packages/models/nfl/game/historical_feature_core.py
test -f docs/architecture/NFL_2.9.0_PHASE1_DATA_CONTRACT.md

grep -q '"holdoutSeason": 2025' packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json
grep -q '"prospectiveSeason": 2026' packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json
grep -q 'NOT_A_2026_PRODUCTION_PROVIDER' packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json
grep -q 'No sportsbook price as a predictive input' packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json

python3 tests/providers/nflverse/test_contract.py
python3 tests/models/nfl/game/test_historical_feature_core.py

# NFL Phase 1 must not mutate current production runtime versions.
python3 - <<'PY'
import json
from pathlib import Path
root=Path('.')
m=json.loads((root/'apps/chrome-extension/src/manifest.json').read_text())
assert m['version']=='3.0.0', m
svc=(root/'services/market-service/src/model_service.py').read_text()
assert 'VERSION = "2.3.6"' in svc
print('PASS MLB runtime remains frozen at extension 3.0.0 / service 2.3.6')
PY

# No NFL OddsPapi runtime wiring yet.
if grep -R -n -E 'sportId[^0-9]*14|tournamentId[^0-9]*31|moneyline[^0-9]*141' \
  apps/chrome-extension/src services/market-service/src 2>/dev/null | grep -v 'archive/' >/tmp/model_nfl_phase1_market_hits.$$; then
  cat /tmp/model_nfl_phase1_market_hits.$$
  rm -f /tmp/model_nfl_phase1_market_hits.$$
  echo "FAIL NFL market runtime wiring appeared during Phase 1"
  exit 1
fi
rm -f /tmp/model_nfl_phase1_market_hits.$$

echo "PASS no NFL OddsPapi runtime wiring / no market dependency"
echo "AUDIT PASS — NFL 2.9.0 Phase 1 historical foundation"

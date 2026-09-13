#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

echo "MODEL NFL 2.9.0 PHASE 1B SNAPSHOT AUDIT"
echo "Root: $ROOT"

test -f packages/providers/nflverse/src/snapshot.py
test -f packages/providers/nflverse/src/normalize.py
test -f requirements/nfl-phase1b.txt
test -f scripts/nfl/build_phase1_snapshot.command
test -f scripts/nfl/check_phase1b_dependencies.py
test -f docs/architecture/NFL_2.9.0_PHASE1B_SNAPSHOT.md

grep -q '"contractVersion": "0.2.0"' packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json
grep -q '"trainingWindowStatus": "NOT_FROZEN"' packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json
grep -q '"historySeedSeasons"' packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json
grep -q '^pyarrow==25.0.1$' requirements/nfl-phase1b.txt
grep -q '^certifi==2026.7.22$' requirements/nfl-phase1b.txt
grep -q 'def _verified_tls_context' packages/providers/nflverse/src/snapshot.py
grep -q 'context=context' packages/providers/nflverse/src/snapshot.py
if grep -q -E 'CERT_NONE|_create_unverified_context|check_hostname[[:space:]]*=[[:space:]]*False' packages/providers/nflverse/src/snapshot.py; then
  echo "FAIL insecure TLS bypass detected in nflverse snapshot acquisition"
  exit 1
fi
grep -q 'versions_equivalent(certifi_runtime, CERTIFI_PIN)' scripts/nfl/check_phase1b_dependencies.py
grep -q 'def _pbp_schema_plan' packages/providers/nflverse/src/normalize.py
grep -q 'play_type' packages/providers/nflverse/src/normalize.py
echo "PASS NFL acquisition TLS integrity: pinned certifi CA bundle / verification required / no insecure bypass"
echo "PASS NFL dependency pin integrity: calendar-version normalization accepts equivalent zero-padded certifi runtime strings"
echo "PASS NFL PBP schema compatibility guard: no_play/qb_kneel semantics resolve through native flags or play_type"

python3 tests/providers/nflverse/test_contract.py
python3 tests/providers/nflverse/test_dependency_versions.py
python3 tests/providers/nflverse/test_snapshot.py
python3 tests/providers/nflverse/test_normalize.py
python3 tests/providers/nflverse/test_pbp_schema_compat.py

PLAN="$(python3 scripts/nfl/build_phase1_snapshot.py --root "$ROOT" --plan)"
python3 - "$PLAN" <<'PY'
import json, sys
x=json.loads(sys.argv[1])
assert x['analysisSeasons']==list(range(2016,2026)), x
assert x['historySeedSeasons']==[2015], x
assert x['trainingWindowFrozen'] is False
assert x['oddsPapiRequests']==0
assert len(x['assets'])==24, len(x['assets'])
print('PASS default immutable asset plan: 2015 seed + 2016-2025 audit window · 24 source assets · OddsPapi 0')
PY

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
  apps/chrome-extension/src services/market-service/src 2>/dev/null >/tmp/model_nfl_phase1b_market_hits.$$; then
  cat /tmp/model_nfl_phase1b_market_hits.$$
  rm -f /tmp/model_nfl_phase1b_market_hits.$$
  echo "FAIL NFL market runtime wiring appeared during Phase 1B"
  exit 1
fi
rm -f /tmp/model_nfl_phase1b_market_hits.$$

echo "PASS no NFL OddsPapi runtime wiring / production market dependency"
echo "AUDIT PASS — NFL 2.9.0 Phase 1B snapshot + normalization foundation"

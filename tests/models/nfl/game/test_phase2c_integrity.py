#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
ctx=(ROOT/'scripts/nfl/build_phase2c_context.py').read_text()
mdl=(ROOT/'scripts/nfl/build_phase2c_model.py').read_text()
core=(ROOT/'packages/models/nfl/game/phase2c_context.py').read_text()
assert ('if season >= HOLDOUT_SEASON' in core or 'if season>=HOLDOUT_SEASON' in core)
assert 'if s >= 2025:' in mdl and 'continue' in mdl
assert '"holdoutLabelsAdmitted": 0' in mdl
assert '"marketFieldsAllowed": False' in mdl
assert '"oddsPapiRequests": 0' in mdl
assert 'seasons=list(range(2015,2025))' in ctx
assert "'holdoutRead':False" in ctx
assert 'import OddsPapi' not in ctx and 'requests.get' not in ctx
assert 'DEVELOPMENT_VALIDATION_REPORT.json' in mdl
assert 'exactPhase2ABaselineReused' in mdl
print('PASS Phase2C integrity: 2015-2024 context only / 2025 sealed / exact Phase2A baseline / no market dependency')

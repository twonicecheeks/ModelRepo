#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
s=(ROOT/'scripts/nfl/build_phase2e_freeze.py').read_text()
assert 'season>=2025' in s
assert 'holdoutEvaluated' in s and 'holdoutLabelsAdmitted' in s
assert 'OddsPapi' not in s or 'oddsPapiRequests' in s
assert 'market_edge' not in s
assert '2018, 2019, 2020, 2021' not in s or 'SELECTION_SEASONS' in (ROOT/'packages/models/nfl/game/phase2e_freeze.py').read_text()
print('PASS Phase2E integrity boundary')

#!/usr/bin/env python3
from pathlib import Path
import ast
root=Path(__file__).resolve().parents[2]
app=(root/'scripts/nfl/append_omega_tackle_market_snapshot_017.py').read_text()
cmp=(root/'scripts/nfl/compare_omega_tackle_market_017.py').read_text()
assert 'model_probability' in app and 'predicted_xtc' in app and 'recommended_bet' in app
assert 'ONE_SIDED_EV_ONLY' in cmp and 'TWO_SIDED_NO_VIG' in cmp
assert 'AVAILABILITY_UNVERIFIED' in cmp and 'SETTLEMENT_UNRESOLVED' in cmp
assert 'marketEnteredModel' in cmp and "'actionableRows':0" in cmp
assert 'EXPECTED_WEEK1_LEDGER' in cmp and 'fe4991a743a1c02994b59d473a1bec9a1ccafa61a60548df43f2f5292e4ca08a' in cmp
for p in (root/'scripts/nfl').glob('*_017.py'):ast.parse(p.read_text())
print('PASS OMEGA 0.17 market-comparison contracts')

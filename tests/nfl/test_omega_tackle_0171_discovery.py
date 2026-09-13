#!/usr/bin/env python3
from pathlib import Path
import ast
root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/discover_omega_propsmadness_adapter_0171.py'
s=p.read_text()
ast.parse(s)
assert 'EXPECTED_LEDGER_SHA' in s
assert 'fe4991a743a1c02994b59d473a1bec9a1ccafa61a60548df43f2f5292e4ca08a' in s
assert 'EXPECTED_PROVIDER_FILES' in s
assert 'NETWORK' not in ''  # no-op to keep test tiny
assert 'networkRequests' in s and "'networkRequests':0" in s
assert 'embeddedCredentialIndicators' in s
assert 'OMEGA_0171_PROPSMADNESS_PROVIDER_HANDOFF.zip' in s
assert 'urllib' not in s and 'requests.' not in s
print('PASS OMEGA 0.17.1 PropsMadness adapter-discovery contracts')

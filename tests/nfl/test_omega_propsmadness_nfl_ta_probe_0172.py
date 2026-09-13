from pathlib import Path
import re
root=Path(__file__).resolve().parents[2]
js=(root/'packages/providers/propsmadness/nfl-tackle-probe/omega_propsmadness_nfl_ta_probe_0172.js').read_text()
imp=(root/'scripts/nfl/import_omega_propsmadness_nfl_ta_probe_0172.py').read_text()
assert 'Tckl+Ast' in js and "click('Tackles')" in js
assert '/api/offer/' in js
assert 'authorization' not in js.lower()
assert 'cookie' not in js.lower()
assert 'responseData' in js
assert 'OMEGA_PM_NFL_TA_PROBE_0.17.2' in js and 'OMEGA_PM_NFL_TA_PROBE_0.17.2' in imp
assert 'omegaIWritten' in imp and "False" in imp
print('PASS OMEGA 0.17.2 NFL T+A endpoint-probe contracts')

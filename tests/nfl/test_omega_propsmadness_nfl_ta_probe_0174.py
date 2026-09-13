from pathlib import Path
root=Path(__file__).resolve().parents[2]
js=(root/'packages/providers/propsmadness/nfl-tackle-probe/omega_propsmadness_nfl_ta_probe_0174.js').read_text()
imp=(root/'scripts/nfl/import_omega_propsmadness_nfl_ta_probe_0174.py').read_text()
assert 'performance.getEntriesByType' in js
assert 'domSnapshots' in js and 'jsonState' in js and 'apiEvents' in js
assert "interestingNetwork" in js and "p.includes('/api/')" in js
assert 'document.cookie' not in js and 'localStorage' not in js and 'sessionStorage' not in js
assert 'authorization' not in js.lower()
assert 'OMEGA_PM_NFL_TA_DISCOVERY_0.17.4' in js and 'OMEGA_PM_NFL_TA_DISCOVERY_0.17.4' in imp
assert 'if not (api or perf_n or dom_n or js_n)' in imp
assert 'marketNormalizationPerformed' in imp and "'omegaIWritten':False" in imp
print('PASS OMEGA 0.17.4 broad discovery probe contracts')

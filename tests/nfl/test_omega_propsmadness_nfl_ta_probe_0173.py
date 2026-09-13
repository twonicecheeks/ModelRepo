from pathlib import Path
root=Path(__file__).resolve().parents[2]
js=(root/'packages/providers/propsmadness/nfl-tackle-probe/omega_propsmadness_nfl_ta_probe_0173.js').read_text()
imp=(root/'scripts/nfl/import_omega_propsmadness_nfl_ta_probe_0173.py').read_text()
prep=(root/'scripts/nfl/prepare_omega_propsmadness_nfl_ta_probe_0173.command').read_text()
assert 'Tckl+Ast' in js and "click('Tackles')" in js
assert 'Blob' in js and '.download = filename()' in js
assert 'Download OMEGA T+A capture' in js
assert 'navigator.clipboard.writeText' not in js
assert 'OMEGA_PM_NFL_TA_PROBE_0.17.3' in js and 'OMEGA_PM_NFL_TA_PROBE_0.17.3' in imp
assert 'newest_capture' in imp and "Path.home()/'Downloads'" in imp
assert '--file' in imp
assert 'authorization' not in js.lower() and 'cookie' not in js.lower()
assert 'OMEGA-I writes: 0' in imp
assert 'orange' in prep.lower()
print('PASS OMEGA 0.17.3 file-handoff probe contracts')

from pathlib import Path
import re
root = Path(__file__).resolve().parents[2]
js=(root/"packages/providers/propsmadness/omega-probe/omega_propsmadness_nfl_ta_exact_capture_0175.js").read_text()
assert '=== "Tckl+Ast"' in js
assert 'target.click()' in js
assert 'location.pathname.startsWith("/nfl")' in js
assert "Tackles" not in re.sub(r'Tckl\+Ast','',js).split("target.click()")[0][-500:]  # no pre-click Tackles action
print("PASS OMEGA 0.17.5 exact-control capture regression")

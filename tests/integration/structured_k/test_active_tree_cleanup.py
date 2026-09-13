from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[3]
ext=ROOT/'apps/chrome-extension/src'
manifest=json.loads((ext/'manifest.json').read_text())
assert manifest['version']=='3.2.0'
assert not (ext/'popup.js').exists()
for rel in ['workflow_v1.js','workflow_v1_core.js','pm_model_v1_core.js','pm_model_v1_lab.js','ml_orchestrator_v0937.js','ml_remaining_slate_guard_v0936.js','network_probe.js','pm_v0937_page_bridge.js','propsmadness_table_probe_main.js']:
    assert not (ext/rel).exists(), f'retired runtime still active: {rel}'
assert 'web_accessible_resources' not in manifest
flat='\n'.join(str(x) for x in ext.iterdir())
assert '.pre_v' not in flat
assert not any(re.match(r'^(V0|v09)',p.name) for p in ext.iterdir() if p.is_file())
html=(ext/'popup.html').read_text()
for forbidden in ['popup.js','workflow_v1.js','workflow_v1_core.js','pm_model_v1_core.js','pm_model_v1_lab.js','ml_orchestrator_v0937.js']:
    assert forbidden not in html
for needed in ['model_v2_core.js','model_v2.js','features/data_pipeline/controller.js','features/slate_radar/radar_core.js','features/slate_radar/radar_panel.js','providers/public_research/public_research_core.js','models/mlb/k/structured_k_core.js','models/mlb/moneyline/structured_ml_core.js']:
    assert needed in html
all_runtime='\n'.join(p.read_text(errors='ignore') for p in ext.rglob('*') if p.is_file() and p.suffix in {'.js','.html','.json'})
assert 'window.PMV1Engine' not in all_runtime
print('PASS active extension tree: legacy PMV1Engine/Hydrate/Batch runtime and versioned clutter physically removed')

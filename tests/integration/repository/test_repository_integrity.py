from pathlib import Path
import json
import importlib.util
import tempfile

ROOT = Path(__file__).resolve().parents[3]
ext = ROOT / 'apps/chrome-extension/src'
packages = ROOT / 'packages'

manifest = json.loads((ext / 'manifest.json').read_text())
assert manifest['version'] == '3.2.0'
assert manifest['version_name'] == '3.2.0 Personnel & Matchup Impact'
assert 'https://news.google.com/*' in manifest['host_permissions']
assert 'https://www.fanduel.com/*' in manifest['host_permissions']
assert 'https://site.api.espn.com/*' in manifest['host_permissions']

# Runtime/package mirrors that are intended to be exact copies.
pairs = [
    (ext/'model_v2.js', packages/'core/src/trust/model_v2.js'),
    (ext/'model_v2_core.js', packages/'core/src/trust/model_v2_core.js'),
    (ext/'features/data_pipeline/controller.js', packages/'core/src/data_pipeline/controller.js'),
    (ext/'features/slate_radar/radar_core.js', packages/'core/src/slate_radar/radar_core.js'),
    (ext/'providers/public_research/public_research_core.js', packages/'providers/public_research/src/public_research_core.js'),
    (ext/'providers/nfl_public/nfl_public_core.js', packages/'providers/nfl_public/src/nfl_public_core.js'),
    (ext/'features/matchup_center/matchup_core.js', packages/'core/src/matchup_center/matchup_core.js'),
    (ext/'features/matchup_center/matchup_intelligence_core.js', packages/'core/src/matchup_center/matchup_intelligence_core.js'),
    (ext/'models/mlb/k/structured_k_core.js', packages/'models/mlb/k/structured_k_core.js'),
    (ext/'models/mlb/moneyline/structured_ml_core.js', packages/'models/mlb/moneyline/structured_ml_core.js'),
]
for a,b in pairs:
    assert a.read_text() == b.read_text(), f'mirror divergence: {a} != {b}'

controller = (ext/'features/data_pipeline/controller.js').read_text()
assert "const VERSION='1.13.0'" in controller
assert "release:'3.0.0'" in controller
assert 'MODEL STRUCTURED ML PRODUCTION AUDIT 3.0.0' in controller
assert 'fetchRecentTransactions' in controller and 'fetchNumberFireProjection' in controller and 'fetchResearchBundle' in controller
assert 'refreshResearch' in controller and 'model_mlb_public_research_current' in controller

# Service source/templates must agree on current non-user-owned metadata.
svc_path = ROOT/'services/market-service/src/model_service.py'
svc_text = svc_path.read_text()
assert 'VERSION = "2.3.7"' in svc_text
K_LINEAGE = 'mlb-k-v0.8.3-sample-shrinkage-workload-2026-09-07'
ML_LINEAGE = 'mlb-moneyline-v0.8.0-offense-strength-2026-09-06'
assert K_LINEAGE in svc_text and ML_LINEAGE in svc_text

root_tpl = ROOT/'services/market-service/config.template.json'
src_tpl = ROOT/'services/market-service/src/config.template.json'
assert root_tpl.read_text() == src_tpl.read_text(), 'service config templates diverged'
tpl = json.loads(src_tpl.read_text())
assert tpl['serviceVersion'] == '2.3.7'
assert tpl['sports']['mlb']['modelAdaptersAvailable'] == [ML_LINEAGE, K_LINEAGE]

# Persisted config is allowed to be old, but runtime-owned metadata must normalize to running code.
spec = importlib.util.spec_from_file_location('model_service_integrity', svc_path)
svc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(svc)
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    svc.APP_DIR = td
    svc.CONFIG_PATH = td/'config.json'
    svc.CONFIG_PATH.write_text(json.dumps({
        'serviceVersion': '2.3.1',
        'sports': {'mlb': {'modelAdaptersAvailable': ['stale-adapter']}},
        'provider': {'oddspapi': {'minRefreshSeconds': 91}}
    }))
    merged = svc.load_config()
    assert merged['serviceVersion'] == '2.3.7'
    assert merged['sports']['mlb']['modelAdaptersAvailable'] == [ML_LINEAGE, K_LINEAGE]
    assert merged['provider']['oddspapi']['minRefreshSeconds'] == 91, 'user config should still override user-owned fields'

checkpoint = (ROOT/'docs/v281 Model Checkpoint.rtf').read_text()
assert '* Slate Radar: **1.7**' in checkpoint
assert '* Data Pipeline: **1.13.0**' in checkpoint
assert 'RCE-0.5' in checkpoint and 'Public Research provider: **0.5.0**' in checkpoint
active = (ROOT/'docs/architecture/ACTIVE_RUNTIME.md').read_text()
for marker in ('3.2.0', '2.3.7', 'Slate Radar: **1.7', 'RCE-0.5', 'MLB Public Research provider: **0.5.0**', 'NFL Public Research provider: **0.4.0**', 'Matchup Intelligence: **0.2.0**', K_LINEAGE):
    assert marker in active
assert (ROOT/'docs/MODEL_3.0_MATCHUP_CENTER_CHECKPOINT.md').is_file()
assert (ROOT/'docs/MODEL_3.0.1_MATCHUP_DETAIL_CHECKPOINT.md').is_file()
assert (ROOT/'docs/MODEL_3.0.2_MATCHUP_CLARITY_CHECKPOINT.md').is_file()
assert (ROOT/'docs/MODEL_3.1_MATCHUP_INTELLIGENCE_CHECKPOINT.md').is_file()
assert (ROOT/'docs/MODEL_3.2_PERSONNEL_MATCHUP_IMPACT_CHECKPOINT.md').is_file()

workspace = (ext/'features/workspace/workspace_shell.js').read_text()
popup = (ext/'popup.html').read_text()
radar = (ext/'features/slate_radar/radar_core.js').read_text()
panel = (ext/'features/slate_radar/radar_panel.js').read_text()
research = (ext/'providers/public_research/public_research_core.js').read_text()
nfl_research=(ext/'providers/nfl_public/nfl_public_core.js').read_text()
matchup=(ext/'features/matchup_center/matchup_core.js').read_text()
matchup_panel=(ext/'features/matchup_center/matchup_panel.js').read_text()
matchup_intelligence=(ext/'features/matchup_center/matchup_intelligence_core.js').read_text()
assert "get('workspace')==='1'" in workspace and 'body.classList.add' in workspace
assert 'features/workspace/workspace_shell.js' in popup
assert 'providers/public_research/public_research_core.js' in popup
assert "const VERSION='1.7'" in radar and "const RESEARCH_VERSION='RCE-0.5'" in radar
assert 'probabilityMutationFromResearch:false' in radar
assert "gap!==null&&gap>=.12" in radar and "verdict='CONFLICT'" in radar
assert "const VERSION='0.5.0'" in research and 'numberFire via FanDuel Research' in research and 'Google News RSS' in research and 'materialSummary' in research
assert 'WHY THIS PROBABILITY?' in panel and 'Recent Form' in panel and 'Research probability mutation' in panel
assert 'INDEPENDENT ML PROJECTION' in panel and 'SOURCED PUBLIC RESEARCH' in panel and 'NEWS HOLD' in panel
assert 'BET STATUS / WHY' in panel and 'STRONGEST SUPPORT' in panel and 'STRONGEST OPPOSITION' in panel
assert 'MATERIAL FINDINGS' in panel and 'Model Thesis' in panel and 'Research Confidence' in panel
assert 'modelDeltaPP' in research and 'assessment' in research
assert "const VERSION='0.4.0'" in nfl_research and 'ESPN NFL SCOREBOARD + ESPN GAME SUMMARY + GOOGLE NEWS' in nfl_research and 'parseSummary' in nfl_research
assert "const VERSION='1.4.0'" in matchup and 'mlbMatchups' in matchup and 'nflMatchups' in matchup and 'omegaForGame' in matchup
assert "const VERSION='0.2.0'" in matchup_intelligence and 'mlbIntelligence' in matchup_intelligence and 'nflIntelligence' in matchup_intelligence and 'probabilityMutation:false' in matchup_intelligence
assert 'MODEL · Matchup Center' in matchup_panel and 'REFRESH NFL WEEK + DETAIL' in matchup_panel and 'OMEGA TACKLE MODEL' in matchup_panel and 'INJURY / AVAILABILITY IMPACT' in matchup_panel
assert 'providers/nfl_public/nfl_public_core.js' in popup and 'features/matchup_center/matchup_panel.js' in popup and 'features/matchup_center/matchup_intelligence_core.js' in popup
assert 'MODEL_TRUST_CONTROLLER' in controller and 'refreshFromLatest' in controller and '0 new API' in controller
trust_js=(ext/'model_v2.js').read_text()
assert 'LATEST_MARKET_ZERO_API' in trust_js and 'edgeMarketSignature' in trust_js and 'modelV2PreviousEdgeBoard' in trust_js
assert '/v1/nfl/omega/current' in svc_text and 'load_omega_nfl_current' in svc_text
print('PASS repository integrity: 3.2.0 Personnel & Matchup Impact, lineup transition audit, NFL depth-chart weighting, frozen model/service boundaries')

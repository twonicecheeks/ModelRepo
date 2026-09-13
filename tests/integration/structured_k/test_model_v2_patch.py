from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'apps/chrome-extension/src/model_v2.js'
s=p.read_text(encoding='utf-8')
assert s == (ROOT/'packages/core/src/trust/model_v2.js').read_text(encoding='utf-8'), 'Trust package/extension mirrors diverged'
assert "const V='3.0.0';" in s
assert 'model_mlb_k_projection_board_current' in s
assert "model_mlb_k_projection_board_current" in s
assert "marketReferenceSource:'PROPSMADNESS_MULTI_BOOK_K_REFERENCE'" in s
assert "EXPECTED_K_INDEPENDENT_OF_TARGET_K_LINE" in s
assert 'structured K lineage is prospective after input migration' in s
assert 'K_ONLY_ZERO_ODDSPAPI' in s
assert '0 requests · K-only local evaluation' in s
assert 'player props NOT INCLUDED' in s
# Production ML is now sourced only from the structured ML board.
assert 'model_mlb_ml_projection_board_current' in s
assert "productionModelSource:'STRUCTURED_ML_BOARD'" in s
assert 'Legacy PMV1Engine runtime: REMOVED · production dependency: NO' in s
assert 'model_mlb_slate_radar_current' in s
assert 'Slate Radar is preliminary-only scouting and never feeds Trust' in s
assert 'Opportunity order: VERIFIED > WATCH (NOT VERIFIED) > preliminary Radar > RESEARCH ANOMALY > PASS/BLOCKED' in s
assert 'core.sortEdgesByOpportunity' in s
assert 'WATCH (NOT VERIFIED)' in s and 'RESEARCH ANOMALY' in s
assert 'window.PMV1Engine' not in s and 'getMlSlate' not in s and 'projectGame(game)' not in s
assert 'model_mlb_ml_shadow_board_current' not in s
assert 'indexMarketsByGamePk' in s and 'marketRowRank' in s, 'Trust must defensively prefer the strongest canonical market row per gamePk'
assert "state.lastRefreshMode='STRUCTURED_ML_FULL_GAME_MARKET'" in s
subprocess.run(['node','--check',str(p)],check=True)
print('PASS Trust integration: K live path preserved; Structured ML is production Trust source')

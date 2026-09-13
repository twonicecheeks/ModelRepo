from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
c=(ROOT/'packages/core/src/data_pipeline/controller.js').read_text(encoding='utf-8')
ce=(ROOT/'apps/chrome-extension/src/features/data_pipeline/controller.js').read_text(encoding='utf-8')
props=(ROOT/'packages/providers/propsmadness/src/table_core.js').read_text(encoding='utf-8')+(ROOT/'packages/providers/propsmadness/src/table_main.js').read_text(encoding='utf-8')
k=(ROOT/'packages/models/mlb/k/structured_k_core.js').read_text(encoding='utf-8')
ml=(ROOT/'packages/models/mlb/moneyline/structured_ml_core.js').read_text(encoding='utf-8')
assert c == ce, 'controller package/extension mirrors diverged'
assert "const VERSION='1.13.0'" in c
assert "kCore.VERSION!=='1.4'" in c
assert "mlCore.VERSION!=='1.3'" in c
assert "savantCore.VERSION!=='1.2'" in c
assert "starterCore.VERSION!=='1.5'" in c
assert "wrcCore.VERSION!=='1.0'" in c
assert "bullpenCore.VERSION!=='1.1'" in c
assert "parkCore.VERSION!=='1.1'" in c
assert "researchCore.VERSION!=='0.5.0'" in c
assert "probablePitcher(note),lineups" in c
assert '/boxscore' in c and 'resolvePregameLineups' in c
assert 'model_mlb_k_projection_board_current' in c
assert 'model_mlb_ml_projection_board_current' in c
assert 'model_mlb_slate_radar_current' in c and 'model_mlb_lineup_transition_baselines' in c and 'advanceLineupBaselines' in c
assert "radarCore.VERSION!=='1.7'" in c
assert 'radarCore.buildBoard' in c and 'rostersByTeam:bullpenResult.rostersByTeam' in c
assert 'PRELIMINARY ONLY' in c and '0 new API' in c
assert 'SYNC + BUILD K + ML + TRUST' in c and 'COPY K BOARD' in c and 'COPY ML BOARD AUDIT' in c and 'OPEN WORKSPACE' in c
assert 'openWorkspace' in c and "popup.html?workspace=1" in c and 'chrome.tabs.query' in c and 'chrome.tabs.update' in c
assert 'fetchRecentSchedule' in c and 'mlbRecentResults' in c and 'recentSchedule:recentScheduleResult.bundle' in c
assert 'fetchRecentTransactions' in c and 'fetchResearchBundle' in c and 'fetchNumberFireProjection' in c
assert 'Google News' not in c or 'news.google.com' in (ROOT/'apps/chrome-extension/src/manifest.json').read_text()
assert 'REFRESH RESEARCH' in c and 'refreshResearch' in c and 'model_mlb_public_research_current' in c
assert 'Research Confirmation' in c and 'Research never mutates model probability' in c
assert 'MODEL_TRUST_CONTROLLER' in c and 'refreshFromLatest' in c and '0 new API' in c
assert 'productionPathCutover:true' in c and 'productionModelSource' in c and 'oddsPapiRequests:0' in c
assert "REAL_FANGRAPHS_EXACT_MLBAM_ID" in c
assert "STRUCTURED_MLB_STATSAPI" in c
assert 'sourceSchemaInventory' not in c+props
assert 'schemaProfile' not in props and 'schemaProfiler' not in props
assert 'bootstrap.js' not in c
assert 'seasonBundle' in c and 'year-1' in c
assert 'fetchFangraphs' in c and 'buildUrl(year)' in c
assert 'fetchBullpenResources' in c and 'parseYesterdayUsage' in c and 'buildRosterUrl' in c and 'buildStatsUrl' in c and 'parseTeamPitchingStats' in c
assert 'fetchParkFactorsAdaptive' in c and 'MODEL_SAVANT_PARK_CORE' in c and 'BASEBALL_SAVANT_LONGEST_AVAILABLE_ROLLING_WINDOW' in c
assert 'parkCore.buildUrl(year,3)' in c and 'for(const rolling of [2,1])' in c
assert 'TARGET_K_MARKET_WEIGHT=0' in k
assert "CALIBRATION_STATUS='PRODUCTION_INPUT_MIGRATION'" in ml
print('PASS controller contract: K workload/sample hardening + ML workload gate + Slate Radar + sourced research + automatic zero-new-API Trust rebuild')

assert 'window.PMV1Engine' not in c
assert 'blockLegacyLiveClicks' not in c

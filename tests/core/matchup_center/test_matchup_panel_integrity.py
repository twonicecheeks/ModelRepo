from pathlib import Path
s=Path('apps/chrome-extension/src/features/matchup_center/matchup_panel.js').read_text()
assert "const VERSION='1.4.0'" in s
for marker in ['REFRESH NFL WEEK + DETAIL','REFRESH MLB RESEARCH','GAME OUTLOOK','STARTING PITCHING','OFFENSE / RECENT FORM','BULLPEN','MARKET / MOVEMENT','BOTTOM LINE','QB / STARTING-ROLE CONTEXT','INJURY / AVAILABILITY IMPACT','OMEGA TACKLE MODEL','model_nfl_omega_matchup_current','TRUST STATUS','BACKGROUND SOURCES','PRE-GAMEDAY / NOT ACTIONABLE','Official lineups:','MATCHUP INTELLIGENCE','PUBLIC-CONTEXT INTELLIGENCE','LINEUP / PERSONNEL IMPACT','PERSONNEL / UNIT IMPACT','depthChartUrl']:
    assert marker in s,marker
assert 'MODEL_DATA_PIPELINE_CONTROLLER' in s and 'MODEL_NFL_PUBLIC_CORE' in s and 'MODEL_MATCHUP_CORE' in s and 'MODEL_MATCHUP_INTELLIGENCE' in s
assert "serviceGet?.('/v1/nfl/omega/current')" in s
print('PASS Matchup Center panel 1.4 integrity: expanded MLB/NFL detail panels + player-specific NFL context + read-only OMEGA bridge')

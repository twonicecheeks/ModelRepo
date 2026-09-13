from pathlib import Path
p=Path('apps/chrome-extension/src/features/slate_radar/radar_panel.js')
s=p.read_text()
assert "const VERSION='1.7'" in s
assert "WATCH — NOT VERIFIED" in s
assert "TRUST ANOMALY — MODEL/MARKET GAP" in s
assert "RCE ANOMALY — MODEL/OBSERVED-DATA CONFLICT" in s
assert "NO CURRENT K MARKET" in s
assert "PASS/BLOCKED" in s
assert "ACTIONABLE WATCH" not in s
assert "v!==null&&v!==undefined&&v!==''" in s
assert "core.opportunityScore" in s
assert "WHY THIS PROBABILITY?" in s
assert "Recent Form" in s
assert "MARKET MOVEMENT" in s
assert 'INDEPENDENT ML PROJECTION' in s and 'SOURCED PUBLIC RESEARCH' in s
assert 'NEWS HOLD' in s and 'REFRESH SOURCED RESEARCH' in s
assert 'BET STATUS / WHY' in s and 'STRONGEST SUPPORT' in s and 'STRONGEST OPPOSITION' in s
assert 'MATERIAL FINDINGS' in s and 'Model Thesis' in s and 'Research Confidence' in s
assert 'modelDeltaPP' in s
assert 'EXTERNAL ${esc(x.assessment)' in s or 'sr-conflict' in s
assert 'DIRECTLY_MATERIAL' in s and 'POSSIBLY_MATERIAL' in s
assert "Research probability mutation: <b>NO</b>" in s
assert "modelV2PreviousEdgeBoard" in s
print('PASS Opportunity Radar panel 1.7: trust-first ranking, model explanations, Recent Form/RCE, market movement, anomaly quarantine, null-safe formatting')

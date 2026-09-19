#!/usr/bin/env python3
from pathlib import Path
import importlib.util
root=Path(__file__).resolve().parents[2]
p=root/'packages/models/nfl/game/omega_market_calibration_0350.py'
spec=importlib.util.spec_from_file_location('m',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

base={
 'game_id':'2026_02_DET_BUF','player_id':'P1','player_name':'One','team':'BUF','position_group':'LB',
 'line':7.5,'over_odds_american':-128,'under_odds_american':101,
 'control_best_side':'UNDER','control_best_ev':0.4034,'role_shadow_best_side':'UNDER','role_shadow_best_ev':0.371,
 'control_p_over':0.3018,'control_p_under':0.6982,'role_shadow_p_over':0.3179,'role_shadow_p_under':0.6821,
 'tracks_agree_side':'TRUE','role_state':'ROLE_ALIGNED','operational_status':'PRELIMINARY_NO_AUTHORITATIVE_INACTIVE_OVERLAY',
 'market_quote_classification':'EXECUTABLE_OFFER','market_source':'propsmadness-table-api'
}
g=m.grade_row(base,4)
assert g['actual_side']=='UNDER' and g['control_selected_hit']==1
assert g['control_ev_bin']=='EV_35_PLUS'
assert abs(g['control_selected_probability']-.6982)<1e-12
assert abs(g['control_realized_roi']-1.01)<1e-12
assert g['clean_role_state'] and g['executable_quote']

bad=dict(base);bad.update({'player_id':'P2','player_name':'Two','team':'DET','line':3.5,'control_best_side':'UNDER','role_shadow_best_side':'UNDER','control_p_under':.65,'control_p_over':.35,'role_shadow_p_under':.63,'role_shadow_p_over':.37,'control_best_ev':.39,'role_state':'STARTER_CONFLICT_REVIEW','operational_status':'REVIEW_STARTER_CONFLICT'})
g2=m.grade_row(bad,5)
assert g2['control_selected_hit']==0 and g2['quarantined_or_reference']

ref=dict(base);ref.update({'player_id':'P3','control_best_side':'OVER','role_shadow_best_side':'OVER','control_p_over':.70,'control_p_under':.30,'role_shadow_p_over':.68,'role_shadow_p_under':.32,'control_best_ev':.18,'over_odds_american':-110,'role_state':'ROLE_ALIGNED','operational_status':'REFERENCE_ONLY_NOT_EXECUTABLE','market_quote_classification':'REFERENCE_ONLY_NON_EXECUTABLE'})
g3=m.grade_row(ref,8)
assert g3['control_selected_hit']==1 and g3['quarantined_or_reference']

s=m.summarize([g,g2,g3])
assert s['all']['rows']==3
assert s['cleanRoleExecutableNotQuarantined']['rows']==1
assert s['filteredOutOrRoleConflict']['rows']==2
assert s['extremeEv35Plus']['gradedSelectedSides']==2
assert s['extremeEv35Plus']['calibrationStatus']=='SAMPLE_INSUFFICIENT'
assert s['extremeEv35Plus']['automaticProbabilityCompressionAllowed'] is False
assert s['modelRefitPerformed'] is False and s['frozenOmegaMutation'] is False

assert abs(m.american_profit_per_unit(127)-1.27)<1e-12
assert abs(m.american_profit_per_unit(-200)-.5)<1e-12
print('PASS OMEGA 0.35 postgame market calibration contracts · no refit · no frozen mutation')

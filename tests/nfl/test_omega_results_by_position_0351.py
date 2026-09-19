#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/report_omega_results_by_position_0351.py'
spec=importlib.util.spec_from_file_location('m',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

evals=[
 {'evaluation_id':'E1','packaged_at':'2026-09-10T10:00:00Z'},
 {'evaluation_id':'E2','packaged_at':'2026-09-10T11:00:00Z'},
]
players=[
 {'evaluation_id':'E1','game_id':'G','player_id':'P1','position':'MLB','position_group':'LB','grade_status':'GRADED','predicted_xtc':'6','actual_xtc':'5'},
 {'evaluation_id':'E2','game_id':'G','player_id':'P1','position':'MLB','position_group':'LB','grade_status':'GRADED','predicted_xtc':'5.5','actual_xtc':'5'},
 {'evaluation_id':'E1','game_id':'G','player_id':'P2','position':'CB','position_group':'DB','grade_status':'GRADED','predicted_xtc':'4','actual_xtc':'6'},
]
latest,eids=m.latest_player_rows(players,m.evaluation_times(evals))
assert len(latest)==2 and eids[('G','P1')]=='E2'
fm=m.forecast_metrics(latest)
assert fm['n']==2 and abs(fm['mae']-1.25)<1e-12
assert m.canonical_position_row({'position':'DE','position_group':'LB'})=='EDGE'
assert m.canonical_position_row({'position':'EDGE','position_group':'LB'})=='EDGE'
assert m.canonical_position_row({'position':'LB','position_group':'LB','current_depth_position':'DE'})=='EDGE'
assert m.canonical_position_row({'position':'LB','position_group':'DL'})=='EDGE'

thresholds=[
 {'evaluation_id':'E1','game_id':'G','player_id':'P1','grade_status':'GRADED','model_probability':'.7','actual_event':'1'},
 {'evaluation_id':'E2','game_id':'G','player_id':'P1','grade_status':'GRADED','model_probability':'.8','actual_event':'1'},
 {'evaluation_id':'E1','game_id':'G','player_id':'P2','grade_status':'GRADED','model_probability':'.6','actual_event':'0'},
]
lt=m.latest_threshold_rows(thresholds,eids)
assert len(lt)==2 and any(r['evaluation_id']=='E2' and r['player_id']=='P1' for r in lt)

decisions=[
 {'decision_id':'D1','score_id':'1','game_id':'G','player_id':'P1','grade_status':'GRADED','result':'WIN','realized_roi_1u':'1.0','expected_roi':'.1','model_probability':'.6'},
 {'decision_id':'D1','score_id':'2','game_id':'G','player_id':'P1','grade_status':'GRADED','result':'WIN','realized_roi_1u':'1.0','expected_roi':'.1','model_probability':'.6'},
 {'decision_id':'D2','score_id':'2','game_id':'G','player_id':'P2','grade_status':'GRADED','result':'LOSS','realized_roi_1u':'-1','expected_roi':'.08','model_probability':'.57'},
]
dd=m.dedupe_decisions(decisions)
assert len(dd)==2
pmap=m.position_map(latest)
dd=m.with_positions(dd,pmap)
by=m.grouped(dd,m.decision_metrics)
assert by['LB']['wins']==1 and by['DB']['losses']==1
assert by['LB']['sampleStatus']=='VERY_SMALL_SAMPLE'

m35=[
 {'position_group':'LB','control_selected_hit':'1','control_realized_roi':'1.1','control_selected_probability':'.65'},
 {'position_group':'LB','control_selected_hit':'0','control_realized_roi':'-1','control_selected_probability':'.62'},
 {'position_group':'DB','control_selected_hit':'1','control_realized_roi':'.9','control_selected_probability':'.58'},
]
m35all=m.market035_metrics(m35)
assert m35all['n']==3 and m35all['wins']==2 and m35all['losses']==1
m35by=m.grouped(m35,m.market035_metrics)
assert m35by['LB']['n']==2 and m35by['DB']['wins']==1
for r,side in zip(m35,['UNDER','OVER','UNDER']):r['control_best_side']=side
ps=m.grouped_position_side(m35,m.market035_metrics,'control_best_side')
assert ps['LB|UNDER']['n']==1 and ps['LB|OVER']['n']==1 and ps['DB|UNDER']['wins']==1
print('PASS OMEGA 0.35.1 cumulative results-by-position contracts')

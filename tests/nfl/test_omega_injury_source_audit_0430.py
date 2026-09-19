#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/audit_omega_injury_source_0430.py'
spec=importlib.util.spec_from_file_location('audit0430',p)
m=importlib.util.module_from_spec(spec);sys.modules['audit0430']=m;spec.loader.exec_module(m)

assert m.timing_class('2024-09-06T12:00:00Z','2024-09-08')=='STRICT_PRIOR_DAY'
assert m.timing_class('2024-09-08T10:00:00Z','2024-09-08')=='SAME_GAMEDAY'
assert m.timing_class('2024-09-09T01:00:00Z','2024-09-08')=='AFTER_GAMEDAY'
assert m.timing_class('', '2024-09-08')=='MISSING_DATE'

sched={(2024,1,'A'):{'game_id':'G','gameday':'2024-09-08','gametime':'13:00','team':'A'}}
rows=[
 {'season':2024,'season_type':'REG','team':'A','week':1,'gsis_id':'P1','position':'LB','full_name':'A One',
  'report_status':'Questionable','practice_status':'Limited','date_modified':'2024-09-06T12:00:00Z'},
 {'season':2024,'season_type':'REG','team':'A','week':1,'gsis_id':'P2','position':'LB','full_name':'A Two',
  'report_status':'Out','practice_status':'Did Not Participate','date_modified':'2024-09-08T10:00:00Z'},
]
s=m.summarize_year(2024,rows,sched,'season_type')
assert s['rows']==2
assert s['gsisIdCoverage']==1.0
assert s['scheduleJoinCoverage']==1.0
assert s['timingCounts']['STRICT_PRIOR_DAY']==1
assert s['timingCounts']['SAME_GAMEDAY']==1
assert s['duplicateExtraRows']==0
assert s['seasonTypePolicy']=='EXPLICIT_SEASON_TYPE'

game_rows=[dict(r,game_type=r['season_type']) for r in rows]
for r in game_rows:r.pop('season_type',None)
sg=m.summarize_year(2024,game_rows,sched,'game_type')
assert sg['rows']==2
assert sg['seasonTypePolicy']=='EXPLICIT_GAME_TYPE'

legacy=[{k:v for k,v in r.items() if k!='season_type'} for r in rows]
sl=m.summarize_year(2024,legacy,sched,None)
assert sl['rows']==2
assert sl['seasonTypePolicy']=='INFERRED_FROM_REGULAR_SCHEDULE_WEEK_WINDOW'
print('PASS OMEGA 0.43 injury source timing audit contracts · season_type/game_type/legacy adapters')

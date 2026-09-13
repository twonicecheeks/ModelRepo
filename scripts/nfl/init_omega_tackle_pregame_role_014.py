#!/usr/bin/env python3
"""Create the source-neutral OMEGA pregame availability/role capture contract."""
from pathlib import Path
import argparse,csv,json
FIELDS=[
'captured_at','source','source_priority','source_updated_at','source_record_id','game_id','season','week','game_date','team','opponent',
'player_id','player_name','position','roster_status','game_status','injury_designation','listed_starter','depth_position','depth_role','notes'
]
ENUMS={
'source_priority':['OFFICIAL_NFL','OFFICIAL_TEAM','AUTHORITATIVE_PROVIDER','SECONDARY_PROVIDER','MANUAL_VERIFIED'],
'roster_status':['ACTIVE_ROSTER','PRACTICE_SQUAD','IR','PUP','NFI','SUSPENDED','EXEMPT','FREE_AGENT','UNKNOWN'],
'game_status':['ACTIVE','INACTIVE','OUT','DOUBTFUL','QUESTIONABLE','PROBABLE','NOT_LISTED','UNKNOWN'],
'listed_starter':['TRUE','FALSE','UNKNOWN'],
'depth_role':['STARTER','BACKUP','ROTATIONAL','SPECIALIST','UNKNOWN'],
}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args();root=Path(a.root).resolve();d=root/'data/manual/nfl/omega/pregame_role';d.mkdir(parents=True,exist_ok=True)
 t=d/'OMEGA_PREGAME_ROLE_CAPTURE_TEMPLATE.csv';s=d/'OMEGA_PREGAME_ROLE_SCHEMA.json'
 if not t.exists():
  with t.open('w',newline='',encoding='utf-8') as f:csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n').writeheader()
 schema={'schemaVersion':'OMEGA_PREGAME_ROLE_INPUT_0.14','purpose':'Pregame football-state input only; no sportsbook/market/model-derived fields','fields':FIELDS,'enums':ENUMS,'required':['captured_at','source','source_priority','source_updated_at','game_id','season','week','team','player_id','player_name','roster_status','game_status','listed_starter','depth_role'],'forbiddenFieldPatterns':['odds','price','line','market','edge','ev','model_probability','predicted_xtc','actual_xtc'],'failClosedRule':'A target player is not VERIFIED-ready when identity, roster/game status, freshness, or required pregame role state is unresolved.'}
 s.write_text(json.dumps(schema,indent=2)+'\n',encoding='utf-8')
 print(f'PASS OMEGA pregame role template: {t}');print(f'PASS schema: {s}');print('PASS sportsbook/model-derived fields forbidden from raw pregame-state capture')
 return 0
if __name__=='__main__':raise SystemExit(main())

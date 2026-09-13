#!/usr/bin/env python3
from pathlib import Path
import argparse,csv,json
FIELDS=[
 'captured_at','source','book','game_id','game_date','away_team','home_team',
 'player_id','player_name','player_team','opponent','market_kind','market_label','line',
 'over_odds_american','under_odds_american','one_sided_side','one_sided_odds_american',
 'settlement_scope','includes_special_teams','stat_correction_policy','source_event_id','notes'
]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args()
 root=Path(a.root).resolve();base=root/'data/manual/nfl/omega/market';base.mkdir(parents=True,exist_ok=True)
 p=base/'OMEGA_TACKLE_MARKET_CAPTURE_TEMPLATE_017.csv'
 if not p.exists():
  with p.open('w',newline='',encoding='utf-8') as f:csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n').writeheader()
 schema={'schemaVersion':'OMEGA_TACKLE_MARKET_CAPTURE_0.17','fields':FIELDS,'rules':{'rawOnly':True,'modelFieldsForbidden':True,'comparisonMarketKind':'tackles_assists','halfPointLinesOnlyForComparison':True,'oneSided':'EV_ONLY_NO_DEVIG','settlementUnknown':'NON_ACTIONABLE','oddsPapiPlayerPropRequests':0}}
 (base/'OMEGA_TACKLE_MARKET_CAPTURE_SCHEMA_017.json').write_text(json.dumps(schema,indent=2)+'\n')
 print(f'PASS market capture template: {p}')
 print('PASS raw market schema only · no model probability/edge/EV fields')
 return 0
if __name__=='__main__':raise SystemExit(main())

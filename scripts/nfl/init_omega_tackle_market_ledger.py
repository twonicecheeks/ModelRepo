#!/usr/bin/env python3
from pathlib import Path
import argparse,csv

FIELDS=[
    'captured_at','source','book','game_id','game_date','away_team','home_team',
    'player_id','player_name','player_team','opponent','market_kind','market_label',
    'line','over_odds_american','under_odds_american','one_sided_side','one_sided_odds_american',
    'settlement_scope','includes_special_teams','stat_correction_policy','source_event_id','notes'
]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args()
    root=Path(a.root).resolve();out=root/'data/manual/nfl/omega/OMEGA_TACKLE_MARKET_CAPTURE_TEMPLATE.csv';out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        print(f'PASS template already exists: {out}');return 0
    with out.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n');w.writeheader()
    print(f'PASS OMEGA tackle market capture template: {out}')
    print('NOTE: settlement_scope/includes_special_teams/stat_correction_policy should remain UNKNOWN until book rules are verified.')
    return 0
if __name__=='__main__':raise SystemExit(main())

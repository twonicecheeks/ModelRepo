#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/game'))
import persistence

def main():
    rows=[]
    for t in range(10):
        team=f'T{t}'
        for w in range(1,8):
            rows.append({'game_id':f'{t}-{w}','season':2024,'week':w,'team':team,'x':t+w*.01,'off_turnover_rate':(w%3)*.01})
    a=persistence.lag1_persistence(rows,['x','off_turnover_rate'],max_season=2024)
    assert a['x']['pairs']>=20 and a['x']['researchPersistence']>0
    assert a['off_turnover_rate']['researchPersistence']<=.45
    print('PASS persistence tests')
if __name__=='__main__':main()

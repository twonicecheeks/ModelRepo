#!/usr/bin/env python3
from pathlib import Path
import csv,importlib.util,sys,tempfile

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/score_nfl_qb_passing_yards_slate_0242.py'
spec=importlib.util.spec_from_file_location('qb0242',p)
m=importlib.util.module_from_spec(spec);sys.modules['qb0242']=m;spec.loader.exec_module(m)

with tempfile.TemporaryDirectory() as td:
    fp=Path(td)/'m.csv'
    with fp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=m.REQUIRED);w.writeheader()
        w.writerow({'game_id':'2026_02_A_B','team':'A','qb_gsis_id':'00-001','qb_name':'QB A','identity_source':'USER_VERIFIED_EXTERNAL'})
    rows=m.read_manifest(fp)
    assert len(rows)==1 and rows[0]['qb_gsis_id']=='00-001'

with tempfile.TemporaryDirectory() as td:
    fp=Path(td)/'m.csv'
    with fp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=m.REQUIRED);w.writeheader()
        w.writerow({'game_id':'2026_02_A_B','team':'A','qb_gsis_id':'00-001','qb_name':'QB A','identity_source':'BAD'})
    try:m.read_manifest(fp)
    except ValueError:pass
    else:raise AssertionError('invalid identity source should fail')

print('PASS QB 0.2.4.2 verified-starter slate batch contracts')

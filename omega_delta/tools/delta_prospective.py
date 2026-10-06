"""Freeze a future-only 2026 DELTA cohort and audit saved pre-first-pitch rows.

The audit reads an existing OMEGA SQLite database. It cannot turn completed
games into prospective evidence, alter predictions, or authenticate book odds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core import canonical, stamp
from tools.run_delta_backtest import scores

ROOT = Path(__file__).resolve().parents[1]
CHECKED = ('audit/delta/FROZEN_MODEL.json','app/delta_model.py',
           'audit/mlb/FROZEN_MODEL.json','app/mlb_model.py')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(out, clock=None):
    target = Path(out).expanduser().resolve()
    if target.exists(): raise ValueError('The prospective freeze already exists; it cannot be overwritten.')
    frozen = json.loads((ROOT/CHECKED[0]).read_text())
    if frozen.get('season') != 2026 or '2026' not in frozen.get('folds', {}):
        raise ValueError('A frozen 2026 DELTA parameter fold is required.')
    instant = clock or datetime.now(timezone.utc)
    if instant.tzinfo is None: raise ValueError('Freeze clock must include timezone.')
    when = instant.astimezone(timezone.utc).isoformat()
    payload = {
        'status':'FUTURE_ONLY_UNSCORED','frozen_at':when,'eligible_after':when,
        'model_version':'delta-0.1.0','app_version':'2.1.3-delta.0.1.0',
        'season':2026,'training_seasons':frozen['folds']['2026']['training_seasons'],
        'parameter_sha256':hashlib.sha256(canonical(frozen['folds']['2026']).encode()).hexdigest(),
        'file_sha256':{name:digest(ROOT/name) for name in CHECKED},
        'selection_rule':'Latest locally received complete forecast after freeze and before first pitch, once per game and actual starter; no postgame feature updates.',
        'prediction_gate':'game start, captured timestamp and local receipt all after freeze/before first pitch; 2026 fold and frozen parameters match.',
        'markets':'No historical authenticated K entry/closing prices. ROI and CLV remain unmeasured.',
        'excluded':'All 2026 games with first pitch at or before the freeze; replay and previously inspected 2016–2025 games.',
        'model_promotion':False}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload,indent=2)+'\n')
    return payload


def audit(freeze_path, database):
    locked=json.loads(Path(freeze_path).read_text())
    for name, hash_value in locked['file_sha256'].items():
        if digest(ROOT/name)!=hash_value:
            raise ValueError(f'Frozen input changed: {name}')
    floor=stamp(locked['eligible_after']); excluded=Counter(); selected={}
    dbpath=Path(database).expanduser().resolve()
    if not dbpath.is_file(): raise ValueError('OMEGA database does not exist.')
    db=sqlite3.connect(f'file:{dbpath.as_posix()}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        for record in db.execute("SELECT id, raw, received_at FROM snapshots WHERE kind='mlb_forecast' ORDER BY rowid"):
            try:
                payload=json.loads(record['raw']); game=payload['game']
                start=stamp(game['start_at']); captured=stamp(game['captured_at']); received=stamp(record['received_at'])
                if start<=floor or captured<=floor or received<=floor or captured>=start or received>=start:
                    excluded['time_gate']+=1; continue
                if start.year != 2026 or int(game.get('season', 2026))!=2026:
                    excluded['not_2026']+=1; continue
                for d in game.get('forecast', {}).get('delta', []):
                    if d.get('model_version') != locked['model_version'] or d.get('parameters_sha256') != locked['parameter_sha256']:
                        excluded['model_mismatch']+=1; continue
                    key=(str(game['game_id']),str(d['player_id']))
                    if key not in selected or received>stamp(selected[key]['received_at']):
                        selected[key]={'game_id':key[0],'player_id':key[1],
                            'start_at':game['start_at'],'captured_at':game['captured_at'],
                            'received_at':record['received_at'],
                            'snapshot_id':record['id'],'forecast_k':d['pa']['expected_k'],
                            'pmf':d['pa']['pmf']}
            except (ValueError, KeyError, TypeError):
                excluded['invalid_snapshot']+=1
        grades={}
        setting=db.execute("SELECT payload FROM settings WHERE key='delta_grading'").fetchone()
        if setting:
            grading=json.loads(setting['payload'])
            for row in grading.get('rows', []):
                # Official grading verifies the actual starter and final K.
                # Its selected snapshot may differ from the receipt-time
                # prospective selection; the observed result is game-level.
                grades[(str(row['game_id']),str(row['player_id']))]=row['actual_k']
    finally:
        db.close()
    entries=[]
    for key, item in sorted(selected.items()):
        actual=grades.get(key)
        entries.append({**item,'actual_k':actual,'score':scores(actual,item['pmf']) if actual is not None else None})
    return {'status':'PROSPECTIVE_AUDIT_NO_PROMOTION','freeze_at':locked['frozen_at'],
            'eligible_forecasts':len(entries),'graded_forecasts':sum(e['score'] is not None for e in entries),
            'excluded':dict(excluded),'entries':entries,
            'note':'Grading uses official finals already recorded by OMEGA; missing outcomes stay pending. Quote authenticity and profit are not tested.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('freeze');a.add_argument('--out',required=True)
    a=sub.add_parser('audit');a.add_argument('--freeze',required=True);a.add_argument('--db',required=True);a.add_argument('--out',required=True)
    args=p.parse_args(argv)
    try:
        if args.command=='freeze': report=freeze(args.out)
        else:
            report=audit(args.freeze,args.db)
            out=Path(args.out).expanduser().resolve()
            if out.exists():raise ValueError('Audit output already exists; choose a new versioned path.')
            out.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report[k] for k in ('status','frozen_at') if k in report}|
                         ({'eligible_forecasts':report['eligible_forecasts']} if args.command=='audit' else {}),indent=2))
    except (ValueError,OSError,sqlite3.Error) as exc:p.exit(2,f'DELTA prospective error: {exc}\n')


if __name__=='__main__':main()

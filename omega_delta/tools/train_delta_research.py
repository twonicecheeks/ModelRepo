"""Fit prior-year DELTA discrete-hook or logit-residual research contracts.

Requires a separately assembled, timestamped PA-end risk set or pregame PA
feature table. Training never accepts a 2026 target. SciPy and NumPy are
optional training dependencies; OMEGA inference does not install them.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.delta_model import FEATURES, numeric

HOOK_FEATURES = ('bf','pitch_count','runs_allowed','strikeouts','leverage')


def when(raw):
    value=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timestamps require a timezone.')
    return value


def binary(value, name):
    if str(value) not in {'0','1'}: raise ValueError(f'{name} must be 0 or 1.')
    return int(value)


def load_rows(path, task, feature_names, cutoff):
    source=Path(path).expanduser().resolve(); rows=[]; games=defaultdict(list)
    boundary=when(cutoff)
    with source.open(newline='',encoding='utf-8-sig') as file:
        reader=csv.DictReader(file)
        required={'season','game_pk','game_start_at','state_at','pa_index',
                  'censored','target',*feature_names}
        if task=='residual': required.update(('baseline_logit','feature_observed_at'))
        if required-set(reader.fieldnames or []):
            raise ValueError(f'Incomplete {task} training table: {sorted(required-set(reader.fieldnames or []))}')
        for raw in reader:
            season_value=numeric(raw['season'],'season',2016,2025)
            if not season_value.is_integer(): raise ValueError('Season must be an integer.')
            season=int(season_value)
            start,state=when(raw['game_start_at']),when(raw['state_at'])
            if season!=start.year or start>=boundary or state>=boundary or state<start:
                raise ValueError('Only 2016–2025 games before the training cutoff are allowed.')
            index=int(numeric(raw['pa_index'],'PA index',1,100))
            if str(index)!=raw['pa_index'].strip(): raise ValueError('PA index must be integer.')
            target=binary(raw['target'],'target'); censored=binary(raw['censored'],'censored')
            if task=='residual' and censored:
                raise ValueError('Residual training cannot use censored PA outcomes.')
            x=[numeric(raw[name],name,-1e5,1e5) for name in feature_names]
            offset=numeric(raw['baseline_logit'],'baseline logit',-20,20) if task=='residual' else 0.
            if task=='residual' and not (start > when(raw.get('feature_observed_at'))):
                raise ValueError('Residual features must have a pre-first-pitch observation time.')
            if task=='hook' and not (state>start):
                raise ValueError('A hook risk state must follow first pitch.')
            if task=='hook' and x[0]!=index:
                raise ValueError('End-of-PA BF must equal the sequential PA index.')
            if censored and target: raise ValueError('Censored PA cannot also be a hook event.')
            item=(season,raw['game_pk'],index,x,target,censored,offset,state)
            games[(season,raw['game_pk'])].append(item)
            rows.append(item)
    if task=='hook':
        for key,events in games.items():
            indices=[r[2] for r in events]
            if indices!=list(range(1,len(indices)+1)):
                raise ValueError(f'Hook risk set for {key} is not a complete PA sequence.')
            labels=[r[4]+r[5] for r in events]
            if labels[-1]!=1 or any(labels[:-1]):
                raise ValueError(f'Hook risk set for {key} must end at exactly one removal or censoring.')
            for a,b in zip(events,events[1:]):
                if b[7] < a[7]:
                    raise ValueError('End-of-PA observations must follow chronological order.')
                if b[3][0] < a[3][0] or b[3][1] < a[3][1] or b[3][2] < a[3][2]:
                    raise ValueError('BF, pitch count and runs allowed cannot decrease within a start.')
    # A right-censored final PA contributes an observed no-removal risk interval.
    # Its unknown subsequent outcome is never manufactured as a training row.
    if len(rows)<40 or len(games)<3 or len({r[4] for r in rows})<2:
        raise ValueError('Need at least 40 observed PAs, three games, and both outcomes.')
    return rows, {'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                    'rows':len(rows),'risk_games':len(games),'right_censored_games':sum(r[5] for r in rows),
                    'earliest_season':min(r[0] for r in rows),'latest_season':max(r[0] for r in rows)}


def fit(rows, features, penalty):
    try:
        import numpy as np
        from scipy.optimize import minimize
        from scipy.special import expit
    except ImportError as exc:
        raise ValueError('Training needs optional NumPy and SciPy in a separate Python environment.') from exc
    reg=numeric(penalty,'ridge penalty',.000001,1000)
    x=np.asarray([r[3] for r in rows],dtype=float); y=np.asarray([r[4] for r in rows],dtype=float)
    offset=np.asarray([r[6] for r in rows],dtype=float)
    center=x.mean(axis=0);scale=x.std(axis=0);scale=np.where(scale>1e-9,scale,1.)
    x=(x-center)/scale
    matrix=np.column_stack((np.ones(len(x)),x))
    def objective(weights):
        z=offset+matrix@weights
        loss=np.logaddexp(0,z).mean()-np.mean(y*z)+reg*(weights[1:]@weights[1:])/2
        grad=matrix.T@(expit(z)-y)/len(y)
        grad[1:]+=reg*weights[1:]
        return loss,grad
    result=minimize(objective,np.zeros(matrix.shape[1]),jac=True,method='L-BFGS-B',
                    options={'maxiter':1000,'ftol':1e-12})
    if not result.success: raise ValueError(f'Ridge logit fit did not converge: {result.message}')
    return {'intercept':float(result.x[0]),
            'coefficients':dict(zip(features,map(float,result.x[1:]))),
            'reference':dict(zip(features,map(float,center))),
            'scale':dict(zip(features,map(float,scale))),
            'training_log_loss_penalized':float(result.fun),
            'ridge_penalty':reg,'training_pa':len(rows),
            'events':int(y.sum())}


def train(task,path,feature_names,cutoff,penalty,source):
    if not source.strip(): raise ValueError('An explicit historical data source is required.')
    allowed=set(HOOK_FEATURES if task=='hook' else FEATURES)
    if not feature_names or len(set(feature_names))!=len(feature_names) or set(feature_names)-allowed:
        raise ValueError('Choose distinct supported feature names.')
    if task=='hook' and feature_names[:3]!=list(HOOK_FEATURES[:3]):
        raise ValueError('Hook training requires bf,pitch_count,runs_allowed first.')
    rows,coverage=load_rows(path,task,feature_names,cutoff)
    model=fit(rows,feature_names,penalty)
    model.update({'status':'UNVALIDATED_RESEARCH_NO_PROMOTION','kind':'discrete_end_pa_hook' if task=='hook' else 'pa_logit_residual',
                  'source':source,'training_end_at':cutoff,'coverage':coverage,
                  'cutoff_rule':'Historical prior-season input only; 2026 outcomes prohibited. Input feature time must precede decision.',
                  'requires':'Independent season-wise log loss and calibration comparison before use in a live forecast.'})
    return model


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task',choices=['hook','residual'],required=True)
    p.add_argument('--csv',required=True)
    p.add_argument('--features',required=True,help='Comma-separated supported names; hook starts bf,pitch_count,runs_allowed')
    p.add_argument('--training-end-before',default='2026-01-01T00:00:00Z')
    p.add_argument('--ridge',type=float,default=.01)
    p.add_argument('--source',required=True)
    p.add_argument('--out',required=True)
    args=p.parse_args(argv)
    try:
        output=Path(args.out).expanduser().resolve()
        if output.exists():raise ValueError('Research model output already exists.')
        model=train(args.task,args.csv,args.features.split(','),args.training_end_before,args.ridge,args.source)
        output.write_text(json.dumps(model,indent=2)+'\n')
        print(json.dumps({'status':model['status'],'kind':model['kind'],
                          'training_pa':model['training_pa'],'events':model['events'],'out':str(output)},indent=2))
    except (OSError,ValueError) as exc:p.exit(2,f'DELTA trainer error: {exc}\n')


if __name__=='__main__':main()

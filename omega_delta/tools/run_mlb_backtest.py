"""Reproduce OMEGA V2's chronological playoff development backtest offline.

Python standard library + Node >=18. No paid API requests. Inputs and outcome
targets travel separately to the inference engines. Evidence is not promotion.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import subprocess
import sys
from datetime import datetime,timezone
from collections import defaultdict
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.mlb_model import (usage_factor, fit_calibration, exposure_ml, postseason_k,
                           logistic, logit, k_pmf, strip_targets)


def readl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def metrics(rows, pkey, kind):
    if not rows: return {'n': 0}
    if kind == 'ML':
        e = [r[pkey]-r['actual_win'] for r in rows]
        ll = [-math.log(max(1e-12,r[pkey] if r['actual_win'] else 1-r[pkey])) for r in rows]
        bins = []
        for lower in [0.,.1,.2,.3,.4,.5,.6,.7,.8,.9]:
            rs = [r for r in rows if min(9,int(r[pkey]*10)) == int(round(lower*10))]
            if rs: bins.append({'lower':lower,'n':len(rs),'mean_probability':fmean(r[pkey] for r in rs),'win_rate':fmean(r['actual_win'] for r in rs)})
        return {'n': len(e), 'brier': fmean(x*x for x in e), 'log_loss':fmean(ll),
                'bias': fmean(e),'accuracy':fmean((r[pkey]>=.5)==bool(r['actual_win']) for r in rows), 'calibration_bins': bins}
    e = [r[pkey]-r['actual_k'] for r in rows]
    ll, rps = [], []
    for r in rows:
        pmf = k_pmf(r[pkey], r.get('uncertainty_multiplier',1))
        actual = int(r['actual_k'])
        ll.append(-math.log(max(1e-12,pmf[actual])))
        cdf, score = 0., 0.
        for k,p in enumerate(pmf):
            cdf += p; score += (cdf-(1. if actual<=k else 0.))**2
        rps.append(score)
    return {'n':len(e),'mae':fmean(abs(x) for x in e),'rmse':math.sqrt(fmean(x*x for x in e)),
            'bias':fmean(e),'log_loss':fmean(ll),'ranked_probability_score':fmean(rps)}


def cluster_ci(rows, values, cluster='series', reps=2000):
    """Paired resampling of whole series/seasons, retaining correlated starts."""
    grouped = defaultdict(list)
    for r,v in zip(rows, values): grouped[str(r[cluster])].append(v)
    groups = [(sum(v),len(v)) for v in grouped.values()]
    if len(groups)<2: return None
    rng = random.Random(300926)
    boot=[]
    for _ in range(reps):
        chosen = rng.choices(groups,k=len(groups))
        boot.append(sum(x[0] for x in chosen)/sum(x[1] for x in chosen))
    boot.sort()
    return [boot[int(.025*(reps-1))], boot[int(.975*(reps-1))]]


def compare(rows, a, b, kind):
    am,bm=metrics(rows,a,kind),metrics(rows,b,kind)
    out={'baseline':am,'challenger':bm,'paired_n':len(rows)}
    measures=['brier','log_loss'] if kind=='ML' else ['mae','log_loss','ranked_probability_score']
    changes={}
    for measure in measures:
        vals=[]
        for r in rows:
            ma=metrics([r],a,kind)[measure]; mb=metrics([r],b,kind)[measure]
            vals.append(mb-ma)
        changes[measure]={'delta':fmean(vals) if vals else None,
                         'series_ci95':cluster_ci(rows,vals),'season_ci95':cluster_ci(rows,vals,'season')}
    out['challenger_minus_baseline']=changes
    return out


def run(output, reproject=True):
    seed=ROOT/'seed/mlb'
    inputs=readl(seed/'REPRODUCTION_INPUTS.jsonl')
    baseline=readl(seed/'BASELINE_LEDGER.jsonl')
    outcomes=readl(seed/'OUTCOMES.jsonl')
    pairs=json.loads((seed/'USAGE_PAIRS.json').read_text())
    manifest=json.loads((seed/'REPLAY_MANIFEST.json').read_text())
    archive_audit=json.loads((seed/'MARKET_ARCHIVE_AUDIT.json').read_text())
    if reproject:
        proc=subprocess.run(['node',str(ROOT/'tools/mlb_project.cjs')], input=json.dumps([strip_targets(r) for r in inputs]),text=True,capture_output=True,check=True,timeout=120)
        projections=json.loads(proc.stdout)
        for r,b,p in zip(inputs,baseline,projections):
            expected=b['model_probability'] if r['replay_type']=='ML' else b['xk']
            actual=p['base']['homeWin'] if r['replay_type']=='ML' else p['base']['expectedK']
            if abs(expected-actual)>1e-10: raise ValueError('Recovered engine reproduction differs from baseline')
    else:
        projections=[{'base':b['ml_projection'] if b['market_type']=='ML' else b['k_projection']} for b in baseline]
    targets={r['game_id']:r for r in outcomes}
    bygame={r['game_id']:r for r in inputs if r['replay_type']=='ML'}
    ml,krows=[],[]
    for r,b,p in zip(inputs,baseline,projections):
        game=targets[r['game_id']]
        series=f"{r['season']}:{game['game_type']}:"+':'.join(sorted(str(game[s]['team_id']) for s in ['away','home']))
        common={'game_id':r['game_id'],'season':r['season'],'game_date':r['game_date'],'series':series}
        f=usage_factor(pairs,r['season'])
        if r['replay_type']=='ML':
            workloads={s:dict(r['production_input']['starters'][r['production_input'][s]]['workload'],regular_starts=b[s+'_workload_proxy_source']=='REGULAR_SEASON_STARTS') for s in ['away','home']}
            proj=exposure_ml(p['base'],workloads,f['factor'])
            ml.append({**common,'home':r['production_input']['home'],'away':r['production_input']['away'],
                       'actual_win':r['actual_home_win'],'baseline_probability':p['base']['homeWin'],
                       'exposure_probability':proj['home_probability'],'exposure':proj,'usage_training':f})
        else:
            if f['status']!='READY' or b['workload_proxy_source']!='REGULAR_SEASON_STARTS': continue
            proj=postseason_k(p['base'],f['factor'])
            krows.append({**common,'pitcher':b['pitcher'],'player_id':str(r['starter_input']['officialMlbId']),
                          'actual_k':r['actual_k'],'baseline_k':p['base']['expectedK'],
                          'postseason_k':proj['expected_k'],'uncertainty_multiplier':proj['uncertainty_multiplier'],
                          'usage_training':f})
    recal=[]
    for row in ml:
        c=fit_calibration(ml,row['season'])
        if c['status']=='READY':
            row['calibrated_probability']=logistic(c['intercept']+c['slope']*logit(row['exposure_probability']))
            row['calibration_training']=c; recal.append(row)
    report={'version':'2.0.0','protocol':json.loads((ROOT/'V2_RESEARCH_PROTOCOL.json').read_text()),
            'status':'EDGE_NOT_VERIFIED','evidence_label':'EXPLORATORY_CHRONOLOGICAL_REPLAY',
            'coverage':{'official_games':len(outcomes),'projected_games':len(ml),'blocked_games':manifest['blocked_games'],
                        'baseline_k_rows':sum(b['market_type']=='K' for b in baseline),'paired_k_rows':len(krows),
                        'paired_calibrated_ml_games':len(recal),'blocked':manifest['blocked']},
            'moneyline_exposure':compare(ml,'baseline_probability','exposure_probability','ML'),
            'moneyline_calibrated':compare(recal,'baseline_probability','calibrated_probability','ML'),
            'strikeouts':compare(krows,'baseline_k','postseason_k','K'),
            'market_archive_audit':archive_audit,
            'market_evidence':{'accepted_pregame_moneyline_prices':0,'accepted_pregame_k_prices':0,
                               'roi':None,'clv':None,'model_vs_market':None},
            'verification_gates':{'historical_replay_reproduced':True,'no_same_season_parameter_fit':True,
                'authentic_timestamped_entry_prices':False,'at_least_100_wagers_3_seasons':False,
                'positive_series_cluster_roi_lower_bound':False,'beats_market_probability_scores':False,
                'independent_confirmation_after_model_selection':False},
            'limitations':['2015–2025 was already consumed in prior mechanism research; this is development evidence.',
                'Historical workload is reconstructed from regular-season logs, rather than captured current-game supporting markets.',
                'Historical starting lineups come from completed boxscore identities, rather than timestamped pregame captures.',
                'Season-end public skill and park data is reconstructed; release has no original timestamped feature receipts.',
                'No accepted historical K line/price pairs or executable moneyline entry snapshots; profitability and CLV remain unmeasured.',
                'No multiple-comparison promotion: all fixed challengers and cohorts are reported.'],
            'cohorts':{},'per_season':{},'bootstrap':{'seed':300926,'reps':2000,'clusters':['playoff series','season']},
            'input_hashes':{p.name:sha(p) for p in seed.iterdir() if p.is_file()}}
    for name,predicate in [('all',lambda r:True),('exclude_2020',lambda r:r['season']!=2020),('2020_only',lambda r:r['season']==2020),('2022_plus',lambda r:r['season']>=2022)]:
        km=[r for r in krows if predicate(r)]; mm=[r for r in recal if predicate(r)]
        report['cohorts'][name]={'strikeouts':compare(km,'baseline_k','postseason_k','K'),'moneyline':compare(mm,'baseline_probability','calibrated_probability','ML')}
    for year in range(2015,2026):
        km=[r for r in krows if r['season']==year]; mm=[r for r in recal if r['season']==year]
        report['per_season'][str(year)]={'usage_training':usage_factor(pairs,year),
            'strikeouts':{'baseline':metrics(km,'baseline_k','K'),'challenger':metrics(km,'postseason_k','K')},
            'moneyline':{'baseline':metrics(mm,'baseline_probability','ML'),'challenger':metrics(mm,'calibrated_probability','ML')}}
    frozen_at=datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    frozen={'model_version':'omega-mlb-playoff-2.0.0','season':2026,'status':'RESEARCH_EDGE_UNVERIFIED',
            'usage':usage_factor(pairs,2026),'calibration':fit_calibration(ml,2026),
            'protocol_sha256':sha(ROOT/'V2_RESEARCH_PROTOCOL.json'),'training_targets_through':2025,
            'created_at':frozen_at,'effective_from_utc':frozen_at}
    write(output/'BACKTEST_REPORT.json',report);write(output/'FROZEN_MODEL.json',frozen)
    (output/'PREDICTIONS.jsonl').write_text('\n'.join(json.dumps(r,allow_nan=False) for r in ml+krows)+'\n')
    print(json.dumps({'status':report['status'],'coverage':{k:v for k,v in report['coverage'].items() if k!='blocked'},
        'strikeouts':report['strikeouts'],'moneyline_calibrated':report['moneyline_calibrated'],'frozen_model':frozen},indent=2))
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'audit/mlb')
    args=ap.parse_args();run(args.output)

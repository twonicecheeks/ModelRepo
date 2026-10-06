"""Reproduce DELTA's PA development comparison using V2's actual sealed inputs.

No source download, sportsbook call, production mutation, or profit simulation.
The missing advanced-feature histories are not substituted with invented data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.delta_model import VERSION, fit_parameters, forecast
from app.mlb_model import usage_factor, postseason_k, k_pmf
from tools.run_mlb_backtest import cluster_ci


def readl(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n')


def scores(actual, pmf):
    mean = sum(i*p for i, p in enumerate(pmf))
    error = mean-actual
    logloss = -math.log(max(1e-12, pmf[actual] if actual < len(pmf) else 0))
    cdf = 0.; rps = 0.
    for k in range(max(len(pmf), actual+2)):
        cdf += pmf[k] if k < len(pmf) else 0
        rps += (cdf-(1 if actual <= k else 0))**2
    return {'expected_k': mean, 'error': error, 'absolute_error': abs(error),
            'square_error': error**2, 'log_loss': logloss, 'rps': rps}


def aggregate(rows, model):
    values = [r['metrics'][model] for r in rows]
    if not values: return {'n': 0}
    return {'n': len(values), 'mae': fmean(v['absolute_error'] for v in values),
            'rmse': math.sqrt(fmean(v['square_error'] for v in values)),
            'bias': fmean(v['error'] for v in values),
            'log_loss': fmean(v['log_loss'] for v in values),
            'ranked_probability_score': fmean(v['rps'] for v in values)}


def compare(rows, model):
    result = {}
    for key in ['absolute_error', 'log_loss', 'rps']:
        values = [r['metrics'][model][key]-r['metrics']['v2'][key] for r in rows]
        result[key] = {'delta': fmean(values), 'series_ci95': cluster_ci(rows, values),
                       'season_ci95': cluster_ci(rows, values, 'season')}
    return result


def run(output):
    seed = ROOT/'seed/mlb'
    inputs = readl(seed/'REPRODUCTION_INPUTS.jsonl')
    baseline = readl(seed/'BASELINE_LEDGER.jsonl')
    outcomes = {r['game_id']: r for r in readl(seed/'OUTCOMES.jsonl')}
    usage = json.loads((seed/'USAGE_PAIRS.json').read_text())
    training, predictions, blocked = [], [], []
    for row, base in zip(inputs, baseline):
        if row['replay_type'] != 'K' or base['workload_proxy_source'] != 'REGULAR_SEASON_STARTS': continue
        game = outcomes[row['game_id']]
        pid = str(row['starter_input']['officialMlbId'])
        actual = next((game[s]['starter'] for s in ['away', 'home']
                       if str(game[s]['starter']['mlb_id']) == pid), None)
        if actual is None or actual.get('batters_faced') is None:
            blocked.append({'game_id': row['game_id'], 'player_id': pid, 'reason': 'Actual BF missing'}); continue
        n, k = actual['batters_faced'], actual['strikeouts']
        if not isinstance(n, int) or not isinstance(k, int) or not 0 <= k <= n <= 100:
            raise ValueError('Official BF/K target invalid.')
        u = usage_factor(usage, row['season'])
        v2 = postseason_k(base['k_projection'], u['factor'])
        training.append({'input': row, 'v2': v2, 'actual_bf': n, 'actual_k': k,
                         'season': row['season'], 'base': base,
                         'series': f"{row['season']}:{game['game_type']}:"+':'.join(sorted(str(game[s]['team_id']) for s in ['away', 'home']))})
    folds = {}
    for year in range(2015, 2027):
        folds[str(year)] = fit_parameters(training, year)
    for r in training:
        if r['season'] == 2015: continue
        row, params = r['input'], folds[str(r['season'])]
        d = forecast(row, r['v2'], params)
        variants = {'baseline': k_pmf(r['base']['xk'], r['v2']['uncertainty_multiplier']),
                    'v2': k_pmf(r['v2']['expected_k'], r['v2']['uncertainty_multiplier']),
                    'delta_pa': d['pa']['pmf'], 'delta_beta': d['beta_binomial']['pmf']}
        predictions.append({'game_id': row['game_id'], 'player_id': d['player_id'], 'player': d['player'],
                            'game_date': row['game_date'], 'season': r['season'], 'series': r['series'],
                            'actual_k': r['actual_k'], 'actual_bf': r['actual_bf'],
                            'expected_bf': d['expected_bf'], 'training_n': params['training_n'],
                            'training_seasons': params['training_seasons'],
                            'beta_concentration': params['beta_concentration'],
                            # Retain the exact distributions so a later
                            # market audit can score the saved model instead
                            # of rebuilding a different PMF from its mean.
                            'pmfs': variants,
                            'metrics': {name: scores(r['actual_k'], pmf) for name, pmf in variants.items()}})
    models = ['baseline', 'v2', 'delta_pa', 'delta_beta']
    limitations = [
        'Previously inspected 2015–2025 postseason data: chronological development replay, not independent confirmation.',
        'Reconstructed season-end skill and completed-game starting orders; original pregame feature receipts unavailable.',
        'Starting-order repetition approximates PA identities; historical substitutions are not reconstructed.',
        'No historical pitch/count, Stuff+/PitchingBot, platoon, umpire, weather, manager hazard, or familiarity feature replay.',
        'Workload residuals are fit on earlier-season BF only and centered to preserve V2 expected BF; endogenous K/hook dependence is unfit.',
        'Beta concentration is selected on prior seasons only from the declared 5/20/100/500/5000 grid.',
        'No authenticated entry quotes or tickets: ROI, CLV, market outperformance, and betting edge are unmeasured.',
    ]
    report = {'model_version': VERSION, 'status': 'DEVELOPMENT_REPLAY_ONLY',
              'created_at': datetime.now(timezone.utc).isoformat(),
              'coverage': {'paired_starts': len(predictions), 'training_rows': len(training), 'blocked': blocked,
                           'test_seasons': sorted({r['season'] for r in predictions})},
              'models': {name: aggregate(predictions, name) for name in models},
              'delta_minus_v2': {name: compare(predictions, name) for name in ['delta_pa', 'delta_beta']},
              'per_season': {str(y): {name: aggregate([r for r in predictions if r['season'] == y], name) for name in models}
                             for y in sorted({r['season'] for r in predictions})},
              'sensitivities': {label: {name: aggregate([r for r in predictions if predicate(r)], name) for name in models}
                                for label, predicate in [('without_2020', lambda r: r['season'] != 2020),
                                                        ('2022_onward', lambda r: r['season'] >= 2022)]},
              'advanced_feature_validation': 'NOT_RUN_MISSING_HISTORICAL_INPUTS',
              'market_evidence': {'roi': None, 'clv': None, 'edge_verified': False},
              'limitations': limitations,
              'source_sha256': {name: hashlib.sha256((seed/name).read_bytes()).hexdigest() for name in
                                ['REPRODUCTION_INPUTS.jsonl', 'BASELINE_LEDGER.jsonl', 'OUTCOMES.jsonl', 'USAGE_PAIRS.json']}}
    report['engine_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                             ['app/delta_model.py','app/mlb_model.py','models/mlb/k/structured_k_core.js']}
    frozen = {'model_version': VERSION, 'season': 2026, 'status': 'RESEARCH_FROZEN',
              'frozen_at': report['created_at'], 'source_sha256': report['source_sha256'],
              'engine_sha256':report['engine_sha256'],
              'folds': folds, 'parameters': folds['2026'], 'limitations': limitations,
              'default_variant': 'delta_pa', 'automatic_promotion': False, 'target_k_market_weight': 0}
    write(output/'BACKTEST_REPORT.json', report); write(output/'FROZEN_MODEL.json', frozen)
    (output/'PREDICTIONS.jsonl').write_text(''.join(json.dumps(r, separators=(',', ':'), allow_nan=False)+'\n' for r in predictions))
    print(json.dumps({'coverage': report['coverage'], 'models': report['models'], 'status': report['status']}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, default=ROOT/'audit/delta')
    run(parser.parse_args().output)

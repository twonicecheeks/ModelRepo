"""Score proposed fixed October boosts and 19-BF caps on sealed development rows.

This is a deliberately unpromoted counterfactual. The held-out seasons have
already been inspected; results cannot establish a future betting edge.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.delta_model import hitter_rates, workload_pmf, count_distributions
from app.mlb_model import usage_factor, postseason_k
from tools.run_delta_backtest import scores


def readl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summary(items):
    return {'n': len(items), 'mae': fmean(x['absolute_error'] for x in items),
            'rmse': math.sqrt(fmean(x['square_error'] for x in items)),
            'bias': fmean(x['error'] for x in items),
            'log_loss': fmean(x['log_loss'] for x in items),
            'ranked_probability_score': fmean(x['rps'] for x in items)}


def run():
    seed = ROOT/'seed/mlb'
    inputs, baseline = readl(seed/'REPRODUCTION_INPUTS.jsonl'), readl(seed/'BASELINE_LEDGER.jsonl')
    usage = json.loads((seed/'USAGE_PAIRS.json').read_text())
    frozen = json.loads((ROOT/'audit/delta/FROZEN_MODEL.json').read_text())
    saved = {(r['game_id'],r['player_id']):r for r in readl(ROOT/'audit/delta/PREDICTIONS.jsonl')}
    actual_bf = [row['actual_bf'] for row in saved.values()]
    outcomes = defaultdict(list)
    for row, base in zip(inputs, baseline):
        if row['replay_type'] != 'K' or base['workload_proxy_source'] != 'REGULAR_SEASON_STARTS':
            continue
        pid = str(row['starter_input']['officialMlbId'])
        actual = saved.get((row['game_id'],pid))
        if actual is None:
            continue
        params = frozen['folds'][str(row['season'])]
        v2 = postseason_k(base['k_projection'],usage_factor(usage,row['season'])['factor'])
        rates = hitter_rates(row,params)
        bf = workload_pmf(v2['expected_bf'],params)
        capped = defaultdict(float)
        for n, weight in bf.items():
            capped[min(n,19)] += weight
        boosted = [dict(h,k_probability=min(h['k_probability']*1.04,.95)) for h in rates]
        variants = {'delta_unchanged': (rates,bf), 'boost_1_04': (boosted,bf),
                    'bf_cap_19': (rates,capped), 'boost_and_cap': (boosted,capped)}
        for name, (probabilities, workload) in variants.items():
            pmf = count_distributions(probabilities,workload,params['beta_concentration'])['pa']
            outcomes[name].append(scores(actual['actual_k'],pmf))
    if any(len(rows)!=len(saved) for rows in outcomes.values()):
        raise ValueError('Counterfactual did not score every sealed DELTA prediction.')
    result = {'status': 'DEVELOPMENT_COUNTERFACTUAL_DO_NOT_PROMOTE',
              'model_version': frozen['model_version'], 'n': len(saved),
              'hypotheses': {'boost':'Multiply each individual PA probability by 1.04, then cap at 0.95.',
                             'cap':'For each workload atom, replace BF with min(BF,19).'},
              'actual_bf': {'over_18':sum(n>18 for n in actual_bf),
                            'over_19':sum(n>19 for n in actual_bf),
                            'over_27':sum(n>27 for n in actual_bf),
                            'maximum':max(actual_bf)},
              'reference_v2':json.loads((ROOT/'audit/delta/BACKTEST_REPORT.json').read_text())['models']['v2'],
              'models':{name:summary(items) for name,items in outcomes.items()},
              'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in [seed/'REPRODUCTION_INPUTS.jsonl',seed/'BASELINE_LEDGER.jsonl',
                                            seed/'USAGE_PAIRS.json',ROOT/'audit/delta/FROZEN_MODEL.json',
                                            ROOT/'audit/delta/PREDICTIONS.jsonl']},
              'limitations':['Previously inspected postseason replay, not a prospective test.',
                             'No pregame quote, manager plan, umpire assignment or weather observation used.',
                             'A hard BF cap cannot represent official workloads above 19.']}
    original = json.loads((ROOT/'audit/delta/BACKTEST_REPORT.json').read_text())['models']['delta_pa']
    for key in ['mae','rmse','bias','log_loss','ranked_probability_score']:
        if abs(result['models']['delta_unchanged'][key]-original[key])>1e-8:
            raise ValueError('Sealed DELTA comparison did not reproduce.')
    target = ROOT/'audit/delta/POSTSEASON_ESCALATOR_EXPERIMENT.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'n':result['n'],
                      'actual_bf':result['actual_bf'],'reference_v2':result['reference_v2'],
                      'models':result['models']},indent=2))
    return result


if __name__ == '__main__':
    run()

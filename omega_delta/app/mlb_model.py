"""OMEGA V2 postseason candidates. Pure functions; prices/outcomes are not inputs.

The recovered structured engines supply regular-season skill and workload.
This layer changes exposure and calibrates moneyline probabilities using frozen
earlier-season parameters. All candidates remain research until market gates pass.
"""
from __future__ import annotations
import copy
import math
from statistics import median

MODEL_VERSION = 'omega-mlb-playoff-2.0.0'


def clamp(x, lo, hi):
    return max(lo, min(hi, float(x)))


def logistic(x):
    return 1 / (1 + math.exp(-clamp(x, -35, 35)))


def logit(p):
    p = clamp(p, 1e-6, 1-1e-6)
    return math.log(p / (1-p))


def usage_factor(pairs, test_season):
    prior = [r for r in pairs if int(r['season']) < int(test_season)]
    return {'factor': median(r['outs_ratio'] for r in prior) if prior else 1.,
            'training_seasons': sorted({int(r['season']) for r in prior}),
            'training_pitcher_seasons': len(prior),
            'status': 'READY' if prior else 'WARMUP'}


def fit_calibration(rows, test_season):
    """Ridge logistic intercept + slope, with prior (0,1), lambda=1.

    Select training years here, rather than relying on a caller to remove test data.
    No market data is read. Newton updates fit two coefficients deterministically.
    """
    prior = [r for r in rows if int(r['season']) < int(test_season)]
    a, b = 0., 1.
    if len(prior) >= 60:
        for _ in range(80):
            ga, gb, haa, hab, hbb = a, b-1., 1., 0., 1.
            for r in prior:
                x, y = logit(r['exposure_probability']), float(r['actual_win'])
                p = logistic(a+b*x)
                w = p*(1-p)
                ga += p-y; gb += (p-y)*x
                haa += w; hab += w*x; hbb += w*x*x
            det = haa*hbb-hab*hab
            da, db = (ga*hbb-gb*hab)/det, (gb*haa-ga*hab)/det
            a -= da; b -= db
            if max(abs(da), abs(db)) < 1e-9: break
    return {'intercept': a, 'slope': b, 'ridge_lambda': 1., 'training_games': len(prior),
            'training_seasons': sorted({int(r['season']) for r in prior}),
            'status': 'READY' if len(prior) >= 60 else 'WARMUP'}


def exposure_ml(base, workloads, factor):
    """Reconstruct run components with the requested IP; permit short starts.

    workloads keys away/home refer to pitchers; run components refer to offenses.
    A current-game market or explicit manager plan already anchors the leash.
    """
    runs, ips, applied = {}, {}, {}
    for offense, pitcher in [('away','home'), ('home','away')]:
        c = base[offense+'RunComponents']
        w = workloads[pitcher]
        mode = w.get('state')
        if mode not in {'HISTORY_PROXY','CURRENT_GAME_MARKET_ANCHORED','MANAGER_PLAN'}:
            raise ValueError('Workload state must be explicit.')
        adjust = mode == 'HISTORY_PROXY' and w.get('regular_starts', True)
        ip = clamp(float(w['IP']) * (factor if adjust else 1.), 0., 7.8333333333)
        ips[pitcher] = ip; applied[pitcher] = adjust
        raw = (float(c['starterR9'])*ip + float(c['bullpenR9'])*(9-ip))/9
        runs[offense] = clamp(raw*float(c['parkFactor'])+float(c['homeFieldRuns']), 1.8, 7.5)
    p = logistic((runs['home']-runs['away'])/1.60)
    return {'home_probability': p, 'away_probability': 1-p, 'away_runs': runs['away'],
            'home_runs': runs['home'], 'starter_ip': ips, 'usage_factor_applied': applied}


def postseason_k(distribution, factor, mode='HISTORY_PROXY', regular_starts=True):
    if mode not in {'HISTORY_PROXY','CURRENT_GAME_MARKET_ANCHORED','MANAGER_PLAN'}:
        raise ValueError('Workload state must be explicit.')
    c = distribution['components']
    apply = mode == 'HISTORY_PROXY' and regular_starts
    outs = clamp(c['expectedOuts'] * (factor if apply else 1.), 3., 23.5)
    opener = bool(distribution.get('openerLike'))
    bf = clamp(outs+c['expectedHits']+c['expectedWalks']+.30, 3.5 if opener else 10., 14. if opener else 33.)
    structural = bf * c['matchupK']/100
    weights = c['blendWeights']
    xk = weights.get('structural',0)*structural
    for key, field in [('recent','recentK'),('season','seasonK')]:
        if weights.get(key,0): xk += weights[key]*c[field]
    ceiling = max(.5, min(18., bf*.75))
    return {'expected_k': clamp(xk, .15, ceiling), 'expected_outs': outs,
            'expected_bf': bf, 'usage_factor_applied': apply,
            'uncertainty_multiplier': distribution.get('uncertaintyMultiplier',1),
            'player': distribution.get('player'), 'player_id': str(distribution.get('officialMlbId',''))}


def k_pmf(mu, uncertainty=1, max_k=80):
    d = .18 * clamp(uncertainty, 1., 1.7)
    result = [0.] * (max_k+1)
    for scale, weight in zip([1-d,1-d/2,1,1+d/2,1+d],[.08,.22,.40,.22,.08]):
        lam = max(.05, mu*scale)
        term = math.exp(-lam)
        for k in range(max_k+1):
            if k: term *= lam/k
            result[k] += weight*term
    return result


def k_probabilities(mu, line, uncertainty=1):
    line = float(line)
    if line < 0 or line > 40: raise ValueError('K line must be between 0 and 40.')
    if not math.isfinite(line) or not (line*2).is_integer():raise ValueError('Use a whole or half strikeout line.')
    pmf = k_pmf(mu, uncertainty)
    over = sum(p for k,p in enumerate(pmf) if k > line)
    under = sum(p for k,p in enumerate(pmf) if k < line)
    push = pmf[int(line)] if line.is_integer() else 0.
    return {'over': over, 'under': under, 'push': push}


def decimal_odds(american):
    o = float(american)
    if not math.isfinite(o) or abs(o) < 100 or abs(o) > 100000:
        raise ValueError('Use valid American odds, such as -110 or +125.')
    return 1 + (o/100 if o > 0 else 100/abs(o))


def quote_ev(pwin, ppush, american):
    return pwin*(decimal_odds(american)-1)-(1-pwin-ppush)


def fair_odds(pwin, ppush=0.):
    if pwin<=0 or pwin>=1-ppush:return None
    p = pwin/(1-ppush)
    return round(-100*p/(1-p)) if p >= .5 else round(100*(1-p)/p)


def settle(selection, actual, line, american):
    if selection == 'ML': won, push = bool(actual), False
    elif selection in {'OVER','UNDER'}:
        push = float(actual) == float(line)
        won = float(actual) > float(line) if selection == 'OVER' else float(actual) < float(line)
    else: raise ValueError('Unknown selection.')
    return 0. if push else decimal_odds(american)-1 if won else -1.


def strip_targets(row):
    clean = copy.deepcopy(row)
    for key in list(clean):
        if key.startswith('actual_') or key in {'market_odds','closing_odds','book','opening_odds'}:
            clean.pop(key)
    return clean

"""DELTA 0.1: finite plate-appearance distributions, with optional pitch inputs.

The neutral path is a chronological research challenger. Imported physical,
count and manager models remain sourced research inputs, not validated weights.
Target K prices, actuals, and closing prices are never forecast inputs.
"""
from __future__ import annotations

import math
import random
from statistics import fmean

VERSION = 'delta-0.1.0'
LEAGUE_K = .225  # Declared legacy prior; not a measured postseason escalator.
MAX_BF = 100
FEATURES = (
    'stuff_plus', 'pitchingbot_stuff', 'location_plus', 'command_plus',
    'csw_pct', 'whiff_pct', 'chase_pct', 'velocity', 'vertical_break',
    'horizontal_break', 'release_height', 'extension', 'arsenal_whiff_pct',
    'arsenal_chase_pct', 'arsenal_run_value_per100', 'umpire_called_strike_residual',
    'temperature_f', 'wind_mph', 'air_density', 'park_k_factor',
    'familiarity_pa', 'series_game', 'elimination_game', 'bullpen_available',
    'rest_days', 'velocity_change', 'postseason_environment',
)


def numeric(value, name='number', lo=-1e6, hi=1e6):
    if value is None or isinstance(value, bool) or str(value).strip() == '':
        raise ValueError(f'{name} is required; missing is not zero.')
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{name} must be numeric.') from None
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f'{name} must be finite and between {lo} and {hi}.')
    return value


def logistic(x):
    return 1 / (1 + math.exp(-max(-35., min(35., x))))


def logit(p):
    p = max(1e-9, min(1-1e-9, p))
    return math.log(p / (1-p))


def log5(pitcher, batter, league=LEAGUE_K):
    return logistic(logit(pitcher) + logit(batter) - logit(league))


def skill(row, league=LEAGUE_K, prior_pa=120):
    p = numeric(row.get('K'), 'K percentage', 0, 100)/100
    n = numeric(row.get('pa'), 'skill sample PA', 0, 1e6)
    return (n*p + prior_pa*league)/(n+prior_pa)


def split_skill(base, details, hand, league, prior_pa):
    overall = skill(base, league, prior_pa)
    split = details.get('splits', {}).get(hand)
    if not split:
        return overall, False
    n = numeric(split.get('pa'), 'split PA', 0, 1e6)
    p = numeric(split.get('K'), 'split K percentage', 0, 100)/100
    return (n*p + prior_pa*overall)/(n+prior_pa), True


def features_for(pitcher, hitter, context):
    result = {k: v for k, v in {**pitcher, **context}.items() if k in FEATURES}
    arsenal = pitcher.get('arsenal', [])
    if arsenal:
        if abs(sum(numeric(p.get('usage'), 'pitch usage', 0, 1) for p in arsenal)-1) > 1e-8:
            raise ValueError('Pitch arsenal usage must sum to one.')
        for target, field in [('arsenal_whiff_pct', 'whiff_pct'),
                              ('arsenal_chase_pct', 'chase_pct'),
                              ('arsenal_run_value_per100', 'run_value_per100')]:
            rows = hitter.get('pitch_types', {})
            if all(field in rows.get(p['pitch_type'], {}) for p in arsenal):
                result[target] = sum(p['usage']*numeric(rows[p['pitch_type']][field], field) for p in arsenal)
        for key in ['velocity', 'vertical_break', 'horizontal_break', 'release_height', 'extension']:
            if all(key in p for p in arsenal):
                result[key] = sum(p['usage']*numeric(p[key], key) for p in arsenal)
    return result


def feature_offset(model, features):
    offset = numeric(model.get('intercept', 0), 'feature intercept', -20, 20)
    for name, coefficient in model.get('coefficients', {}).items():
        if name not in FEATURES:
            raise ValueError(f'Unsupported feature: {name}')
        value = numeric(features.get(name), name)
        reference = numeric(model.get('reference', {}).get(name, 0), name+' reference')
        scale = numeric(model.get('scale', {}).get(name, 1), name+' scale', 1e-9, 1e6)
        offset += numeric(coefficient, name+' coefficient', -20, 20)*(value-reference)/scale
    return offset


def validate_counts(table):
    if not isinstance(table, dict):
        raise ValueError('Count probabilities must be an object.')
    for b in range(4):
        for s in range(3):
            cell = table.get(f'{b}-{s}', {})
            if set(cell) != {'ball', 'called_strike', 'whiff', 'foul', 'in_play'}:
                raise ValueError('Each of the 12 counts needs ball/called_strike/whiff/foul/in_play.')
            values = [numeric(v, 'pitch event probability', 0, 1) for v in cell.values()]
            if abs(sum(values)-1) > 1e-8 or (s == 2 and cell['foul'] >= 1-1e-9):
                raise ValueError('Pitch probabilities must sum to one and allow termination.')
    return table


def count_k_probability(table):
    """Absorbing count recursion; a two-strike foul stays in the same count."""
    validate_counts(table)
    values = {}
    for b in reversed(range(4)):
        for s in reversed(range(3)):
            q = table[f'{b}-{s}']
            next_ball = values[(b+1, s)] if b < 3 else 0.
            next_strike = values[(b, s+1)] if s < 2 else 1.
            v = q['ball']*next_ball + (q['called_strike']+q['whiff'])*next_strike
            if s < 2:
                v += q['foul']*next_strike
            else:
                v /= 1-q['foul']
            values[(b, s)] = v
    return values[(0, 0)]


def hitter_rates(row, params, profile=None):
    profile = profile or {}
    league = numeric(params.get('league_k', LEAGUE_K), 'league K prior', .001, .999)
    pitcher = profile.get('pitcher', {})
    hitters = profile.get('hitters', {})
    phand = pitcher.get('hand')
    rows = sorted(row['lineup_rows'], key=lambda b: b['order'])
    if len(rows) != 9 or [b['order'] for b in rows] != list(range(1, 10)):
        raise ValueError('DELTA needs the exact nine-player batting order.')
    if len({str(b['mlbId']) for b in rows}) != 9:
        raise ValueError('DELTA lineup identities must be unique.')
    result = []
    for batter in rows:
        detail = hitters.get(str(batter['mlbId']), {})
        hand = detail.get('hand')
        if hand == 'S' and phand in {'L', 'R'}:
            hand = 'R' if phand == 'L' else 'L'
        pk, psplit = split_skill(row['pitcher_row'], pitcher, hand, league, 180)
        bk, bsplit = split_skill(batter, detail, phand, league, 120)
        p = log5(pk, bk, league)
        mode = 'SHRUNK_LOG5'
        features = features_for(pitcher, detail, profile.get('context', {}))
        if detail.get('count_probabilities'):
            if profile.get('feature_model'):
                raise ValueError('Use a count model or a feature adjustment, to avoid double counting.')
            p = count_k_probability(detail['count_probabilities'])
            mode = 'IMPORTED_PITCH_COUNT_MODEL'
        elif profile.get('feature_model'):
            p = logistic(logit(p)+feature_offset(profile['feature_model'], features))
            mode = 'IMPORTED_FEATURE_MODEL'
        else:
            p = logistic(logit(p)+numeric(params.get('skill_intercept', 0), 'skill intercept', -10, 10))
        result.append({'player_id': str(batter['mlbId']), 'player': batter['name'],
                       'order': batter['order'], 'k_probability': p,
                       'pitcher_split_used': psplit, 'batter_split_used': bsplit,
                       'mode': mode, 'features': features})
    return result


def probability_rows(rows, key):
    output = {}
    for row in rows:
        index = numeric(row.get(key), key, 0, MAX_BF)
        if not index.is_integer():
            raise ValueError(f'{key} must be an integer.')
        p = numeric(row.get('probability'), 'probability', 0, 1)
        output[int(index)] = output.get(int(index), 0)+p
    if not output or abs(sum(output.values())-1) > 1e-8:
        raise ValueError('Distribution probabilities must sum to one.')
    return output


def workload_pmf(mean_bf, params, profile=None):
    profile = profile or {}
    if profile.get('bf_pmf') is not None:
        return probability_rows(profile['bf_pmf'], 'bf')
    mean = numeric(mean_bf, 'expected BF', 0, MAX_BF)
    residuals = params.get('bf_residuals') or [1.]
    output = {}
    for r in residuals:
        n = mean*numeric(r, 'BF residual', 0, 10)
        if n > MAX_BF:
            raise ValueError('BF support exceeds DELTA compute limit; provide a bounded workload distribution.')
        low = math.floor(n)
        for bf, weight in [(low, 1-(n-low)), (low+1, n-low)]:
            if weight:
                output[bf] = output.get(bf, 0)+weight/len(residuals)
    return output


def beta_binomial(n, p, concentration):
    if n == 0:
        return [1.]
    if p <= 0 or p >= 1:
        return [1. if k == (n if p >= 1 else 0) else 0. for k in range(n+1)]
    c = numeric(concentration, 'beta concentration', .01, 1e8)
    a, b = p*c, (1-p)*c
    normal = math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)-math.lgamma(n+a+b)
    result = [math.exp(math.lgamma(n+1)-math.lgamma(k+1)-math.lgamma(n-k+1)+
                       math.lgamma(k+a)+math.lgamma(n-k+b)+normal) for k in range(n+1)]
    total = sum(result)
    return [v/total for v in result]


def count_distributions(rates, bf, concentration=100):
    max_bf = max(bf)
    pa, beta, prefix, total_p = [0.]*(max_bf+1), [0.]*(max_bf+1), [1.], 0.
    for n in range(max_bf+1):
        if n:
            p = rates[(n-1) % 9]['k_probability']
            total_p += p
            updated = [0.]*(n+1)
            for k, v in enumerate(prefix):
                updated[k] += v*(1-p)
                updated[k+1] += v*p
            prefix = updated
        weight = bf.get(n, 0)
        if weight:
            bp = beta_binomial(n, total_p/n if n else 0, concentration)
            for k, (a, b) in enumerate(zip(prefix, bp)):
                pa[k] += weight*a
                beta[k] += weight*b
    return {'pa': pa, 'beta_binomial': beta}


def summarize(pmf):
    mean = sum(k*p for k, p in enumerate(pmf))
    variance = sum((k-mean)**2*p for k, p in enumerate(pmf))
    quantiles, cdf = {}, 0.
    for k, p in enumerate(pmf):
        cdf += p
        for label, q in [('p10', .1), ('p50', .5), ('p90', .9)]:
            if label not in quantiles and cdf >= q-1e-12:
                quantiles[label] = k
    return {'expected_k': mean, 'variance': variance, 'sd': math.sqrt(variance),
            **quantiles, 'pmf': pmf}


def at_line(pmf, line):
    line = numeric(line, 'strikeout line', 0, MAX_BF)
    if not (line*2).is_integer():
        raise ValueError('Use a whole or half strikeout line.')
    return {'over': sum(p for k, p in enumerate(pmf) if k > line),
            'under': sum(p for k, p in enumerate(pmf) if k < line),
            'push': sum(p for k, p in enumerate(pmf) if k == line)}


def forecast(row, v2, params, profile=None):
    profile = profile or {}
    rates = hitter_rates(row, params, profile)
    bf = workload_pmf(v2['expected_bf'], params, profile)
    distributions = count_distributions(rates, bf, params.get('beta_concentration', 100))
    return {'model_version': VERSION, 'player_id': str(row['starter_input']['officialMlbId']),
            'player': row['starter_input']['officialName'], 'game_id': str(row['game_id']),
            'status': 'RESEARCH_ADVANCED_INPUTS' if profile else 'RESEARCH_PA_PROXY',
            'expected_bf': sum(n*p for n, p in bf.items()),
            'probability_bf_over_18': sum(p for n, p in bf.items() if n > 18),
            'probability_bf_over_27': sum(p for n, p in bf.items() if n > 27),
            'bf_pmf': [{'bf': n, 'probability': p} for n, p in sorted(bf.items())],
            'hitters': rates, 'pa': summarize(distributions['pa']),
            'beta_binomial': summarize(distributions['beta_binomial']),
            'beta_concentration': params.get('beta_concentration', 100),
            'training_seasons': params.get('training_seasons', []),
            'feature_profile_snapshot_id': profile.get('snapshot_id'),
            'target_k_market_weight': 0, 'edge_verified': False,
            'advanced_layers': {
                'platoon_splits': 'IMPORTED' if any(r['pitcher_split_used'] or r['batter_split_used'] for r in rates) else 'MISSING',
                'pitch_count_model': 'IMPORTED' if all(r['mode'] == 'IMPORTED_PITCH_COUNT_MODEL' for r in rates) else 'MISSING_OR_PARTIAL',
                'physical_feature_model': 'IMPORTED' if profile.get('feature_model') else 'NOT_FITTED',
                'manager_hook_model': 'SCENARIO_AVAILABLE' if profile.get('hook_model') else 'NOT_FITTED',
                'umpire_weather_series_familiarity': 'IMPORTED_FEATURES' if profile.get('context') else 'MISSING',
            },
            'notes': ['Independent workload mixture assumes K efficiency and the hook are conditionally independent.',
                      'No automatic October K boost, extra velocity, cross-league reward, or 18-BF hard cap.',
                      'Beta-binomial averages PA rates and adds shared efficiency variation; PA retains hitter heterogeneity.',
                      'Imported advanced models and simplified hook simulations have not earned promotion.']}


def fit_parameters(training, test_season):
    """Fit only supplied PRIOR seasons. Workload fitting reads BF, not K targets.

    A scalar efficiency intercept uses historical K/BF, not prices. BF residuals
    are centered to keep the V2 workload mean. No manager hazard is fabricated.
    """
    training = [r for r in training if int(r['season']) < int(test_season)]
    if not training:
        return {'league_k': LEAGUE_K, 'skill_intercept': 0., 'bf_residuals': [1.],
                'beta_concentration': 100., 'training_seasons': [], 'training_n': 0,
                'status': 'WARMUP'}
    raw_rates = [hitter_rates(r['input'], {}) for r in training]
    pairs = [(rates[(i-1) % 9]['k_probability'], 1) for r, rates in zip(training, raw_rates)
             for i in range(1, r['actual_bf']+1)]
    target = sum(r['actual_k'] for r in training)
    lo, hi = -5., 5.
    for _ in range(45):
        mid = (lo+hi)/2
        expected = sum(logistic(logit(p)+mid)*n for p, n in pairs)
        if expected < target:
            lo = mid
        else:
            hi = mid
    intercept = (lo+hi)/2
    residuals = [r['actual_bf']/r['v2']['expected_bf'] for r in training if r['v2']['expected_bf'] > 0]
    center = fmean(residuals)
    residuals = [r/center for r in residuals] if center > 0 else [1.]
    scores = {}
    # Declared prior-only dispersion grid. Every future fold is evaluated.
    for c in [5., 20., 100., 500., 5000.]:
        loss = 0.
        for r, rates in zip(training, raw_rates):
            n = r['actual_bf']
            p = fmean(logistic(logit(rates[i % 9]['k_probability'])+intercept) for i in range(n)) if n else 0.
            loss -= math.log(max(1e-12, beta_binomial(n, p, c)[r['actual_k']]))
        scores[c] = loss
    return {'league_k': LEAGUE_K, 'skill_intercept': intercept,
            'bf_residuals': residuals, 'beta_concentration': min(scores, key=scores.get),
            'training_seasons': sorted({r['season'] for r in training}),
            'training_n': len(training), 'status': 'PRIOR_SEASON_FIT',
            'dispersion_training_log_loss': {str(k): v/len(training) for k, v in scores.items()},
            'bf_center_before_normalization': center,
            'assumptions': ['League prior .225; pitcher/batter prior PA 180/120.',
                            'Retrospective starting-order proxy; substitutions and original pregame receipts unavailable.']}


def draw_count(table, rng, validated=False):
    if not validated: validate_counts(table)
    b, s, pitches = 0, 0, 0
    while pitches < 500:
        q = table[f'{b}-{s}']; pitches += 1
        event = rng.choices(list(q), list(q.values()))[0]
        if event == 'in_play': return 'CONTACT', pitches
        if event == 'ball':
            b += 1
            if b == 4: return 'WALK', pitches
        elif event != 'foul' or s < 2:
            s += 1
            if s == 3: return 'K', pitches
    raise ValueError('Count simulation did not terminate within its compute limit.')


def simulate(row, v2, params, profile=None, draws=10000, seed=61026):
    draws = numeric(draws, 'simulation draws', 1000, 50000)
    seed = numeric(seed, 'seed', 0, 2**32-1)
    if not draws.is_integer() or not seed.is_integer(): raise ValueError('Draws and seed must be integers.')
    draws, seed = int(draws), int(seed)
    profile = profile or {}; rates = hitter_rates(row, params, profile)
    bf = workload_pmf(v2['expected_bf'], params, profile)
    rng = random.Random(seed); counts = [0]*(MAX_BF+1); workloads = [0]*(MAX_BF+1)
    hook = profile.get('hook_model')
    if hook:
        # Hazard simulation replaces the independent BF mixture, never stacks it.
        allowed = {'bf', 'outs', 'pitch_count', 'tto', 'baserunners', 'runs', 'leverage', 'bullpen_available', 'elimination_game'}
        if set(hook.get('coefficients', {}))-allowed: raise ValueError('Unsupported hook feature.')
        cap = int(numeric(hook.get('max_bf'), 'manager max BF', 1, MAX_BF))
        if not all(profile.get('hitters', {}).get(r['player_id'], {}).get('count_probabilities') for r in rates):
            raise ValueError('Dynamic hook scenarios require a pitch-count model for all nine hitters.')
        contact = profile.get('contact_outcomes', {})
        if set(contact) != {'OUT', '1B', '2B', '3B', 'HR'} or abs(sum(numeric(p, 'contact probability', 0, 1) for p in contact.values())-1)>1e-8:
            raise ValueError('Hook simulation requires conditional contact OUT/1B/2B/3B/HR probabilities.')
    for _ in range(draws):
        n = cap if hook else rng.choices(list(bf), list(bf.values()))[0]
        ks = outs = pitches = runs = faced = 0; bases = [False]*3
        for i in range(n):
            r = rates[i % 9]; detail = profile.get('hitters', {}).get(r['player_id'], {})
            table = detail.get('count_probabilities')
            event, used = draw_count(table, rng, True) if table else ('K' if rng.random()<r['k_probability'] else 'CONTACT', 0)
            pitches += used; faced += 1
            if event == 'K': ks += 1; outs += 1
            elif hook:
                if event == 'CONTACT': event = rng.choices(list(contact), list(contact.values()))[0]
                if event == 'OUT': outs += 1
                elif event == 'WALK':
                    if all(bases): runs += 1
                    if bases[0] and bases[1]: bases[2] = True
                    if bases[0]: bases[1] = True
                    bases[0] = True
                else:
                    distance = {'1B': 1, '2B': 2, '3B': 3, 'HR': 4}[event]
                    updated = [False]*3
                    for j, occupied in enumerate(bases):
                        if occupied:
                            if j+distance >= 3: runs += 1
                            else: updated[j+distance] = True
                    if distance == 4: runs += 1
                    else: updated[distance-1] = True
                    bases = updated
            if hook:
                if outs >= 27: break
                if event in {'K', 'OUT'} and outs % 3 == 0: bases = [False]*3
                values = {'bf': faced, 'outs': outs, 'pitch_count': pitches, 'tto': i//9,
                          'baserunners': sum(bases), 'runs': runs,
                          **{k: profile.get('context', {}).get(k) for k in ['leverage', 'bullpen_available', 'elimination_game']}}
                offset = numeric(hook.get('intercept'), 'hook intercept', -35, 35)
                for key, coef in hook.get('coefficients', {}).items():
                    offset += numeric(coef, key+' hook coefficient', -20, 20)*numeric(values.get(key), key)
                max_pitches = numeric(hook.get('max_pitches'), 'manager pitch ceiling', 1, 200)
                if pitches >= max_pitches or rng.random() < logistic(offset): break
        counts[ks] += 1; workloads[faced] += 1
    pmf = [c/draws for c in counts]
    return {'model_version': VERSION, 'draws': draws, 'seed': seed,
            'mode': 'SIMPLIFIED_DYNAMIC_HOOK_SCENARIO' if hook else 'PA_OR_PITCH_MONTE_CARLO',
            'distribution': summarize(pmf), 'expected_bf': sum(i*c/draws for i, c in enumerate(workloads)),
            'bf_pmf': [{'bf': i, 'probability': c/draws} for i, c in enumerate(workloads) if c],
            'expected_k_mc_se': math.sqrt(summarize(pmf)['variance']/draws),
            'note': 'Hook scenarios use simplified base advancement and externally supplied leverage; they are not trained game-state forecasts.'}

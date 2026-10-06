"""Unpromoted DELTA research calculations. The frozen 0.1 forecast does not call these.

All inputs must be known at the stated pregame cutoff. These functions produce
auditable estimates and conditional scenarios, not fitted 2026 coefficients.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime

from .delta_model import MAX_BF, logit, logistic, numeric


def _stamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Research source times require an explicit timezone.')
    return parsed


def platoon_posterior(overall_k, league_overall_k, league_hand_k,
                      split_pa=0, split_k=0, prior_pa=120):
    """Beta posterior with a league hand odds shift applied to player overall K.

    The league adjustment is an odds ratio, not a product of two percentages.
    An unsampled split is explicitly ESTIMATED, not an observed player split.
    """
    base = numeric(overall_k, 'player overall K rate', .001, .999)
    league = numeric(league_overall_k, 'league overall K rate', .001, .999)
    hand = numeric(league_hand_k, 'league hand K rate', .001, .999)
    n = numeric(split_pa, 'split PA', 0, 1e6)
    k = numeric(split_k, 'split K count', 0, 1e6)
    c = numeric(prior_pa, 'prior PA', 1, 1e6)
    if not n.is_integer() or not k.is_integer() or k > n:
        raise ValueError('Split K and PA must be integer counts, with K <= PA.')
    prior = logistic(logit(base) + logit(hand) - logit(league))
    alpha, beta = c*prior+k, c*(1-prior)+n-k
    mean = alpha/(alpha+beta)
    return {'projected_k_rate': mean, 'prior_k_rate': prior,
            'observed_pa': int(n), 'observed_k': int(k), 'prior_pa': c,
            'posterior_sd': math.sqrt(alpha*beta/((alpha+beta)**2*(alpha+beta+1))),
            'status': 'SHRUNK_OBSERVED' if n else 'ESTIMATED_LEAGUE_HAND_PRIOR'}


def arsenal_whiff(pitcher_arsenal, hitter_pitch_types, league_whiff_by_type,
                  prior_swings=50):
    """Usage weighted posterior whiff per *swing*, with measured denominators.

    Pitch selection may change against a particular hitter; this descriptive
    matrix is deliberately not converted into K probability without fitting.
    """
    c = numeric(prior_swings, 'prior swings', 1, 1e6)
    usage = sum(numeric(p['usage'], 'pitch usage', 0, 1) for p in pitcher_arsenal)
    if not pitcher_arsenal or abs(usage-1) > 1e-8:
        raise ValueError('Complete pitcher arsenal usage must sum to one.')
    out, estimate, baseline = [], 0., 0.
    for pitch in pitcher_arsenal:
        name = pitch['pitch_type']
        if name not in league_whiff_by_type:
            raise ValueError(f'Missing sourced league whiff prior for {name}.')
        prior = numeric(league_whiff_by_type[name], name+' league whiff', .001, .999)
        details = hitter_pitch_types.get(name, {})
        swings = numeric(details.get('swings', 0), name+' swings', 0, 1e6)
        whiffs = numeric(details.get('whiffs', 0), name+' whiffs', 0, 1e6)
        if not swings.is_integer() or not whiffs.is_integer() or whiffs > swings:
            raise ValueError('Whiffs and swings must be integer counts, with whiffs <= swings.')
        p = (whiffs+c*prior)/(swings+c)
        weight = numeric(pitch['usage'], 'pitch usage', 0, 1)
        estimate += weight*p
        baseline += weight*prior
        out.append({'pitch_type': name, 'usage': weight, 'swings': int(swings),
                    'whiffs': int(whiffs), 'projected_whiff_per_swing': p,
                    'league_whiff_per_swing': prior,
                    'status': 'SHRUNK_OBSERVED' if swings else 'ESTIMATED_LEAGUE_TYPE_PRIOR'})
    return {'pitch_types': out, 'weighted_whiff_per_swing': estimate,
            'weighted_league_whiff_per_swing': baseline,
            'difference': estimate-baseline, 'status': 'DESCRIPTIVE_UNFITTED'}


def four_seam_trend(pitches, starter_game_ids=None, min_pitches=10):
    """Compare final two complete prior regular-season starts with earlier starts.

    Expects the normalized pitcher pitch rows. A 1.5 mph change is reported as
    a measurement, never transformed into a Stuff+ or strikeout coefficient.
    """
    if not starter_game_ids:
        return {'status':'MISSING_CONFIRMED_START_IDENTITIES'}
    starters = {str(game) for game in starter_game_ids}
    games = defaultdict(list)
    for row in pitches:
        if (row.get('game_type') != 'R' or row.get('pitch_type') != 'FF' or
                str(row.get('game_pk')) not in starters):
            continue
        speed = row.get('velocity_mph')
        if speed is not None:
            games[(row['game_date'], row['game_pk'])].append(numeric(speed, 'velocity', 50, 110))
    qualified = [(key, values) for key, values in sorted(games.items()) if len(values) >= min_pitches]
    if len(qualified) < 3:
        return {'status': 'INSUFFICIENT_REGULAR_SEASON_STARTS', 'qualified_starts': len(qualified)}
    earlier = [p for _, values in qualified[:-2] for p in values]
    recent = [p for _, values in qualified[-2:] for p in values]
    before, after = sum(earlier)/len(earlier), sum(recent)/len(recent)
    return {'status': 'MEASURED_UNFITTED', 'qualified_starts': len(qualified),
            'recent_game_ids': [key[1] for key, _ in qualified[-2:]],
            'baseline_pitches': len(earlier), 'recent_pitches': len(recent),
            'baseline_mph': before, 'recent_mph': after, 'change_mph': after-before}


def research_matchups(profile, priors, lineup):
    """Build optional matchup estimates, never live DELTA 0.1 inputs."""
    if not priors.get('source') or _stamp(priors.get('training_end_at')) >= _stamp(profile['observed_at']):
        raise ValueError('League/player priors need a source and a cutoff before the profile receipt.')
    if len(lineup) != 9 or len(set(lineup)) != 9:
        raise ValueError('Research lineup needs nine distinct MLBAM IDs.')
    league = numeric(priors.get('league_k'), 'league K rate', .001, .999)
    player_k = priors.get('player_overall_k', {})
    pitcher = profile['pitcher']; pitcher_id = str(profile['player_id'])
    phand = pitcher.get('hand')
    rows = []
    for index, player_id in enumerate(lineup, 1):
        pid = str(player_id); hitter = profile['hitters'].get(pid, {})
        bhand = hitter.get('hand')
        if bhand == 'S' and phand in {'L','R'}:
            bhand = 'R' if phand == 'L' else 'L'
        result = {'order':index,'player_id':pid,'batter_hand':bhand,
                  'pitcher_hand':phand,'status':'UNAVAILABLE'}
        if phand in {'L','R'} and bhand in {'L','R'} and pid in player_k and pitcher_id in player_k:
            hitter_split = hitter.get('splits', {}).get(phand, {})
            pitcher_split = pitcher.get('splits', {}).get(bhand, {})
            def observed(split):
                pa = int(numeric(split.get('pa',0),'observed split PA',0,1e6))
                ks = round(pa*numeric(split.get('K',0),'observed split K%',0,100)/100)
                return pa,ks
            hp,hk = observed(hitter_split); pp,pk = observed(pitcher_split)
            hp_prior=priors['batter_k_by_pitcher_hand'][phand]
            pp_prior=priors['pitcher_k_by_batter_hand'][bhand]
            h = platoon_posterior(player_k[pid],league,hp_prior,hp,hk,priors['hitter_prior_pa'])
            p = platoon_posterior(player_k[pitcher_id],league,pp_prior,pp,pk,priors['pitcher_prior_pa'])
            result.update(status='ESTIMATED_RESEARCH',pitcher_split=p,batter_split=h,
                          matchup_log5_unfitted=logistic(logit(p['projected_k_rate'])+
                                 logit(h['projected_k_rate'])-logit(league)))
        if pitcher.get('arsenal') and 'league_pitch_type_whiff' in priors:
            try:
                result['arsenal_whiff'] = arsenal_whiff(pitcher['arsenal'],
                    hitter.get('pitch_types', {}), priors['league_pitch_type_whiff'],
                    priors['pitch_type_prior_swings'])
            except (KeyError, ValueError) as exc:
                result['arsenal_unavailable_reason'] = str(exc)
        rows.append(result)
    return {'status':'UNFITTED_RESEARCH_NO_FORECAST_EFFECT',
            'source':priors['source'],'training_end_at':priors['training_end_at'],
            'profile_observed_at':profile['observed_at'],
            'four_seam_trend':pitcher.get('four_seam_trend',{'status':'MISSING'}),
            'lineup':rows}


def hook_probability(model, state):
    """Discrete end-of-PA removal hazard for a separately fitted model."""
    offset = numeric(model['intercept'], 'hook intercept', -35, 35)
    for name, coef in model.get('coefficients', {}).items():
        if name not in {'bf', 'pitch_count', 'runs_allowed', 'strikeouts', 'leverage'}:
            raise ValueError(f'Unsupported dynamic hook feature: {name}.')
        value = numeric(state.get(name), name, 0, 1e5)
        center = numeric(model.get('reference', {}).get(name, 0), name+' reference')
        scale = numeric(model.get('scale', {}).get(name, 1), name+' scale', 1e-9, 1e6)
        offset += numeric(coef, name+' coefficient', -20, 20)*(value-center)/scale
    return logistic(offset)


def conditional_k_matrix(hitter_kernels, hook_model, max_bf=36, initial_state=None):
    """Exact forward recursion over K, pitches, runs and supplied leverage state.

    Each of nine kernels contains outcome rows with probability, k (0/1),
    pitches, runs_allowed, and leverage_after. The outcomes and hook model
    require independently fitted, pregame-vintage contracts. A path stops only
    after a PA. This is a research engine, with no artificial 19-BF ceiling.
    """
    if len(hitter_kernels) != 9:
        raise ValueError('Exactly nine hitter outcome kernels are required.')
    cap = numeric(max_bf, 'max BF support', 1, MAX_BF)
    if not cap.is_integer(): raise ValueError('Max BF must be an integer.')
    cap = int(cap)
    kernels = []
    for rows in hitter_kernels:
        if not rows or abs(sum(numeric(r['probability'], 'outcome probability', 0, 1) for r in rows)-1)>1e-8:
            raise ValueError('Each hitter outcome kernel must sum to one.')
        validated = []
        for r in rows:
            k = numeric(r['k'], 'K event', 0, 1)
            p = numeric(r['pitches'], 'PA pitch count', 1, 30)
            runs = numeric(r['runs_allowed'], 'runs allowed', 0, 4)
            lev = numeric(r['leverage_after'], 'leverage after PA', 0, 10)
            if not all(v.is_integer() for v in (k,p,runs)):
                raise ValueError('K, pitches and runs must be integer events.')
            validated.append((numeric(r['probability'],'outcome probability',0,1),int(k),int(p),int(runs),lev))
        kernels.append(validated)
    initial = initial_state or {'pitch_count':0,'runs_allowed':0,'leverage':1.}
    states = {(0,0,0,numeric(initial['leverage'],'initial leverage',0,10)):1.}
    terminal = [0.]*(cap+1); bf_pmf = [0.]*(cap+1)
    for bf in range(1,cap+1):
        if len(states)>100000:
            raise ValueError('Conditional scenario exceeds 100,000 states; coarsen its outcome support.')
        future = defaultdict(float)
        entering_mass = sum(states.values())
        for (ks,pitches,runs,_lev), weight in states.items():
            for probability,k,used,scored,new_lev in kernels[(bf-1)%9]:
                q = weight*probability
                state = (ks+k,pitches+used,runs+scored,new_lev)
                hazard = hook_probability(hook_model, {'bf':bf,'pitch_count':state[1],
                              'runs_allowed':state[2],'strikeouts':state[0],
                              'leverage':new_lev})
                if bf == cap: hazard = 1.
                terminal[state[0]] += q*hazard
                bf_pmf[bf] += q*hazard
                future[state] += q*(1-hazard)
        states = future
    if abs(sum(terminal)-1)>1e-8:
        raise ArithmeticError('Conditional K matrix did not conserve mass.')
    return {'k_pmf': terminal, 'bf_pmf': bf_pmf,
            'expected_k': sum(k*v for k,v in enumerate(terminal)),
            'expected_bf': sum(n*v for n,v in enumerate(bf_pmf)),
            'status': 'CONDITIONAL_RESEARCH_SCENARIO',
            'forced_tail_mass': entering_mass}

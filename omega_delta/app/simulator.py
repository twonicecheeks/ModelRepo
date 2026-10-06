"""An explicit, untrained joint tackle-event simulator.

Anchors on saved H008 family means, shares a game-volume factor, redistributes
credit weights under participation/role scenarios, and allows two different
defenders to receive credit on one opportunity. No outcomes or prices enter.
This is a hypothesis lab, not a replacement fitted champion.
"""
from __future__ import annotations

import bisect
import math
import random
from collections import Counter
from statistics import fmean

from .core import TARGET, bounded, number

FAMILIES = ("RUSH", "COMPLETE_PASS", "SCRAMBLE", "SACK", "OTHER_PASS")


def poisson(rng, mean):
    # Exact additive decomposition avoids underflow for large lambda.
    if mean <= 0:
        return 0
    if mean > 25:
        parts = math.ceil(mean/25)
        return sum(poisson(rng, mean/parts) for _ in range(parts))
    cutoff, p, k = math.exp(-mean), 1.0, 0
    while p > cutoff:
        k += 1
        p *= rng.random()
    return k-1


def choose(rng, weights):
    total = sum(weights)
    if total <= 0:
        return None
    return min(len(weights)-1, bisect.bisect_right(_cumulative(weights), rng.random()*total))


def _cumulative(values):
    total, out = 0.0, []
    for v in values:
        total += v
        out.append(total)
    return out


def quantile(values, q):
    return sorted(values)[min(len(values)-1, int(q*(len(values)-1)))]


def correlation(a, b):
    ma, mb = fmean(a), fmean(b)
    va = sum((x-ma)**2 for x in a)
    vb = sum((x-mb)**2 for x in b)
    if va <= 1e-12 or vb <= 1e-12:
        return None
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(va*vb)


def line_probabilities(values, line):
    n = len(values)
    return {"over": sum(x > line for x in values)/n, "under": sum(x < line for x in values)/n,
            "push": sum(x == line for x in values)/n}


def inclusion_probabilities(weights, total):
    """Capped proportional allocation; each defender can have one credit/event."""
    out = [0.0]*len(weights)
    remaining = {i for i,w in enumerate(weights) if w > 0}
    unallocated = max(0,total-len(remaining))
    total = min(total,len(remaining))
    while remaining and total > 1e-12:
        mass = sum(weights[i] for i in remaining)
        capped = [i for i in remaining if weights[i]/mass*total > 1]
        if not capped:
            for i in remaining: out[i] = weights[i]/mass*total
            break
        for i in capped:
            out[i] = 1.0
            remaining.remove(i)
            total -= 1
    return out, unallocated


def sample_credits(rng, probabilities):
    """Random-order systematic sampling preserves each inclusion marginal.

    A uniform offset traverses intervals of length p_i <= 1 with unit spacing.
    Thus no interval can be selected twice, E[I_i]=p_i, and total credits are
    floor(sum p) or ceil(sum p). This is a scenario dependence assumption.
    """
    order = [i for i,p in enumerate(probabilities) if p > 0]
    rng.shuffle(order)
    offset, edge, selected = rng.random(), 0.0, []
    for i in order:
        edge += probabilities[i]
        if offset < edge-1e-12:
            selected.append(i)
            offset += 1
    return selected


def simulate(rows, config):
    game, team = str(config.get("game_id", "")), str(config.get("team", ""))
    players = [r for r in rows if r["game_id"] == game and r["team"] == team]
    players.sort(key=lambda r: number(r.get("role_point_xtc")), reverse=True)
    if len(players) < 2:
        raise ValueError("Choose a team with at least two saved players.")
    n = int(bounded(config.get("draws", 2500), 200, 10000))
    seed = int(bounded(config.get("seed", 2709), 0, 2**31-1))
    pace = bounded(config.get("pace", 1), .5, 1.6)
    cv = bounded(config.get("volume_cv", .15), 0, .8)
    competition = bounded(config.get("competition", 0), 0, 1.5)
    run_shift = bounded(config.get("rush_shift", 0), -.3, .3)
    availability = config.get("availability", {})
    for pid, prob in availability.items():
        bounded(prob, 0, 1)
        if pid not in {r["player_id"] for r in players}:
            raise ValueError("Availability override names a player outside this team.")
    pair_ids = config.get("pair") or [r["player_id"] for r in players[:2]]
    if len(pair_ids) != 2 or len(set(pair_ids)) != 2:
        raise ValueError("Choose two different teammates.")
    try:
        ia, ib = [next(i for i,r in enumerate(players) if r["player_id"] == p) for p in pair_ids]
    except StopIteration:
        raise ValueError("Pair must belong to the selected team and game.") from None
    lines = [bounded(v, 0, 30) for v in config.get("lines", [6.5, 6.5])]
    if len(lines) != 2:
        raise ValueError("Two comparison thresholds are required.")
    opportunities = max(1, number(players[0].get("predicted_xto"), 48))
    shares = [max(0, number(players[0].get("pred_share_"+f))) for f in FAMILIES]
    if not sum(shares):
        raise ValueError("This snapshot lacks H008 opportunity-family inputs.")
    share_sum = sum(shares)
    shares = [x/share_sum for x in shares]
    original_shares = list(shares)
    for row in players:
        if abs(number(row.get('predicted_xto'),48)-opportunities)>1e-6:
            raise ValueError('Teammates have inconsistent team opportunity forecasts.')
        row_shares=[number(row.get('pred_share_'+f)) for f in FAMILIES]
        if sum(row_shares)<=0 or any(abs(v/sum(row_shares)-p)>1e-6 for v,p in zip(row_shares,original_shares)):
            raise ValueError('Teammates have inconsistent opportunity-family shares.')
    delta = max(-shares[0], min(shares[1], run_shift))
    shares[0] += delta
    shares[1] -= delta
    base_weights, yields = [], []
    for j,f in enumerate(FAMILIES):
        weights = []
        for r in players:
            control_share = number(r.get("control_h012_snap_share"))
            role_share = number(r.get("role_point_snap_share"))
            c = max(0, number(r.get("control_pred_credit_"+f)))
            weights.append(c*role_share/control_share if control_share > 0 else 0)
        base_weights.append(weights)
        denom = opportunities*original_shares[j]
        yields.append(sum(weights)/denom if denom > 0 else 0)
    # Keep each saved role mean exactly as the neutral expected count. The old
    # without-replacement second draw changed the marginal inclusion weights.
    for i,r in enumerate(players):
        total = sum(w[i] for w in base_weights)
        target = number(r['role_point_xtc'])
        if target > 0 and total <= 0:
            raise ValueError("Positive role mean has no family contributions.")
        for weights in base_weights:
            weights[i] *= target/total if total else 0
    yields = [sum(w)/(opportunities*original_shares[j]) if original_shares[j] else 0 for j,w in enumerate(base_weights)]
    if any(sum(w)>1e-9 and original_shares[j]<=0 for j,w in enumerate(base_weights)):
        raise ValueError('Positive family credits have zero projected opportunities; reconcile the inputs.')
    if any(x>2+1e-9 for x in yields):
        raise ValueError("Team credit yield exceeds the lab's two-credit event assumption; reconcile the target before simulating.")
    for j,w in enumerate(base_weights):
        denom=opportunities*original_shares[j]
        if denom and any(v/denom>1+1e-9 for v in w):
            raise ValueError("A player exceeds one expected credit per family opportunity; inputs need reconciliation.")
    unbounded_yields = list(yields)
    yields = [min(2, max(0, x)) for x in yields]
    rng = random.Random(seed)
    samples = [[] for _ in players]
    opportunities_samples, total_samples = [], []
    unused_credits = 0
    for _ in range(n):
        active = [rng.random() < number(availability.get(r["player_id"], 1)) for r in players]
        role_factor = [1.0]*len(players)
        z = rng.gauss(0, competition)
        role_factor[ia], role_factor[ib] = math.exp(z), math.exp(-z)
        latent_volume = rng.gammavariate(1/(cv*cv), cv*cv) if cv else 1.0
        counts = [0]*len(players)
        total_opps = 0
        for j,f in enumerate(FAMILIES):
            opp_count = poisson(rng, opportunities*shares[j]*pace*latent_volume)
            total_opps += opp_count
            weights = [w*role_factor[i] if active[i] else 0 for i,w in enumerate(base_weights[j])]
            inclusion, missing = inclusion_probabilities(weights,yields[j])
            for __ in range(opp_count):
                selected = sample_credits(rng,inclusion)
                if len(selected)>2 or len(selected)!=len(set(selected)):
                    raise AssertionError("Credit allocation invariant failed")
                for index in selected: counts[index] += 1
                unused_credits += missing
        opportunities_samples.append(total_opps)
        total_samples.append(sum(counts))
        for i,c in enumerate(counts):
            samples[i].append(c)
    summaries = []
    for r, vals in zip(players, samples):
        histogram = Counter(vals)
        summaries.append({"player_id": r["player_id"], "player_name": r["player_name"], "position": r.get("current_depth_position") or r.get("position_group"),
                          "baseline": number(r.get("role_point_xtc")), "mean": fmean(vals), "median": quantile(vals, .5),
                          "p10": quantile(vals, .1), "p90": quantile(vals, .9), "p_zero": histogram[0]/n,
                          "play_probability_assumption": number(availability.get(r["player_id"], 1)),
                          "histogram": [{"count": x, "p": histogram[x]/n} for x in range(max(vals)+1)]})
    matrix_ids = sorted(set([ia, ib] + list(range(min(6, len(players))))))
    matrix = [[correlation(samples[i], samples[j]) for j in matrix_ids] for i in matrix_ids]
    pa, pb = [line_probabilities(samples[i], line) for i,line in zip((ia,ib),lines)]
    joint = sum(a>lines[0] and b>lines[1] for a,b in zip(samples[ia],samples[ib]))/n
    return {"engine": "OMEGA_NEXT_JOINT_EVENT_LAB_1.0", "status": "UNTRAINED_SCENARIO", "target": TARGET,
            "game_id": game, "team": team, "draws": n, "seed": seed, "config": config, "players": summaries,
            "pair": {"players": [summaries[ia], summaries[ib]], "lines": lines, "probabilities": [pa,pb],
                     "joint_over": joint, "independent_over": pa["over"]*pb["over"], "correlation": correlation(samples[ia],samples[ib])},
            "correlation": {"players": [players[i]["player_name"] for i in matrix_ids], "matrix": matrix},
            "team": {"code": team, "expected_opportunities": fmean(opportunities_samples), "mean_credits": fmean(total_samples),
                     "max_credit_bound_pass": all(t <= 2*o for t,o in zip(total_samples,opportunities_samples)),
                     "unallocated_credits_per_draw": unused_credits/n},
            "family_credit_yields": dict(zip(FAMILIES, unbounded_yields)),
            "yield_cap_applied": any(x>2 for x in unbounded_yields),
            "neutral_mean_policy":"EXACT_INCLUSION_MARGINALS_WITH_MONTE_CARLO_ERROR",
            "monte_carlo_joint_se":math.sqrt(joint*(1-joint)/n),
            "assumptions": ["Saved role-track family rates anchor the simulation; no parameters have been fitted.",
                            "Participation defaults to 100% conditional on playing; supplied overrides are assumptions, not verified news.",
                            "The team opportunity/credit pool stays fixed when a player is removed; weights redistribute across represented teammates.",
                            "Random-order systematic allocation preserves neutral expected means and gives at most two distinct credits per opportunity; the dependence rule still needs historical validation.",
                            "Competition is applied only to the selected pair; a full personnel-package model is still required.",
                            "Monte Carlo correlations are scenario-dependent; they are not measured NFL correlations."]}

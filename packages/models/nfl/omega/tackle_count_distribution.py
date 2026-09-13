"""OMEGA 0.15 discrete tackle-count distribution utilities.

The independent model supplies a mean count (xTC). This module converts that
mean into a discrete probability mass function without reading sportsbook data.
Market-price helpers are pure downstream arithmetic and are never used in model
or distribution fitting.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

ROLE_TIERS = ("LOW", "ROTATIONAL", "STARTER", "EVERY_DOWN")
K_GRID = (0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 35.0, 60.0, 100.0, 200.0, 500.0)
THRESHOLD_LINES = tuple(x + 0.5 for x in range(0, 15))
MIN_ROLE_FIT_ROWS = 250


def role_tier(predicted_snap_share: float) -> str:
    s = min(1.0, max(0.0, float(predicted_snap_share)))
    if s < 0.35:
        return "LOW"
    if s < 0.65:
        return "ROTATIONAL"
    if s < 0.85:
        return "STARTER"
    return "EVERY_DOWN"


def poisson_logpmf(y: int, mean: float) -> float:
    if y < 0:
        return float("-inf")
    mu = max(0.0, float(mean))
    if mu == 0.0:
        return 0.0 if y == 0 else float("-inf")
    return y * math.log(mu) - mu - math.lgamma(y + 1.0)


def nb2_logpmf(y: int, mean: float, size: float) -> float:
    """Negative Binomial NB2 with E[Y]=mean, Var[Y]=mean + mean^2/size."""
    if y < 0:
        return float("-inf")
    mu = max(0.0, float(mean))
    k = float(size)
    if not math.isfinite(k) or k <= 0.0:
        raise ValueError("NB2 size must be finite and > 0")
    if mu == 0.0:
        return 0.0 if y == 0 else float("-inf")
    return (
        math.lgamma(y + k)
        - math.lgamma(k)
        - math.lgamma(y + 1.0)
        + k * math.log(k / (k + mu))
        + y * math.log(mu / (k + mu))
    )


def logpmf(y: int, mean: float, model: str, params: Mapping[str, float] | None = None, tier: str | None = None) -> float:
    m = str(model).upper()
    if m == "POISSON":
        return poisson_logpmf(y, mean)
    params = params or {}
    if m == "NB_GLOBAL":
        return nb2_logpmf(y, mean, float(params["globalSize"]))
    if m == "NB_ROLE":
        if tier is None:
            raise ValueError("NB_ROLE requires exposure role tier")
        size = float(params.get(f"size_{tier}", params["globalSize"]))
        return nb2_logpmf(y, mean, size)
    raise ValueError(f"unknown distribution model: {model}")


def cdf_at(k: int, mean: float, model: str, params: Mapping[str, float] | None = None, tier: str | None = None) -> float:
    if k < 0:
        return 0.0
    total = 0.0
    for y in range(k + 1):
        lp = logpmf(y, mean, model, params, tier)
        if math.isfinite(lp):
            total += math.exp(lp)
    return min(1.0, max(0.0, total))


def over_probability(line: float, mean: float, model: str, params: Mapping[str, float] | None = None, tier: str | None = None) -> float:
    floor_line = math.floor(float(line))
    return min(1.0, max(0.0, 1.0 - cdf_at(floor_line, mean, model, params, tier)))


def under_probability(line: float, mean: float, model: str, params: Mapping[str, float] | None = None, tier: str | None = None) -> float:
    return 1.0 - over_probability(line, mean, model, params, tier)


def american_break_even(price: int | float) -> float:
    a = float(price)
    if a == 0:
        raise ValueError("American odds cannot be zero")
    if a < 0:
        return (-a) / ((-a) + 100.0)
    return 100.0 / (a + 100.0)


def fair_american(probability: float) -> float:
    p = float(probability)
    if not 0.0 < p < 1.0:
        if p <= 0.0:
            return float("inf")
        return float("-inf")
    if p >= 0.5:
        return -100.0 * p / (1.0 - p)
    return 100.0 * (1.0 - p) / p


def expected_roi(probability: float, american_price: int | float) -> float:
    p = float(probability)
    a = float(american_price)
    if not 0.0 <= p <= 1.0 or a == 0:
        raise ValueError("invalid probability or American price")
    win_profit = 100.0 / abs(a) if a < 0 else a / 100.0
    return p * win_profit - (1.0 - p)


def proportional_devig(over_price: int | float, under_price: int | float) -> tuple[float, float]:
    po = american_break_even(over_price)
    pu = american_break_even(under_price)
    total = po + pu
    if total <= 0:
        raise ValueError("invalid two-way market")
    return po / total, pu / total


def fit_global_size(rows: Sequence[Mapping[str, object]], mean_key: str = "predicted_xtc", actual_key: str = "actual_xtc") -> float:
    best = None
    for size in K_GRID:
        nll = 0.0
        n = 0
        for r in rows:
            y = int(round(float(r[actual_key])))
            mu = max(0.0, float(r[mean_key]))
            lp = nb2_logpmf(y, mu, size)
            nll += 50.0 if not math.isfinite(lp) else -lp
            n += 1
        item = (nll / max(1, n), size)
        if best is None or item < best:
            best = item
    if best is None:
        raise ValueError("cannot fit NB size on empty rows")
    return float(best[1])


def fit_params(rows: Sequence[Mapping[str, object]], model: str, mean_key: str = "predicted_xtc", actual_key: str = "actual_xtc", tier_key: str = "role_tier") -> dict[str, float]:
    m = str(model).upper()
    if m == "POISSON":
        return {}
    g = fit_global_size(rows, mean_key, actual_key)
    if m == "NB_GLOBAL":
        return {"globalSize": g}
    if m == "NB_ROLE":
        out = {"globalSize": g}
        for tier in ROLE_TIERS:
            rr = [r for r in rows if str(r.get(tier_key) or "") == tier]
            out[f"n_{tier}"] = float(len(rr))
            out[f"size_{tier}"] = fit_global_size(rr, mean_key, actual_key) if len(rr) >= MIN_ROLE_FIT_ROWS else g
        return out
    raise ValueError(f"unknown distribution model: {model}")


def evaluate_rows(rows: Sequence[Mapping[str, object]], model: str, params: Mapping[str, float], mean_key: str = "predicted_xtc", actual_key: str = "actual_xtc", tier_key: str = "role_tier", lines: Iterable[float] = THRESHOLD_LINES) -> dict[str, float]:
    lines = tuple(float(x) for x in lines)
    nll = 0.0
    brier_sum = 0.0
    brier_n = 0
    count = 0
    for r in rows:
        y = int(round(float(r[actual_key])))
        mu = max(0.0, float(r[mean_key]))
        tier = str(r.get(tier_key) or "") or None
        lp = logpmf(y, mu, model, params, tier)
        nll += 50.0 if not math.isfinite(lp) else -lp
        for line in lines:
            p = over_probability(line, mu, model, params, tier)
            o = 1.0 if y > line else 0.0
            brier_sum += (p - o) ** 2
            brier_n += 1
        count += 1
    return {"n": float(count), "countNLL": nll / max(1, count), "thresholdBrier": brier_sum / max(1, brier_n)}


def threshold_calibration(rows: Sequence[Mapping[str, object]], model: str, params: Mapping[str, float], mean_key: str = "predicted_xtc", actual_key: str = "actual_xtc", tier_key: str = "role_tier", lines: Iterable[float] = THRESHOLD_LINES) -> list[dict[str, float]]:
    out = []
    for line in lines:
        probs, acts = [], []
        for r in rows:
            y = int(round(float(r[actual_key])))
            mu = max(0.0, float(r[mean_key]))
            tier = str(r.get(tier_key) or "") or None
            probs.append(over_probability(float(line), mu, model, params, tier))
            acts.append(1.0 if y > float(line) else 0.0)
        if not probs:
            continue
        pbar = sum(probs) / len(probs)
        abar = sum(acts) / len(acts)
        b = sum((p-a)**2 for p,a in zip(probs,acts)) / len(probs)
        out.append({"line": float(line), "n": float(len(probs)), "predictedOver": pbar, "actualOver": abar, "calibrationGap": pbar-abar, "brier": b})
    return out

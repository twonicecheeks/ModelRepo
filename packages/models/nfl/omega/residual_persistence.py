"""OMEGA 0.9 — H007 residual-persistence challenger.

Pre-registered mechanism H007 from OMEGA 0.1:
    some defenders may persistently over- or under-perform the frozen H008
    tackle-opportunity-footprint expectation because of stable player/role factors
    not fully represented by the current topology and exposure components.

This module deliberately treats the residual as a *shrunk player random intercept*,
not as a new football truth.  The correction is built only from strictly prior
H008 prediction errors and is allowed to select gamma=0 in development, which
collapses exactly back to H008.

No market data, sportsbook settlement convention, postseason, or OMEGA 2025 data
is used here.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.9.0"
LINEAGE = "omega-tackle-v0.9.0-h007-residual-persistence-2026-09-11"
HOLDOUT_SEASON = 2025
RESIDUAL_WINDOW = 8
ALPHA_GRID = (2.0, 4.0, 8.0, 16.0, 32.0)
GAMMA_GRID = (0.0, 0.25, 0.50, 0.75, 1.0)


def num(v: Any, default: float | None = None) -> float | None:
    if v in (None, ""):
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x else x


def as_int(v: Any) -> int:
    return int(round(float(num(v, 0.0) or 0.0)))


def _player_key(r: dict[str, Any]) -> str:
    return str(r.get("player_id") or "")


def _sort_key(r: dict[str, Any]) -> tuple[int, int, str, str]:
    return (
        as_int(r.get("season")),
        as_int(r.get("week")),
        str(r.get("game_id") or ""),
        _player_key(r),
    )


def build_strictly_lagged_residual_rows(
    prediction_rows: Sequence[dict[str, Any]],
    *,
    actual_key: str = "actual_xtc",
    baseline_key: str = "topology_xtc",
    window: int = RESIDUAL_WINDOW,
) -> list[dict[str, Any]]:
    """Attach strictly-prior player residual history to each H008 prediction row.

    All target rows for a season/week are emitted before any residual from that week
    is admitted to history. This is a hard same-week leakage guard.
    """
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in prediction_rows:
        season = as_int(r.get("season"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 row entered H007 residual history")
        if not (2017 <= season <= 2024):
            continue
        if not _player_key(r):
            continue
        by_week[(season, as_int(r.get("week")))].append(r)

    history: dict[str, list[float]] = defaultdict(list)
    out: list[dict[str, Any]] = []
    for season, week in sorted(by_week):
        batch = sorted(by_week[(season, week)], key=_sort_key)
        # Emit first; do not let another row in the same week enter history.
        for r in batch:
            pid = _player_key(r)
            h = history[pid][-window:]
            z = dict(r)
            z["h007_prior_residual_games"] = len(h)
            z["h007_prior_residual_mean"] = fmean(h) if h else 0.0
            z["h007_prior_residual_last"] = h[-1] if h else 0.0
            z["h007_prior_residual_abs_mean"] = fmean(abs(x) for x in h) if h else 0.0
            out.append(z)
        # Update only after the full week's target rows were emitted.
        for r in batch:
            pid = _player_key(r)
            actual = float(num(r.get(actual_key), 0.0) or 0.0)
            pred = float(num(r.get(baseline_key), 0.0) or 0.0)
            history[pid].append(actual - pred)
    return out


def apply_residual_correction(
    rows: Iterable[dict[str, Any]],
    *,
    alpha_games: float,
    gamma: float,
    baseline_key: str = "topology_xtc",
    out_key: str = "h007_xtc",
) -> list[dict[str, Any]]:
    """Apply a shrunk additive player residual correction.

    shrunk_residual = mean(last-8 H008 residuals) * n/(n+alpha_games)
    H007 = max(0, H008 + gamma * shrunk_residual)

    gamma=0 is an explicit null challenger and must equal H008 exactly.
    """
    if alpha_games <= 0:
        raise ValueError("alpha_games must be > 0")
    if gamma < 0 or gamma > 1:
        raise ValueError("gamma must be in [0,1]")
    out: list[dict[str, Any]] = []
    for r in rows:
        z = dict(r)
        n = max(0, as_int(r.get("h007_prior_residual_games")))
        mean_resid = float(num(r.get("h007_prior_residual_mean"), 0.0) or 0.0)
        weight = n / (n + float(alpha_games)) if n > 0 else 0.0
        shrunk = weight * mean_resid
        base = max(0.0, float(num(r.get(baseline_key), 0.0) or 0.0))
        correction = float(gamma) * shrunk
        z["h007_residual_alpha_games"] = float(alpha_games)
        z["h007_residual_gamma"] = float(gamma)
        z["h007_history_weight"] = weight
        z["h007_shrunk_residual"] = shrunk
        z["h007_correction"] = correction
        z[out_key] = max(0.0, base + correction)
        out.append(z)
    return out


def mae(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> float:
    if not rows:
        raise ValueError("empty rows")
    return fmean(abs(float(num(r.get(actual), 0.0) or 0.0) - float(num(r.get(pred), 0.0) or 0.0)) for r in rows)


def rmse(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> float:
    if not rows:
        raise ValueError("empty rows")
    return (fmean((float(num(r.get(actual), 0.0) or 0.0) - float(num(r.get(pred), 0.0) or 0.0)) ** 2 for r in rows)) ** 0.5


def corr(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx = fmean(xs); my = fmean(ys)
    sxx = sum((x-mx)**2 for x in xs); syy = sum((y-my)**2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys)) / (sxx*syy) ** 0.5


def residual_persistence_diagnostics(
    rows: Sequence[dict[str, Any]],
    *,
    actual_key: str = "actual_xtc",
    baseline_key: str = "topology_xtc",
) -> dict[str, float | int]:
    eligible = [r for r in rows if as_int(r.get("h007_prior_residual_games")) > 0]
    if not eligible:
        return {"n": 0, "corrPriorMeanToCurrentResidual": 0.0, "corrLastResidualToCurrentResidual": 0.0}
    current = [float(num(r.get(actual_key), 0.0) or 0.0) - float(num(r.get(baseline_key), 0.0) or 0.0) for r in eligible]
    prior_mean = [float(num(r.get("h007_prior_residual_mean"), 0.0) or 0.0) for r in eligible]
    prior_last = [float(num(r.get("h007_prior_residual_last"), 0.0) or 0.0) for r in eligible]
    return {
        "n": len(eligible),
        "corrPriorMeanToCurrentResidual": corr(prior_mean, current),
        "corrLastResidualToCurrentResidual": corr(prior_last, current),
    }

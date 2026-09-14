"""OMEGA 0.2.3 probabilistic snap-share challenger.

Extends the existing H012 point exposure model without changing frozen OMEGA.
A strictly pre-2024 empirical residual distribution is conditioned on pregame
position, history depth, and predicted role state.  The object being forecast is
P(defensive snap share | player records a defensive snap); availability/inactive
risk remains a separate upstream gate.

No market data, current-game outcomes, or 2025 outcomes are used here.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import floor
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.2.3"
LINEAGE = "omega-tackle-v0.2.3-snap-share-distribution-challenger-2026-09-14"
CALIBRATION_YEARS = (2019, 2020, 2021, 2022, 2023)
MIN_POOL = 80
ROLE_THRESHOLDS = (0.35, 0.65, 0.85)


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def history_band(prior_games: int) -> str:
    n = int(prior_games)
    if n <= 0:
        return "COLD_0"
    if n <= 2:
        return "THIN_1_2"
    if n <= 8:
        return "DEVELOPING_3_8"
    return "ESTABLISHED_9_PLUS"


def role_tier(share: float) -> str:
    x = float(share)
    if x < ROLE_THRESHOLDS[0]:
        return "LOW"
    if x < ROLE_THRESHOLDS[1]:
        return "ROTATIONAL"
    if x < ROLE_THRESHOLDS[2]:
        return "STARTER"
    return "EVERY_DOWN"


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires non-empty values")
    xs = sorted(float(x) for x in values)
    p = max(0.0, min(1.0, float(q))) * (len(xs) - 1)
    lo = int(floor(p)); hi = min(len(xs) - 1, lo + 1)
    if lo == hi:
        return xs[lo]
    w = p - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def empirical_crps(samples: Sequence[float], actual: float) -> float:
    """CRPS for an equally weighted empirical distribution in O(n log n)."""
    if not samples:
        raise ValueError("CRPS requires samples")
    xs = sorted(float(x) for x in samples)
    n = len(xs)
    y = float(actual)
    first = fmean(abs(x - y) for x in xs)
    pair_half = sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(xs)) / (n * n)
    return first - pair_half


def mid_pit(samples: Sequence[float], actual: float, tol: float = 1e-12) -> float:
    if not samples:
        raise ValueError("PIT requires samples")
    y = float(actual)
    less = sum(x < y - tol for x in samples)
    equal = sum(abs(x - y) <= tol for x in samples)
    return (less + 0.5 * equal) / len(samples)


def _position_group(row: dict[str, Any]) -> str:
    pg = str(row.get("position_group") or "UNK").upper()
    return pg if pg in {"DB", "LB", "DL"} else "OTHER"


def context_candidates(row: dict[str, Any], center: float) -> tuple[tuple[str, ...], ...]:
    pg = _position_group(row)
    hb = history_band(int(float(row.get("prior_games") or 0)))
    rt = role_tier(center)
    # Most specific to most robust fallback.  Every key contains only information
    # available before the target game.
    return (
        ("P_H_R", pg, hb, rt),
        ("P_R", pg, rt),
        ("H_R", hb, rt),
        ("R", rt),
        ("P", pg),
        ("GLOBAL",),
    )


@dataclass(frozen=True)
class ResidualObservation:
    game_id: str
    season: int
    week: int
    player_id: str
    position_group: str
    prior_games: int
    center: float
    actual: float
    residual: float


class EmpiricalResidualCalibrator:
    def __init__(self, observations: Iterable[ResidualObservation], *, min_pool: int = MIN_POOL):
        self.min_pool = int(min_pool)
        if self.min_pool < 10:
            raise ValueError("min_pool must be at least 10")
        pools: dict[tuple[str, ...], list[float]] = defaultdict(list)
        self.observations = list(observations)
        if not self.observations:
            raise ValueError("cannot build empty residual calibrator")
        for o in self.observations:
            row = {"position_group": o.position_group, "prior_games": o.prior_games}
            for key in context_candidates(row, o.center):
                pools[key].append(float(o.residual))
        self.pools = {k: tuple(v) for k, v in pools.items()}
        if len(self.pools.get(("GLOBAL",), ())) != len(self.observations):
            raise AssertionError("global residual pool coverage mismatch")

    def select_pool(self, row: dict[str, Any], center: float) -> tuple[tuple[str, ...], tuple[float, ...]]:
        candidates = context_candidates(row, center)
        for key in candidates[:-1]:
            vals = self.pools.get(key, ())
            if len(vals) >= self.min_pool:
                return key, vals
        vals = self.pools.get(("GLOBAL",), ())
        if not vals:
            raise ValueError("global residual pool missing")
        return ("GLOBAL",), vals

    def samples(self, row: dict[str, Any], center: float) -> tuple[tuple[str, ...], list[float]]:
        key, residuals = self.select_pool(row, center)
        return key, [clip01(float(center) + r) for r in residuals]

    def summarize(self, row: dict[str, Any], center: float, actual: float | None = None) -> dict[str, Any]:
        key, samples = self.samples(row, center)
        n = len(samples)
        low = sum(x < 0.35 for x in samples) / n
        rotational = sum(0.35 <= x < 0.65 for x in samples) / n
        starter = sum(0.65 <= x < 0.85 for x in samples) / n
        every = sum(x >= 0.85 for x in samples) / n
        out: dict[str, Any] = {
            "point_center": clip01(center),
            "distribution_mean": fmean(samples),
            "distribution_median": percentile(samples, 0.50),
            "q05": percentile(samples, 0.05),
            "q10": percentile(samples, 0.10),
            "q25": percentile(samples, 0.25),
            "q75": percentile(samples, 0.75),
            "q90": percentile(samples, 0.90),
            "q95": percentile(samples, 0.95),
            "p_low": low,
            "p_rotational": rotational,
            "p_starter": starter,
            "p_every_down": every,
            "p_ge_035": 1.0 - low,
            "p_ge_065": starter + every,
            "p_ge_085": every,
            "pool_key": "|".join(key),
            "pool_n": n,
        }
        if actual is not None:
            y = clip01(actual)
            out.update({
                "actual": y,
                "crps": empirical_crps(samples, y),
                "pit": mid_pit(samples, y),
                "covered_50": int(out["q25"] <= y <= out["q75"]),
                "covered_80": int(out["q10"] <= y <= out["q90"]),
                "covered_90": int(out["q05"] <= y <= out["q95"]),
                "width_50": out["q75"] - out["q25"],
                "width_80": out["q90"] - out["q10"],
                "width_90": out["q95"] - out["q05"],
                "brier_ge_035": (out["p_ge_035"] - int(y >= 0.35)) ** 2,
                "brier_ge_065": (out["p_ge_065"] - int(y >= 0.65)) ** 2,
                "brier_ge_085": (out["p_ge_085"] - int(y >= 0.85)) ** 2,
            })
        return out

    def pool_summary(self) -> list[dict[str, Any]]:
        rows = []
        for key, vals in sorted(self.pools.items()):
            if not vals:
                continue
            rows.append({
                "pool_key": "|".join(key),
                "n": len(vals),
                "residual_mean": fmean(vals),
                "residual_q10": percentile(vals, .10),
                "residual_q50": percentile(vals, .50),
                "residual_q90": percentile(vals, .90),
            })
        return rows


def make_observation(row: dict[str, Any], center: float) -> ResidualObservation:
    actual = float(row["actual_snap_share"])
    return ResidualObservation(
        game_id=str(row.get("game_id") or ""),
        season=int(row.get("season") or 0),
        week=int(row.get("week") or 0),
        player_id=str(row.get("player_id") or ""),
        position_group=_position_group(row),
        prior_games=int(float(row.get("prior_games") or 0)),
        center=clip01(center),
        actual=clip01(actual),
        residual=clip01(actual) - clip01(center),
    )

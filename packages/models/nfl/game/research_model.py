"""Leakage-safe NFL game research model utilities for MODEL 2.9.0 Phase 2A.

This module intentionally implements only historical development tooling. It does not
wire a production/runtime probability into the Chrome extension and does not read
sportsbook prices. The 2025 holdout is excluded from model selection and candidate
fitting by the Phase 2A builder.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, sqrt
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.1.0"
LINEAGE = "nfl-game-v0.1.0-historical-development-2026-09-08"
CALIBRATION_STATUS = "DEVELOPMENT_ONLY_HOLDOUT_UNTOUCHED"
FEATURE_SET_VERSION = "nfl-pregame-team-differentials-v0.1.0"
HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

# The feature family is intentionally pre-registered before holdout evaluation.
TEAM_METRICS = (
    "off_dropback_epa",
    "off_rush_epa",
    "off_success_rate",
    "off_cpoe",
    "off_sack_rate",
    "off_explosive_pass_rate",
    "off_explosive_rush_rate",
    "off_turnover_rate",
    "def_dropback_epa_allowed",
    "def_rush_epa_allowed",
    "def_success_rate_allowed",
    "def_sack_rate_generated",
    "def_explosive_pass_rate_allowed",
    "def_explosive_rush_rate_allowed",
    "def_takeaway_rate",
)
HORIZONS = ("prior_season", "std", "last4", "last8")
L2_GRID = (0.03, 0.1, 0.3)


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _clip_prob(p: float) -> float:
    return min(1.0 - 1e-12, max(1e-12, float(p)))


def sigmoid(z: float) -> float:
    if z >= 0:
        ez = exp(-min(z, 40.0))
        return 1.0 / (1.0 + ez)
    ez = exp(max(z, -40.0))
    return ez / (1.0 + ez)


def base_feature_names() -> tuple[str, ...]:
    names = ["rest_days_diff", "neutral_site", "games_available_diff"]
    for horizon in HORIZONS:
        for metric in TEAM_METRICS:
            names.append(f"{horizon}_{metric}_diff")
    return tuple(names)


def expanded_feature_names() -> tuple[str, ...]:
    out: list[str] = []
    for name in base_feature_names():
        out.append(name)
        out.append(f"missing__{name}")
    return tuple(out)


def _diff(row: dict[str, Any], stem: str) -> float | None:
    h = _num(row.get(f"home_{stem}"))
    a = _num(row.get(f"away_{stem}"))
    if h is None or a is None:
        return None
    return h - a


def vectorize_feature_row(row: dict[str, Any]) -> list[float | None]:
    """Create the pre-registered home-minus-away research feature vector.

    Missing base features are left as ``None`` and paired with an explicit missingness
    indicator. Training-time imputation is performed from development data only.
    """
    vals: dict[str, float | None] = {}
    hr = _num(row.get("home_rest_days"))
    ar = _num(row.get("away_rest_days"))
    vals["rest_days_diff"] = None if hr is None or ar is None else hr - ar

    neutral_raw = row.get("neutral_site")
    if neutral_raw in (None, ""):
        vals["neutral_site"] = None
    elif isinstance(neutral_raw, bool):
        vals["neutral_site"] = 1.0 if neutral_raw else 0.0
    else:
        vals["neutral_site"] = 1.0 if str(neutral_raw).strip().lower() in {"1", "true", "yes"} else 0.0

    vals["games_available_diff"] = _diff(row, "games_available")
    for horizon in HORIZONS:
        for metric in TEAM_METRICS:
            vals[f"{horizon}_{metric}_diff"] = _diff(row, f"{horizon}_{metric}")

    out: list[float | None] = []
    for name in base_feature_names():
        v = vals[name]
        out.append(v)
        out.append(1.0 if v is None else 0.0)
    return out


@dataclass(frozen=True)
class Example:
    game_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    x: tuple[float | None, ...]
    y: int


@dataclass
class LogisticModel:
    feature_names: tuple[str, ...]
    means: list[float]
    scales: list[float]
    intercept: float
    coefficients: list[float]
    l2: float
    iterations: int
    final_gradient_norm: float

    def _transform(self, x: Sequence[float | None]) -> list[float]:
        if len(x) != len(self.feature_names):
            raise ValueError("feature vector length mismatch")
        out: list[float] = []
        for i, v in enumerate(x):
            n = self.means[i] if v is None else float(v)
            out.append((n - self.means[i]) / self.scales[i])
        return out

    def predict_proba(self, x: Sequence[float | None]) -> float:
        z = self.intercept
        tx = self._transform(x)
        for w, v in zip(self.coefficients, tx):
            z += w * v
        return sigmoid(z)

    def to_dict(self) -> dict[str, Any]:
        return {
            "modelClass": "STANDARDIZED_L2_LOGISTIC",
            "version": VERSION,
            "lineage": LINEAGE,
            "calibrationStatus": CALIBRATION_STATUS,
            "featureSetVersion": FEATURE_SET_VERSION,
            "featureNames": list(self.feature_names),
            "means": self.means,
            "scales": self.scales,
            "intercept": self.intercept,
            "coefficients": self.coefficients,
            "l2": self.l2,
            "iterations": self.iterations,
            "finalGradientNorm": self.final_gradient_norm,
        }


def _fit_stats(examples: Sequence[Example]) -> tuple[list[float], list[float]]:
    if not examples:
        raise ValueError("no training examples")
    p = len(examples[0].x)
    means: list[float] = []
    scales: list[float] = []
    for j in range(p):
        good = [float(e.x[j]) for e in examples if e.x[j] is not None]
        mean = fmean(good) if good else 0.0
        var = fmean([(x - mean) ** 2 for x in good]) if len(good) > 1 else 0.0
        scale = sqrt(var) if var > 1e-12 else 1.0
        means.append(mean)
        scales.append(scale)
    return means, scales


def fit_logistic(
    examples: Sequence[Example],
    *,
    l2: float,
    max_iter: int = 140,
    learning_rate: float = 0.12,
    tolerance: float = 2e-5,
) -> LogisticModel:
    if not examples:
        raise ValueError("cannot fit empty dataset")
    if l2 < 0:
        raise ValueError("l2 must be nonnegative")
    names = expanded_feature_names()
    if len(examples[0].x) != len(names):
        raise ValueError("unexpected feature vector schema")
    means, scales = _fit_stats(examples)
    matrix: list[list[float]] = []
    ys: list[int] = []
    for e in examples:
        if e.y not in (0, 1):
            raise ValueError("binary target required")
        if len(e.x) != len(names):
            raise ValueError("inconsistent feature vector length")
        matrix.append([
            ((means[j] if v is None else float(v)) - means[j]) / scales[j]
            for j, v in enumerate(e.x)
        ])
        ys.append(e.y)

    ybar = min(1 - 1e-6, max(1e-6, fmean(ys)))
    intercept = log(ybar / (1.0 - ybar))
    w = [0.0] * len(names)
    n = float(len(examples))
    grad_norm = float("inf")
    completed = 0
    for it in range(1, max_iter + 1):
        gi = 0.0
        gw = [0.0] * len(w)
        for row, y in zip(matrix, ys):
            z = intercept
            for a, b in zip(w, row):
                z += a * b
            err = sigmoid(z) - y
            gi += err
            for j, xj in enumerate(row):
                gw[j] += err * xj
        gi /= n
        for j in range(len(gw)):
            gw[j] = gw[j] / n + l2 * w[j]
        grad_norm = sqrt(gi * gi + sum(g * g for g in gw))
        completed = it
        if grad_norm < tolerance:
            break
        # Smooth decay keeps the pure-Python optimizer stable across seasons while
        # preserving deterministic fitting with no external ML dependency.
        step = learning_rate / sqrt(1.0 + (it - 1) / 75.0)
        intercept -= step * gi
        for j in range(len(w)):
            w[j] -= step * gw[j]

    return LogisticModel(
        feature_names=names,
        means=means,
        scales=scales,
        intercept=intercept,
        coefficients=w,
        l2=l2,
        iterations=completed,
        final_gradient_norm=grad_norm,
    )


def brier_score(ys: Sequence[int], ps: Sequence[float]) -> float:
    if not ys or len(ys) != len(ps):
        raise ValueError("non-empty equally sized targets/probabilities required")
    return fmean((float(p) - int(y)) ** 2 for y, p in zip(ys, ps))


def log_loss(ys: Sequence[int], ps: Sequence[float]) -> float:
    if not ys or len(ys) != len(ps):
        raise ValueError("non-empty equally sized targets/probabilities required")
    return -fmean(y * log(_clip_prob(p)) + (1 - y) * log(_clip_prob(1 - p)) for y, p in zip(ys, ps))


def accuracy(ys: Sequence[int], ps: Sequence[float]) -> float:
    if not ys or len(ys) != len(ps):
        raise ValueError("non-empty equally sized targets/probabilities required")
    return sum((p >= 0.5) == bool(y) for y, p in zip(ys, ps)) / len(ys)


def calibration_bins(ys: Sequence[int], ps: Sequence[float], bins: int = 10) -> list[dict[str, Any]]:
    if bins <= 0:
        raise ValueError("bins must be positive")
    buckets: list[list[tuple[int, float]]] = [[] for _ in range(bins)]
    for y, p in zip(ys, ps):
        idx = min(bins - 1, int(_clip_prob(p) * bins))
        buckets[idx].append((int(y), float(p)))
    out: list[dict[str, Any]] = []
    for i, bucket in enumerate(buckets):
        out.append({
            "bin": i,
            "from": i / bins,
            "to": (i + 1) / bins,
            "n": len(bucket),
            "meanPrediction": fmean(p for _, p in bucket) if bucket else None,
            "observedRate": fmean(y for y, _ in bucket) if bucket else None,
        })
    return out


def metric_summary(ys: Sequence[int], ps: Sequence[float]) -> dict[str, float | int]:
    return {
        "n": len(ys),
        "brier": brier_score(ys, ps),
        "logLoss": log_loss(ys, ps),
        "accuracy": accuracy(ys, ps),
        "meanPrediction": fmean(ps),
        "observedHomeWinRate": fmean(ys),
    }


def constant_home_rate(train: Sequence[Example], test: Sequence[Example]) -> list[float]:
    if not train:
        raise ValueError("constant baseline needs training data")
    p = fmean(e.y for e in train)
    return [p] * len(test)


def elo_online_predictions(
    ordered_examples: Sequence[Example],
    *,
    k: float = 20.0,
    home_advantage: float = 55.0,
    season_regression: float = 0.33,
) -> list[float]:
    """Transparent online Elo-style baseline, predicting before each outcome update."""
    ratings: dict[str, float] = {}
    last_season: int | None = None
    out: list[float] = []
    for e in ordered_examples:
        if last_season is None or e.season != last_season:
            if last_season is not None:
                for team in list(ratings):
                    ratings[team] = 1500.0 + (ratings[team] - 1500.0) * (1.0 - season_regression)
            last_season = e.season
        rh = ratings.get(e.home_team, 1500.0)
        ra = ratings.get(e.away_team, 1500.0)
        expected = 1.0 / (1.0 + 10.0 ** (-((rh + home_advantage) - ra) / 400.0))
        out.append(expected)
        delta = k * (e.y - expected)
        ratings[e.home_team] = rh + delta
        ratings[e.away_team] = ra - delta
    return out


def walk_forward_l2(
    examples: Sequence[Example],
    *,
    validation_seasons: Sequence[int],
    l2_grid: Sequence[float] = L2_GRID,
) -> dict[str, Any]:
    """Tune regularization only on development seasons with chronological folds."""
    ordered = sorted(examples, key=lambda e: (e.season, e.week, e.game_id))
    scores: list[dict[str, Any]] = []
    for l2 in l2_grid:
        pooled_y: list[int] = []
        pooled_p: list[float] = []
        folds: list[dict[str, Any]] = []
        for season in validation_seasons:
            train = [e for e in ordered if e.season < season]
            test = [e for e in ordered if e.season == season]
            if not train or not test:
                continue
            model = fit_logistic(train, l2=float(l2))
            ps = [model.predict_proba(e.x) for e in test]
            ys = [e.y for e in test]
            m = metric_summary(ys, ps)
            folds.append({"season": season, **m})
            pooled_y.extend(ys)
            pooled_p.extend(ps)
        if not pooled_y:
            raise ValueError("walk-forward validation produced no folds")
        scores.append({"l2": float(l2), "pooled": metric_summary(pooled_y, pooled_p), "folds": folds})
    scores.sort(key=lambda r: (r["pooled"]["logLoss"], r["pooled"]["brier"], r["l2"]))
    return {"selectedL2": scores[0]["l2"], "candidates": scores}


def examples_from_rows(
    feature_rows: Iterable[dict[str, Any]],
    targets_by_game: dict[str, int],
    *,
    allowed_seasons: set[int],
    game_type: str = "REG",
) -> list[Example]:
    out: list[Example] = []
    for row in feature_rows:
        season = int(row["season"])
        if season not in allowed_seasons or str(row.get("game_type") or "") != game_type:
            continue
        gid = str(row["game_id"])
        y = targets_by_game.get(gid)
        if y not in (0, 1):
            continue
        out.append(Example(
            game_id=gid,
            season=season,
            week=int(row["week"]),
            home_team=str(row["home_team"]).upper(),
            away_team=str(row["away_team"]).upper(),
            x=tuple(vectorize_feature_row(row)),
            y=int(y),
        ))
    out.sort(key=lambda e: (e.season, e.week, e.game_id))
    return out

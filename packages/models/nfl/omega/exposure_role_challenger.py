"""OMEGA 0.2.2 exposure-role challenger.

Single preregistered mechanism: H012 — improve player defensive exposure/snap share
prediction using strictly lagged role-state features. No tackle-opportunity or market
features are introduced in this phase.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import log1p, sqrt
from statistics import fmean
from typing import Any, Sequence

VERSION = "0.2.2"
LINEAGE = "omega-tackle-v0.2.2-exposure-role-challenger-2026-09-11"
HOLDOUT_SEASON = 2025
L2_GRID = (0.01, 0.03, 0.1, 0.3, 1.0, 3.0)
FOLDS = (2021, 2022, 2023)

FEATURE_NAMES = (
    "position_prior_snap_share",
    "prior_games_cap8",
    "prior_games_log",
    "last1_snap_share",
    "last2_snap_share_mean",
    "last4_snap_share_mean",
    "last8_snap_share_mean",
    "last4_snap_share_std",
    "last4_snap_share_min",
    "last4_snap_share_max",
    "last1_minus_last4",
    "last2_minus_last8",
    "position_DB",
    "position_LB",
    "position_DL",
    "position_OTHER",
    "cold_start",
    "one_prior_game",
)


def num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    x = num(v)
    if x is not None:
        return int(x) != 0
    return str(v or "").strip().lower() in {"true", "yes", "y", "t"}


def normalize_pct(v: Any) -> float | None:
    x = num(v)
    if x is None or x < 0:
        return None
    if x > 1.5:
        x /= 100.0
    if x > 1.05:
        return None
    return min(1.0, x)


def mean_or(xs: Sequence[float], fallback: float) -> float:
    return fmean(xs) if xs else float(fallback)


def std_or_zero(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = fmean(xs)
    return sqrt(fmean((x - m) ** 2 for x in xs))


def mae(actual: Sequence[float], pred: Sequence[float]) -> float:
    if not actual or len(actual) != len(pred):
        raise ValueError("non-empty equal vectors required")
    return fmean(abs(a - p) for a, p in zip(actual, pred))


def rmse(actual: Sequence[float], pred: Sequence[float]) -> float:
    if not actual or len(actual) != len(pred):
        raise ValueError("non-empty equal vectors required")
    return sqrt(fmean((a - p) ** 2 for a, p in zip(actual, pred)))


def canonical_position_group(r: dict[str, Any]) -> str:
    pg = str(r.get("position_group") or "").strip().upper()
    if pg:
        if pg in {"DB", "CB", "S", "SAFETY"}: return "DB"
        if pg in {"LB", "ILB", "OLB", "MLB"}: return "LB"
        if pg in {"DL", "DE", "DT", "NT", "EDGE"}: return "DL"
        return pg
    pos = str(r.get("position") or "").strip().upper()
    if pos in {"CB", "S", "FS", "SS", "DB"}: return "DB"
    if pos in {"LB", "ILB", "OLB", "MLB"}: return "LB"
    if pos in {"DE", "DT", "NT", "DL", "EDGE"}: return "DL"
    return pos or "UNK"


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    aug = [list(map(float, row)) + [float(rhs)] for row, rhs in zip(a, b)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("singular linear system")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        p = aug[col][col]
        aug[col] = [x / p for x in aug[col]]
        for r in range(n):
            if r == col:
                continue
            f = aug[r][col]
            if abs(f) < 1e-18:
                continue
            aug[r] = [x - f*y for x, y in zip(aug[r], aug[col])]
    return [aug[i][-1] for i in range(n)]


@dataclass
class RidgeModel:
    feature_names: tuple[str, ...]
    means: list[float]
    scales: list[float]
    intercept: float
    coefficients: list[float]
    l2: float

    def predict_raw(self, row: dict[str, Any]) -> float:
        z = self.intercept
        for i, name in enumerate(self.feature_names):
            z += self.coefficients[i] * ((float(row[name]) - self.means[i]) / self.scales[i])
        return z

    def predict(self, row: dict[str, Any]) -> float:
        return max(0.0, min(1.0, self.predict_raw(row)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "modelClass": "STANDARDIZED_L2_RIDGE_CLIPPED_0_1",
            "version": VERSION,
            "lineage": LINEAGE,
            "featureNames": list(self.feature_names),
            "means": self.means,
            "scales": self.scales,
            "intercept": self.intercept,
            "coefficients": self.coefficients,
            "l2": self.l2,
            "target": "actual_snap_share",
        }


def fit_ridge(rows: Sequence[dict[str, Any]], l2: float) -> RidgeModel:
    if not rows:
        raise ValueError("cannot fit empty exposure model")
    p = len(FEATURE_NAMES)
    xs = [[float(r[n]) for n in FEATURE_NAMES] for r in rows]
    ys = [float(r["actual_snap_share"]) for r in rows]
    means = [fmean(x[j] for x in xs) for j in range(p)]
    scales: list[float] = []
    for j in range(p):
        var = fmean((x[j] - means[j]) ** 2 for x in xs)
        scales.append(sqrt(var) if var > 1e-12 else 1.0)
    zx = [[(x[j]-means[j])/scales[j] for j in range(p)] for x in xs]
    ybar = fmean(ys)
    yc = [y-ybar for y in ys]
    xtx = [[0.0]*p for _ in range(p)]
    xty = [0.0]*p
    n = float(len(rows))
    for x, y in zip(zx, yc):
        for j in range(p):
            xty[j] += x[j]*y/n
            for k in range(p):
                xtx[j][k] += x[j]*x[k]/n
    for j in range(p):
        xtx[j][j] += float(l2)
    coefs = _solve_linear(xtx, xty)
    return RidgeModel(FEATURE_NAMES, means, scales, ybar, coefs, float(l2))


def _snap_share_from_row(r: dict[str, Any], team_snap_totals: dict[tuple[str, str], float]) -> float | None:
    pct = normalize_pct(r.get("defense_pct"))
    if pct is not None:
        return pct
    snaps = num(r.get("defense_snaps"))
    total = team_snap_totals.get((str(r.get("game_id") or ""), str(r.get("team") or "")))
    if snaps is None or total is None or total <= 0:
        return None
    return max(0.0, min(1.0, snaps/total))


def build_exposure_pregame_rows(
    exposure_rows: Sequence[dict[str, Any]],
    team_snap_totals: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    """Strictly lagged player role-state rows.

    Player history is updated only after the whole week is emitted. The target-game
    row supplies identity/position and the outcome only; no target-game snap value is
    used in features.
    """
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in exposure_rows:
        if not truthy(r.get("eligible_standard_rate_fit")):
            continue
        season = int(float(r.get("season") or 0)); week = int(float(r.get("week") or 0))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 row entered exposure challenger")
        if 2016 <= season <= 2024:
            by_week[(season, week)].append(r)

    player_hist: dict[str, list[float]] = defaultdict(list)
    pos_sum: dict[str, float] = defaultdict(float)
    pos_n: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []

    for season, week in sorted(by_week):
        batch = by_week[(season, week)]
        if season >= 2017:
            for r in batch:
                pid = str(r.get("player_id") or "")
                if not pid:
                    continue
                actual = _snap_share_from_row(r, team_snap_totals)
                if actual is None:
                    continue
                pg = canonical_position_group(r)
                prior = pos_sum[pg]/pos_n[pg] if pos_n[pg] else 0.35
                h = player_hist[pid]
                last1 = h[-1] if h else prior
                l2 = h[-2:]
                l4 = h[-4:]
                l8 = h[-8:]
                m2 = mean_or(l2, prior)
                m4 = mean_or(l4, prior)
                m8 = mean_or(l8, prior)
                s4 = std_or_zero(l4)
                mn4 = min(l4) if l4 else prior
                mx4 = max(l4) if l4 else prior
                row = {
                    "game_id": str(r.get("game_id") or ""),
                    "season": season,
                    "week": week,
                    "team": str(r.get("team") or ""),
                    "opponent": str(r.get("opponent") or ""),
                    "player_id": pid,
                    "display_name": str(r.get("display_name") or ""),
                    "position": str(r.get("position") or ""),
                    "position_group": pg,
                    "actual_snap_share": actual,
                    "actual_defensive_snaps": float(num(r.get("defense_snaps")) or 0.0),
                    "prior_games": len(h),
                    "baseline_last4_snap_share": m4,
                    "position_prior_snap_share": prior,
                    "prior_games_cap8": min(8, len(h))/8.0,
                    "prior_games_log": log1p(len(h)),
                    "last1_snap_share": last1,
                    "last2_snap_share_mean": m2,
                    "last4_snap_share_mean": m4,
                    "last8_snap_share_mean": m8,
                    "last4_snap_share_std": s4,
                    "last4_snap_share_min": mn4,
                    "last4_snap_share_max": mx4,
                    "last1_minus_last4": last1-m4,
                    "last2_minus_last8": m2-m8,
                    "position_DB": 1.0 if pg == "DB" else 0.0,
                    "position_LB": 1.0 if pg == "LB" else 0.0,
                    "position_DL": 1.0 if pg == "DL" else 0.0,
                    "position_OTHER": 1.0 if pg not in {"DB","LB","DL"} else 0.0,
                    "cold_start": 1.0 if len(h) == 0 else 0.0,
                    "one_prior_game": 1.0 if len(h) == 1 else 0.0,
                }
                rows.append(row)
        # update only after all rows in target week were emitted
        for r in batch:
            pid = str(r.get("player_id") or "")
            if not pid:
                continue
            share = _snap_share_from_row(r, team_snap_totals)
            if share is None:
                continue
            pg = canonical_position_group(r)
            player_hist[pid].append(share)
            pos_sum[pg] += share
            pos_n[pg] += 1
    return rows


def choose_l2(rows: Sequence[dict[str, Any]], folds: Sequence[int] = FOLDS) -> tuple[float, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    for lam in L2_GRID:
        mas: list[float] = []
        rms: list[float] = []
        baseline_mas: list[float] = []
        for year in folds:
            train = [r for r in rows if 2017 <= int(r["season"]) < year]
            val = [r for r in rows if int(r["season"]) == year]
            if not train or not val:
                continue
            m = fit_ridge(train, lam)
            y = [float(r["actual_snap_share"]) for r in val]
            p = [m.predict(r) for r in val]
            b = [float(r["baseline_last4_snap_share"]) for r in val]
            mas.append(mae(y,p)); rms.append(rmse(y,p)); baseline_mas.append(mae(y,b))
        if mas:
            results.append({
                "l2": lam,
                "folds": len(mas),
                "meanMAE": fmean(mas),
                "meanRMSE": fmean(rms),
                "baselineLast4MeanMAE": fmean(baseline_mas),
                "maeImprovementVsLast4": fmean(baseline_mas)-fmean(mas),
            })
    if not results:
        raise ValueError("no chronological exposure folds available")
    results.sort(key=lambda x: (x["meanMAE"], x["meanRMSE"], x["l2"]))
    return float(results[0]["l2"]), results

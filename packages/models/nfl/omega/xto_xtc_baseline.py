"""OMEGA 0.2 transparent xTO/xTC research baseline.

This module is intentionally independent of sportsbook prices.  It provides:
* team-level expected defensive snap and tackle-opportunity models;
* player-level expected standard defensive tackle-credit baseline;
* chronological/as-of feature construction primitives;
* transparent ridge regression and count-error metrics.

The 2025 OMEGA tackle holdout is outside the 0.2 development/validation universe.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt
from statistics import fmean, median
from typing import Any, Iterable, Sequence

VERSION = "0.2.0"
LINEAGE = "omega-tackle-v0.2.0-xto-xtc-baseline-2026-09-11"
DEVELOPMENT_SEASONS = tuple(range(2016, 2024))
FIT_TARGET_SEASONS = tuple(range(2017, 2024))
VALIDATION_SEASON = 2024
HOLDOUT_SEASON = 2025
RIDGE_GRID = (0.03, 0.1, 0.3, 1.0, 3.0)
SHRINKAGE_ALPHA_GRID = (25.0, 50.0, 100.0, 200.0, 400.0)
SNAP_WINDOW = 4
RATE_WINDOW = 8
TEAM_WINDOW = 8
STANDARD_PLAY_FAMILIES = frozenset({"RUSH", "COMPLETE_PASS", "OTHER_PASS", "SACK", "SCRAMBLE"})

TEAM_FEATURE_NAMES = (
    "off_def_snaps_mean8",
    "def_def_snaps_mean8",
    "off_opportunity_plays_mean8",
    "def_opportunity_plays_mean8",
    "off_opportunity_rate8",
    "def_opportunity_rate8",
    "off_credits_per_opportunity8",
    "def_credits_per_opportunity8",
    "off_rush_share8",
    "off_complete_pass_share8",
    "off_scramble_share8",
    "off_sack_share8",
    "off_games_available8",
    "def_games_available8",
)


def num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def as_int(v: Any) -> int:
    x = num(v)
    return 0 if x is None else int(round(x))


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


def mean_or(values: Sequence[float], fallback: float = 0.0) -> float:
    return fmean(values) if values else float(fallback)


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    if not actual or len(actual) != len(predicted):
        raise ValueError("non-empty equal-length vectors required")
    return sqrt(fmean((a - p) ** 2 for a, p in zip(actual, predicted)))


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    if not actual or len(actual) != len(predicted):
        raise ValueError("non-empty equal-length vectors required")
    return fmean(abs(a - p) for a, p in zip(actual, predicted))


def bias(actual: Sequence[float], predicted: Sequence[float]) -> float:
    if not actual or len(actual) != len(predicted):
        raise ValueError("non-empty equal-length vectors required")
    return fmean(p - a for a, p in zip(actual, predicted))


def count_metrics(rows: Sequence[dict[str, Any]], *, actual_key: str, pred_key: str) -> dict[str, float | int]:
    ys = [float(r[actual_key]) for r in rows]
    ps = [max(0.0, float(r[pred_key])) for r in rows]
    return {
        "n": len(rows),
        "actualMean": fmean(ys) if ys else 0.0,
        "predictedMean": fmean(ps) if ps else 0.0,
        "mae": mae(ys, ps) if ys else 0.0,
        "rmse": rmse(ys, ps) if ys else 0.0,
        "bias": bias(ys, ps) if ys else 0.0,
    }


@dataclass
class RidgeModel:
    feature_names: tuple[str, ...]
    means: list[float]
    scales: list[float]
    intercept: float
    coefficients: list[float]
    l2: float
    target_name: str

    def predict(self, values: Sequence[float]) -> float:
        if len(values) != len(self.feature_names):
            raise ValueError("feature vector length mismatch")
        z = self.intercept
        for i, v in enumerate(values):
            z += self.coefficients[i] * ((float(v) - self.means[i]) / self.scales[i])
        return max(0.0, z)

    def to_dict(self) -> dict[str, Any]:
        return {
            "modelClass": "STANDARDIZED_L2_RIDGE",
            "version": VERSION,
            "lineage": LINEAGE,
            "targetName": self.target_name,
            "featureNames": list(self.feature_names),
            "means": self.means,
            "scales": self.scales,
            "intercept": self.intercept,
            "coefficients": self.coefficients,
            "l2": self.l2,
        }


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve Ax=b with deterministic partial-pivot Gauss-Jordan elimination."""
    n = len(b)
    if len(a) != n or any(len(row) != n for row in a):
        raise ValueError("square system required")
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
            factor = aug[r][col]
            if abs(factor) < 1e-18:
                continue
            aug[r] = [x - factor * y for x, y in zip(aug[r], aug[col])]
    return [aug[i][-1] for i in range(n)]


def fit_ridge(rows: Sequence[dict[str, Any]], *, target_key: str, l2: float) -> RidgeModel:
    if not rows:
        raise ValueError("cannot fit empty ridge dataset")
    p = len(TEAM_FEATURE_NAMES)
    xs = [[float(r[n]) for n in TEAM_FEATURE_NAMES] for r in rows]
    ys = [float(r[target_key]) for r in rows]
    means = [fmean(row[j] for row in xs) for j in range(p)]
    scales: list[float] = []
    for j in range(p):
        var = fmean((row[j] - means[j]) ** 2 for row in xs)
        scales.append(sqrt(var) if var > 1e-12 else 1.0)
    zx = [[(row[j] - means[j]) / scales[j] for j in range(p)] for row in xs]
    ybar = fmean(ys)
    yc = [y - ybar for y in ys]
    xtx = [[0.0 for _ in range(p)] for _ in range(p)]
    xty = [0.0 for _ in range(p)]
    n = float(len(rows))
    for x, y in zip(zx, yc):
        for j in range(p):
            xty[j] += x[j] * y / n
            for k in range(p):
                xtx[j][k] += x[j] * x[k] / n
    for j in range(p):
        xtx[j][j] += float(l2)
    coefs = _solve_linear(xtx, xty)
    return RidgeModel(
        feature_names=TEAM_FEATURE_NAMES,
        means=means,
        scales=scales,
        intercept=ybar,
        coefficients=coefs,
        l2=float(l2),
        target_name=target_key,
    )


def ridge_predict_rows(model: RidgeModel, rows: Sequence[dict[str, Any]], out_key: str) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        z = dict(r)
        z[out_key] = model.predict([float(r[n]) for n in TEAM_FEATURE_NAMES])
        out.append(z)
    return out


def estimate_team_defensive_snaps(exposure_rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], float]:
    """Recover team defensive-snap totals from player snap rows.

    nflverse provides player defense_snaps and defense_pct.  Median(snaps/pct) is a
    robust team-snap estimate; max player snaps is the fallback and lower bound.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in exposure_rows:
        if not truthy(r.get("eligible_standard_rate_fit")):
            continue
        game = str(r.get("game_id") or "")
        team = str(r.get("team") or "")
        if game and team:
            groups[(game, team)].append(r)
    out: dict[tuple[str, str], float] = {}
    for key, rows in groups.items():
        ratios: list[float] = []
        max_snaps = 0.0
        for r in rows:
            snaps = num(r.get("defense_snaps")) or 0.0
            max_snaps = max(max_snaps, snaps)
            pct = normalize_pct(r.get("defense_pct"))
            if snaps > 0 and pct is not None and pct >= 0.10:
                est = snaps / pct
                if est >= snaps and est <= 150:
                    ratios.append(est)
        val = median(ratios) if ratios else max_snaps
        out[key] = max(max_snaps, float(val))
    return out


def aggregate_team_game_outcomes(
    play_rows: Iterable[dict[str, Any]],
    exposure_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    snap_totals = estimate_team_defensive_snaps(exposure_rows)
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in play_rows:
        if truthy(r.get("is_nullified_or_deleted")):
            continue
        family = str(r.get("play_family") or "")
        if family not in STANDARD_PLAY_FAMILIES:
            continue
        game = str(r.get("game_id") or "")
        off = str(r.get("posteam") or "")
        deff = str(r.get("defteam") or "")
        if not game or not off or not deff:
            continue
        key = (game, off, deff)
        g = groups.setdefault(key, {
            "game_id": game,
            "season": as_int(r.get("season")),
            "week": as_int(r.get("week")),
            "offense_team": off,
            "defense_team": deff,
            "standard_plays": 0,
            "opportunity_plays": 0,
            "credit_units": 0,
            "solo_units": 0,
            "primary_with_assist_units": 0,
            "assist_units": 0,
            "rush_plays": 0,
            "complete_pass_plays": 0,
            "other_pass_plays": 0,
            "sack_plays": 0,
            "scramble_plays": 0,
        })
        g["standard_plays"] += 1
        credits = as_int(r.get("original_defense_credit_units"))
        if credits > 0:
            g["opportunity_plays"] += 1
        g["credit_units"] += credits
        g["solo_units"] += as_int(r.get("original_defense_solo"))
        g["primary_with_assist_units"] += as_int(r.get("original_defense_primary_with_assist"))
        g["assist_units"] += as_int(r.get("original_defense_assists"))
        if family == "RUSH": g["rush_plays"] += 1
        elif family == "COMPLETE_PASS": g["complete_pass_plays"] += 1
        elif family == "OTHER_PASS": g["other_pass_plays"] += 1
        elif family == "SACK": g["sack_plays"] += 1
        elif family == "SCRAMBLE": g["scramble_plays"] += 1
    out = []
    for (_, _, deff), g in groups.items():
        snaps = snap_totals.get((g["game_id"], deff))
        if snaps is None or snaps <= 0:
            continue
        g["defensive_snaps"] = float(snaps)
        out.append(g)
    out.sort(key=lambda r: (r["season"], r["week"], r["game_id"], r["defense_team"]))
    return out


def _summary(history: Sequence[dict[str, Any]]) -> dict[str, float]:
    h = list(history[-TEAM_WINDOW:])
    if not h:
        return {}
    std = sum(float(r["standard_plays"]) for r in h)
    opp = sum(float(r["opportunity_plays"]) for r in h)
    credits = sum(float(r["credit_units"]) for r in h)
    return {
        "def_snaps": fmean(float(r["defensive_snaps"]) for r in h),
        "opportunity_plays": fmean(float(r["opportunity_plays"]) for r in h),
        "opportunity_rate": opp / std if std > 0 else 0.0,
        "credits_per_opportunity": credits / opp if opp > 0 else 1.0,
        "rush_share": sum(float(r["rush_plays"]) for r in h) / std if std else 0.0,
        "complete_pass_share": sum(float(r["complete_pass_plays"]) for r in h) / std if std else 0.0,
        "scramble_share": sum(float(r["scramble_plays"]) for r in h) / std if std else 0.0,
        "sack_share": sum(float(r["sack_plays"]) for r in h) / std if std else 0.0,
        "games": float(len(h)),
    }


def build_team_pregame_rows(outcomes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build strictly lagged team matchup feature rows.

    Features for every game in a week are emitted before that week's results update
    histories, preventing same-week contamination.
    """
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in outcomes:
        if int(r["season"]) == HOLDOUT_SEASON:
            raise ValueError("2025 holdout row entered 0.2 outcomes")
        by_week[(int(r["season"]), int(r["week"]))].append(r)
    off_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    def_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    for season, week in sorted(by_week):
        games = by_week[(season, week)]
        if season >= 2017:
            for g in games:
                oh = _summary(off_hist[g["offense_team"]])
                dh = _summary(def_hist[g["defense_team"]])
                if not oh or not dh:
                    continue
                row = {
                    "game_id": g["game_id"],
                    "season": season,
                    "week": week,
                    "offense_team": g["offense_team"],
                    "defense_team": g["defense_team"],
                    "actual_defensive_snaps": float(g["defensive_snaps"]),
                    "actual_opportunity_plays": float(g["opportunity_plays"]),
                    "actual_credit_units": float(g["credit_units"]),
                    "off_def_snaps_mean8": oh["def_snaps"],
                    "def_def_snaps_mean8": dh["def_snaps"],
                    "off_opportunity_plays_mean8": oh["opportunity_plays"],
                    "def_opportunity_plays_mean8": dh["opportunity_plays"],
                    "off_opportunity_rate8": oh["opportunity_rate"],
                    "def_opportunity_rate8": dh["opportunity_rate"],
                    "off_credits_per_opportunity8": oh["credits_per_opportunity"],
                    "def_credits_per_opportunity8": dh["credits_per_opportunity"],
                    "off_rush_share8": oh["rush_share"],
                    "off_complete_pass_share8": oh["complete_pass_share"],
                    "off_scramble_share8": oh["scramble_share"],
                    "off_sack_share8": oh["sack_share"],
                    "off_games_available8": oh["games"] / TEAM_WINDOW,
                    "def_games_available8": dh["games"] / TEAM_WINDOW,
                    "benchmark_defensive_snaps": 0.5 * (oh["def_snaps"] + dh["def_snaps"]),
                    "benchmark_opportunity_plays": 0.5 * (oh["opportunity_plays"] + dh["opportunity_plays"]),
                }
                rows.append(row)
        # Update only after all target features for this week have been emitted.
        for g in games:
            off_hist[g["offense_team"]].append(g)
            def_hist[g["defense_team"]].append(g)
    return rows


def choose_ridge_lambda(rows: Sequence[dict[str, Any]], *, target_key: str, pred_key: str, folds: Sequence[int] = (2021, 2022, 2023)) -> tuple[float, list[dict[str, Any]]]:
    results = []
    for lam in RIDGE_GRID:
        fold_mae = []
        fold_rmse = []
        for year in folds:
            train = [r for r in rows if 2017 <= int(r["season"]) < year]
            val = [r for r in rows if int(r["season"]) == year]
            if not train or not val:
                continue
            m = fit_ridge(train, target_key=target_key, l2=lam)
            ys = [float(r[target_key]) for r in val]
            ps = [m.predict([float(r[n]) for n in TEAM_FEATURE_NAMES]) for r in val]
            fold_mae.append(mae(ys, ps))
            fold_rmse.append(rmse(ys, ps))
        if not fold_mae:
            continue
        results.append({"l2": lam, "folds": len(fold_mae), "meanMAE": fmean(fold_mae), "meanRMSE": fmean(fold_rmse)})
    if not results:
        raise ValueError("no chronological ridge folds available")
    results.sort(key=lambda x: (x["meanMAE"], x["meanRMSE"], x["l2"]))
    return float(results[0]["l2"]), results


def canonical_position_group(r: dict[str, Any]) -> str:
    pg = str(r.get("position_group") or "").strip().upper()
    if pg:
        if pg in {"DB", "CB", "S", "SAFETY"}: return "DB"
        if pg in {"LB", "ILB", "OLB"}: return "LB"
        if pg in {"DL", "DE", "DT", "NT", "EDGE"}: return "DL"
        return pg
    pos = str(r.get("position") or "").strip().upper()
    if pos in {"CB", "S", "FS", "SS", "DB"}: return "DB"
    if pos in {"LB", "ILB", "OLB", "MLB"}: return "LB"
    if pos in {"DE", "DT", "NT", "DL", "EDGE"}: return "DL"
    return pos or "UNK"


def build_player_pregame_rows(exposure_rows: Sequence[dict[str, Any]], team_feature_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    team_key = {(r["game_id"], r["defense_team"]): r for r in team_feature_rows}
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in exposure_rows:
        if not truthy(r.get("eligible_standard_rate_fit")):
            continue
        season = as_int(r.get("season")); week = as_int(r.get("week"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 holdout row entered player baseline")
        if season < 2016 or season > VALIDATION_SEASON:
            continue
        by_week[(season, week)].append(r)

    player_hist: dict[str, list[dict[str, float]]] = defaultdict(list)
    pos_credits: dict[str, float] = defaultdict(float)
    pos_snaps: dict[str, float] = defaultdict(float)
    pos_pct_sum: dict[str, float] = defaultdict(float)
    pos_pct_n: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []

    for season, week in sorted(by_week):
        batch = by_week[(season, week)]
        if season >= 2017:
            for r in batch:
                game = str(r.get("game_id") or "")
                team = str(r.get("team") or "")
                tf = team_key.get((game, team))
                if tf is None:
                    continue
                pid = str(r.get("player_id") or "")
                pg = canonical_position_group(r)
                hist = player_hist[pid]
                last4 = hist[-SNAP_WINDOW:]
                last8 = hist[-RATE_WINDOW:]
                pos_rate = pos_credits[pg] / pos_snaps[pg] if pos_snaps[pg] > 0 else 0.08
                pos_snap = pos_pct_sum[pg] / pos_pct_n[pg] if pos_pct_n[pg] > 0 else 0.35
                snap_share = mean_or([x["snap_pct"] for x in last4 if x["snap_pct"] >= 0], pos_snap)
                last8_credits = sum(x["credits"] for x in last8)
                last8_snaps = sum(x["snaps"] for x in last8)
                team_snap_fallback = float(tf.get("benchmark_defensive_snaps", tf.get("actual_defensive_snaps", 60.0)))
                last4_pg = mean_or([x["credits"] for x in last4], pos_rate * team_snap_fallback * pos_snap)
                rows.append({
                    "game_id": game,
                    "season": season,
                    "week": week,
                    "team": team,
                    "opponent": str(r.get("opponent") or tf.get("offense_team") or ""),
                    "player_id": pid,
                    "display_name": str(r.get("display_name") or ""),
                    "position": str(r.get("position") or ""),
                    "position_group": pg,
                    "actual_defensive_snaps": float(num(r.get("defense_snaps")) or 0.0),
                    "actual_snap_share": float(normalize_pct(r.get("defense_pct")) or 0.0),
                    "actual_xtc": float(as_int(r.get("combined_standard_def_scrimmage"))),
                    "prior_games": len(hist),
                    "prior_last4_snap_share": snap_share,
                    "prior_last8_credits": last8_credits,
                    "prior_last8_snaps": last8_snaps,
                    "position_prior_credit_rate": pos_rate,
                    "position_prior_snap_share": pos_snap,
                    "benchmark_last4_xtc": last4_pg,
                })
        # Update priors after the entire week is emitted.
        for r in batch:
            pid = str(r.get("player_id") or "")
            if not pid:
                continue
            pg = canonical_position_group(r)
            snaps = float(num(r.get("defense_snaps")) or 0.0)
            pct = normalize_pct(r.get("defense_pct"))
            credits = float(as_int(r.get("combined_standard_def_scrimmage")))
            if snaps <= 0:
                continue
            player_hist[pid].append({"snaps": snaps, "snap_pct": float(pct if pct is not None else -1.0), "credits": credits})
            pos_credits[pg] += credits
            pos_snaps[pg] += snaps
            if pct is not None:
                pos_pct_sum[pg] += pct
                pos_pct_n[pg] += 1
    return rows


def score_player_rows(
    rows: Sequence[dict[str, Any]],
    *,
    alpha: float,
    snap_predictions: dict[tuple[str, str], float],
    out_key: str = "predicted_xtc",
) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        team_snaps = snap_predictions.get((r["game_id"], r["team"]))
        if team_snaps is None:
            continue
        den = float(r["prior_last8_snaps"]) + float(alpha)
        rate = (
            float(r["prior_last8_credits"])
            + float(alpha) * float(r["position_prior_credit_rate"])
        ) / den if den > 0 else float(r["position_prior_credit_rate"])
        xplayer_snaps = max(0.0, float(team_snaps) * float(r["prior_last4_snap_share"]))
        pred = max(0.0, xplayer_snaps * rate)
        z = dict(r)
        z["predicted_team_defensive_snaps"] = float(team_snaps)
        z["predicted_player_defensive_snaps"] = xplayer_snaps
        z["shrunk_credit_rate_per_snap"] = rate
        z["shrinkage_alpha"] = float(alpha)
        z[out_key] = pred
        z["cold_start"] = 1 if int(r["prior_games"]) == 0 else 0
        out.append(z)
    return out


def choose_player_alpha(
    player_rows: Sequence[dict[str, Any]],
    team_rows: Sequence[dict[str, Any]],
    *,
    snap_l2: float,
    folds: Sequence[int] = (2021, 2022, 2023),
) -> tuple[float, list[dict[str, Any]]]:
    results = []
    for alpha in SHRINKAGE_ALPHA_GRID:
        fold_mae = []
        fold_rmse = []
        for year in folds:
            ttrain = [r for r in team_rows if 2017 <= int(r["season"]) < year]
            tval = [r for r in team_rows if int(r["season"]) == year]
            pval = [r for r in player_rows if int(r["season"]) == year]
            if not ttrain or not tval or not pval:
                continue
            sm = fit_ridge(ttrain, target_key="actual_defensive_snaps", l2=snap_l2)
            sp = {(r["game_id"], r["defense_team"]): sm.predict([float(r[n]) for n in TEAM_FEATURE_NAMES]) for r in tval}
            scored = score_player_rows(pval, alpha=alpha, snap_predictions=sp)
            ys = [float(r["actual_xtc"]) for r in scored]
            ps = [float(r["predicted_xtc"]) for r in scored]
            if ys:
                fold_mae.append(mae(ys, ps)); fold_rmse.append(rmse(ys, ps))
        if fold_mae:
            results.append({"alphaPseudoSnaps": alpha, "folds": len(fold_mae), "meanMAE": fmean(fold_mae), "meanRMSE": fmean(fold_rmse)})
    if not results:
        raise ValueError("no chronological player shrinkage folds available")
    results.sort(key=lambda x: (x["meanMAE"], x["meanRMSE"], x["alphaPseudoSnaps"]))
    return float(results[0]["alphaPseudoSnaps"]), results

"""NFL QB Model 0.2.0 — development-only passing-yards challenger helpers.

This layer is conditional on a known target QB identity. Historical observed-start
GSIS identity is used only to retrieve that player's strictly prior history and to
attach the official target. It is not a current-game predictive outcome. A future
caller must supply a verified/market-listed QB identity; starter resolution remains
an independent operational problem.

All feature histories are frozen before the target week is admitted. Same-week
results never enter another row's features. The sealed 2025 holdout is forbidden.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import isnan, sqrt
from statistics import fmean
from typing import Any, Iterable, Sequence

try:
    import numpy as np
except Exception as exc:  # pragma: no cover
    np = None
    _NUMPY_IMPORT_ERROR = exc
else:
    _NUMPY_IMPORT_ERROR = None

VERSION = "0.2.0"
LINEAGE = "nfl-qb-passing-yards-bakeoff-v0.2.0-m31-m36-m39-m41-m48-m50-m87-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
DEVELOPMENT_SEASONS = tuple(range(2016, 2025))
VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
FIXED_L2 = 0.10
BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = 20260916
CANDIDATES = ("MODEL_A_DIRECT", "MODEL_B_VOLUME_X_YPA", "MODEL_C_VOLUME_X_CR_X_YPC")

QB_METRICS = (
    "attempts", "passing_yards", "completion_rate", "ypa",
    "sack_rate", "scramble_rate", "mean_qb_epa", "mean_cpoe",
)
TEAM_METRICS = ("plays", "dropback_rate", "designed_run_rate")
DEF_METRICS = (
    "attempts_allowed", "yards_allowed", "completion_rate_allowed",
    "ypa_allowed", "sack_rate_generated",
)


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if isnan(x) else x


def ratio(a: Any, b: Any) -> float | None:
    x = num(a); y = num(b)
    if x is None or y is None or abs(y) < 1e-12:
        return None
    return x / y


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    vals = tuple(sorted({int(s) for s in seasons}))
    if not vals:
        raise ValueError("at least one development season is required")
    bad = [s for s in vals if s >= SEALED_HOLDOUT_SEASON]
    if bad:
        raise ValueError("QB Model 0.2.0 forbids sealed 2025 / prospective 2026+: " + ",".join(map(str, bad)))
    return vals


def assert_exact_development_window(seasons: Iterable[int]) -> tuple[int, ...]:
    vals = assert_development_only(seasons)
    if vals != DEVELOPMENT_SEASONS:
        raise ValueError(f"QB Model 0.2.0 bakeoff is frozen to {DEVELOPMENT_SEASONS[0]}-{DEVELOPMENT_SEASONS[-1]}")
    return vals


def _sum(rows: Sequence[dict[str, Any]], field: str) -> float:
    return sum(float(v) for r in rows if (v := num(r.get(field))) is not None)


def _mean(rows: Sequence[dict[str, Any]], field: str) -> float | None:
    vals = [float(v) for r in rows if (v := num(r.get(field))) is not None]
    return None if not vals else fmean(vals)


def _window(rows: Sequence[dict[str, Any]], n: int | None = None, season: int | None = None) -> list[dict[str, Any]]:
    vals = list(rows)
    if season is not None:
        vals = [r for r in vals if int(r.get("season") or 0) == int(season)]
    if n is not None:
        vals = vals[-int(n):]
    return vals


def qb_summary(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {k: None for k in QB_METRICS}
    att = _sum(rows, "official_attempts")
    comp = _sum(rows, "official_completions")
    yards = _sum(rows, "official_passing_yards")
    sacks = _sum(rows, "official_sacks_suffered")
    scrambles = _sum(rows, "structural_scrambles")
    db = _sum(rows, "starter_structural_dropbacks")
    return {
        "attempts": _mean(rows, "official_attempts"),
        "passing_yards": _mean(rows, "official_passing_yards"),
        "completion_rate": None if att <= 0 else comp / att,
        "ypa": None if att <= 0 else yards / att,
        "sack_rate": None if db <= 0 else sacks / db,
        "scramble_rate": None if db <= 0 else scrambles / db,
        "mean_qb_epa": _mean(rows, "mean_qb_epa"),
        "mean_cpoe": _mean(rows, "mean_cpoe"),
    }


def team_summary(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {k: None for k in TEAM_METRICS}
    plays = _sum(rows, "team_structural_plays")
    db = _sum(rows, "team_structural_dropbacks")
    runs = _sum(rows, "team_designed_runs")
    return {
        "plays": _mean(rows, "team_structural_plays"),
        "dropback_rate": None if plays <= 0 else db / plays,
        "designed_run_rate": None if plays <= 0 else runs / plays,
    }


def defense_summary(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {k: None for k in DEF_METRICS}
    att = _sum(rows, "official_attempts")
    comp = _sum(rows, "official_completions")
    yards = _sum(rows, "official_passing_yards")
    sacks = _sum(rows, "official_sacks_suffered")
    db = _sum(rows, "starter_structural_dropbacks")
    return {
        "attempts_allowed": _mean(rows, "official_attempts"),
        "yards_allowed": _mean(rows, "official_passing_yards"),
        "completion_rate_allowed": None if att <= 0 else comp / att,
        "ypa_allowed": None if att <= 0 else yards / att,
        "sack_rate_generated": None if db <= 0 else sacks / db,
    }


def feature_names() -> tuple[str, ...]:
    names: list[str] = [
        "home", "week", "qb_prior_games", "qb_same_team_last_game",
        "team_prior_games", "def_prior_games", "league_prior_mean_passing_yards",
        "missing__league_prior_mean_passing_yards",
    ]
    for horizon in ("last4", "last8", "prior_season"):
        for metric in QB_METRICS:
            base = f"qb_{horizon}_{metric}"
            names.extend((base, f"missing__{base}"))
    for horizon in ("last4", "last8"):
        for metric in TEAM_METRICS:
            base = f"team_{horizon}_{metric}"
            names.extend((base, f"missing__{base}"))
    for horizon in ("last4", "last8"):
        for metric in DEF_METRICS:
            base = f"def_{horizon}_{metric}"
            names.extend((base, f"missing__{base}"))
    return tuple(names)

FEATURE_NAMES = feature_names()


def _put_with_missing(out: dict[str, float | None], name: str, value: float | None) -> None:
    out[name] = value
    out[f"missing__{name}"] = 1.0 if value is None else 0.0


@dataclass(frozen=True)
class Example:
    season: int
    week: int
    game_id: str
    team: str
    opponent: str
    qb_gsis_id: str
    home: int
    x: tuple[float | None, ...]
    y_passing_yards: float
    y_attempts: float
    y_completions: float
    baseline_last4_yards: float | None
    league_prior_mean_yards: float | None


def _required_target(row: dict[str, Any], field: str) -> float:
    v = num(row.get(field))
    if v is None:
        raise ValueError(f"target row missing required {field}: {row.get('game_id')} {row.get('team')}")
    return float(v)


def build_examples(rows: Iterable[dict[str, Any]]) -> list[Example]:
    """Build strictly prior-week feature rows from canonical 0.1.9 targets.

    Input rows must already include `_opponent` and `_home`, derived only from game
    identity. Current-week rows are all featurized before any member of that week is
    admitted into histories, preventing same-week leakage.
    """
    data = [dict(r) for r in rows]
    if not data:
        raise ValueError("no QB target rows")
    assert_development_only(int(r.get("season") or 0) for r in data)
    data.sort(key=lambda r: (int(r.get("season") or 0), int(r.get("week") or 0), clean(r.get("game_id")), clean(r.get("team"))))

    qb_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    team_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    def_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    league_hist: list[dict[str, Any]] = []
    examples: list[Example] = []

    batches: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in data:
        batches[(int(row.get("season") or 0), int(row.get("week") or 0))].append(row)

    for season, week in sorted(batches):
        batch = sorted(batches[(season, week)], key=lambda r: (clean(r.get("game_id")), clean(r.get("team"))))
        for row in batch:
            gid = clean(row.get("game_id")); team = clean(row.get("team")).upper()
            opp = clean(row.get("_opponent")).upper(); qid = clean(row.get("observed_start_qb_gsis_id"))
            if not gid or not team or not opp or not qid:
                raise ValueError(f"QB 0.2.0 row missing identity: {gid} {team} {qid}")
            home = int(row.get("_home") or 0)
            qh = qb_hist[qid]; th = team_hist[team]; dh = def_hist[opp]
            fmap: dict[str, float | None] = {
                "home": float(home), "week": float(week),
                "qb_prior_games": float(len(qh)),
                "qb_same_team_last_game": 1.0 if qh and clean(qh[-1].get("team")).upper() == team else 0.0,
                "team_prior_games": float(len(th)), "def_prior_games": float(len(dh)),
            }
            league_prior = _mean(league_hist, "official_passing_yards")
            _put_with_missing(fmap, "league_prior_mean_passing_yards", league_prior)

            qb_windows = {
                "last4": _window(qh, n=4),
                "last8": _window(qh, n=8),
                "prior_season": _window(qh, season=season - 1),
            }
            for horizon, hrows in qb_windows.items():
                sm = qb_summary(hrows)
                for metric in QB_METRICS:
                    _put_with_missing(fmap, f"qb_{horizon}_{metric}", sm[metric])
            for horizon, n in (("last4", 4), ("last8", 8)):
                sm = team_summary(_window(th, n=n))
                for metric in TEAM_METRICS:
                    _put_with_missing(fmap, f"team_{horizon}_{metric}", sm[metric])
                ds = defense_summary(_window(dh, n=n))
                for metric in DEF_METRICS:
                    _put_with_missing(fmap, f"def_{horizon}_{metric}", ds[metric])

            if set(fmap) != set(FEATURE_NAMES):
                missing = sorted(set(FEATURE_NAMES) - set(fmap)); extra = sorted(set(fmap) - set(FEATURE_NAMES))
                raise ValueError(f"feature contract drift missing={missing} extra={extra}")
            last4_yards = qb_summary(_window(qh, n=4))["passing_yards"]
            examples.append(Example(
                season=season, week=week, game_id=gid, team=team, opponent=opp,
                qb_gsis_id=qid, home=home,
                x=tuple(fmap[n] for n in FEATURE_NAMES),
                y_passing_yards=_required_target(row, "official_passing_yards"),
                y_attempts=_required_target(row, "official_attempts"),
                y_completions=_required_target(row, "official_completions"),
                baseline_last4_yards=last4_yards,
                league_prior_mean_yards=league_prior,
            ))

        # Admit the completed target week only after every row in that week was built.
        for row in batch:
            team = clean(row.get("team")).upper(); opp = clean(row.get("_opponent")).upper()
            qid = clean(row.get("observed_start_qb_gsis_id"))
            record = dict(row)
            qb_hist[qid].append(record)
            team_hist[team].append(record)
            def_hist[opp].append(record)
            league_hist.append(record)
    return examples


@dataclass
class RidgeRegressor:
    names: tuple[str, ...]
    means: list[float]
    scales: list[float]
    intercept: float
    coefficients: list[float]
    l2: float

    def predict(self, x: Sequence[float | None]) -> float:
        if len(x) != len(self.names):
            raise ValueError("ridge feature dimension mismatch")
        z = [((self.means[i] if v is None else float(v)) - self.means[i]) / self.scales[i] for i, v in enumerate(x)]
        return float(self.intercept + sum(a * b for a, b in zip(self.coefficients, z)))


def fit_ridge(xs: Sequence[Sequence[float | None]], ys: Sequence[float], names: Sequence[str] = FEATURE_NAMES, *, l2: float = FIXED_L2) -> RidgeRegressor:
    if np is None:
        raise RuntimeError(f"numpy required for QB Model 0.2.0: {_NUMPY_IMPORT_ERROR}")
    if not xs or len(xs) != len(ys):
        raise ValueError("bad ridge design")
    p = len(names)
    if any(len(x) != p for x in xs):
        raise ValueError("inconsistent ridge feature width")
    means: list[float] = []; scales: list[float] = []
    for j in range(p):
        vals = [float(r[j]) for r in xs if r[j] is not None]
        m = fmean(vals) if vals else 0.0
        var = fmean((v - m) ** 2 for v in vals) if len(vals) > 1 else 0.0
        means.append(m); scales.append(sqrt(var) if var > 1e-12 else 1.0)
    Z = np.asarray([
        [((means[j] if v is None else float(v)) - means[j]) / scales[j] for j, v in enumerate(row)]
        for row in xs
    ], dtype=float)
    y = np.asarray([float(v) for v in ys], dtype=float)
    n = float(len(y))
    X = np.column_stack([np.ones(len(Z)), Z])
    penalty = np.eye(p + 1, dtype=float) * (float(l2) * n)
    penalty[0, 0] = 0.0
    lhs = X.T @ X + penalty
    rhs = X.T @ y
    try:
        beta = np.linalg.solve(lhs, rhs)
    except np.linalg.LinAlgError:
        beta = np.linalg.pinv(lhs) @ rhs
    return RidgeRegressor(tuple(names), means, scales, float(beta[0]), [float(v) for v in beta[1:]], float(l2))


def metric_summary(ys: Sequence[float], ps: Sequence[float]) -> dict[str, float | int | None]:
    if not ys or len(ys) != len(ps):
        raise ValueError("bad metric vectors")
    err = [float(p) - float(y) for y, p in zip(ys, ps)]
    abs_err = [abs(e) for e in err]
    sq = [e * e for e in err]
    ordered = sorted(abs_err)
    mid = len(ordered) // 2
    med = ordered[mid] if len(ordered) % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])
    return {
        "n": len(ys),
        "mae": fmean(abs_err),
        "rmse": sqrt(fmean(sq)),
        "bias": fmean(err),
        "medianAbsoluteError": med,
    }


def fit_predict_candidates(train: Sequence[Example], test: Sequence[Example], *, l2: float = FIXED_L2) -> list[dict[str, Any]]:
    if not train or not test:
        raise ValueError("empty train/test fold")
    X = [e.x for e in train]
    direct = fit_ridge(X, [e.y_passing_yards for e in train], l2=l2)
    attempts_b = fit_ridge(X, [e.y_attempts for e in train], l2=l2)
    ypa_train = [e for e in train if e.y_attempts > 0]
    ypa = fit_ridge([e.x for e in ypa_train], [e.y_passing_yards / e.y_attempts for e in ypa_train], l2=l2)
    attempts_c = fit_ridge(X, [e.y_attempts for e in train], l2=l2)
    cr_train = [e for e in train if e.y_attempts > 0]
    cr = fit_ridge([e.x for e in cr_train], [e.y_completions / e.y_attempts for e in cr_train], l2=l2)
    ypc_train = [e for e in train if e.y_completions > 0]
    ypc = fit_ridge([e.x for e in ypc_train], [e.y_passing_yards / e.y_completions for e in ypc_train], l2=l2)
    train_mean_yards = fmean(e.y_passing_yards for e in train)

    out: list[dict[str, Any]] = []
    for e in test:
        pred_a = direct.predict(e.x)
        att_b = max(0.0, attempts_b.predict(e.x)); ypa_p = ypa.predict(e.x); pred_b = att_b * ypa_p
        att_c = max(0.0, attempts_c.predict(e.x)); cr_p = min(1.0, max(0.0, cr.predict(e.x))); ypc_p = ypc.predict(e.x); pred_c = att_c * cr_p * ypc_p
        baseline = e.baseline_last4_yards
        if baseline is None:
            baseline = e.league_prior_mean_yards
        if baseline is None:
            baseline = train_mean_yards
        out.append({
            "season": e.season, "week": e.week, "game_id": e.game_id,
            "team": e.team, "opponent": e.opponent, "qb_gsis_id": e.qb_gsis_id,
            "actual_passing_yards": e.y_passing_yards,
            "baseline_last4": float(baseline),
            "MODEL_A_DIRECT": float(pred_a),
            "MODEL_B_VOLUME_X_YPA": float(pred_b),
            "MODEL_C_VOLUME_X_CR_X_YPC": float(pred_c),
            "model_b_attempts": float(att_b), "model_b_ypa": float(ypa_p),
            "model_c_attempts": float(att_c), "model_c_completion_rate": float(cr_p), "model_c_ypc": float(ypc_p),
        })
    return out


def cluster_bootstrap_mae_delta(rows: Sequence[dict[str, Any]], model_a: str, model_b: str, *, reps: int = BOOTSTRAP_REPS, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Return MAE(model_a)-MAE(model_b), clustering the resample by game_id."""
    if np is None:
        raise RuntimeError(f"numpy required: {_NUMPY_IMPORT_ERROR}")
    if not rows:
        raise ValueError("no rows for bootstrap")
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_game[clean(r.get("game_id"))].append(dict(r))
    gids = sorted(by_game)
    if not gids:
        raise ValueError("no game clusters")

    def delta(sample: Sequence[dict[str, Any]]) -> float:
        da = [abs(float(r[model_a]) - float(r["actual_passing_yards"])) for r in sample]
        db = [abs(float(r[model_b]) - float(r["actual_passing_yards"])) for r in sample]
        return fmean(da) - fmean(db)

    point = delta(rows)
    rng = np.random.default_rng(int(seed))
    sims: list[float] = []
    n = len(gids)
    for _ in range(int(reps)):
        chosen = rng.integers(0, n, size=n)
        sample: list[dict[str, Any]] = []
        for idx in chosen:
            sample.extend(by_game[gids[int(idx)]])
        sims.append(delta(sample))
    sims.sort()
    lo = sims[max(0, int(0.025 * len(sims)))]
    hi = sims[min(len(sims) - 1, int(0.975 * len(sims)))]
    return {"modelA": model_a, "modelB": model_b, "deltaMae": point, "ci95": [lo, hi], "reps": int(reps), "cluster": "game_id"}


def development_selection(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        name: metric_summary([float(r["actual_passing_yards"]) for r in rows], [float(r[name]) for r in rows])
        for name in CANDIDATES
    }
    ordered = sorted(CANDIDATES, key=lambda n: (float(metrics[n]["mae"]), float(metrics[n]["rmse"]), n))
    leader = ordered[0]
    fold_wins = {name: 0 for name in CANDIDATES}
    for season in VALIDATION_SEASONS:
        sr = [r for r in rows if int(r["season"]) == season]
        if not sr:
            continue
        season_metrics = {
            name: metric_summary([float(r["actual_passing_yards"]) for r in sr], [float(r[name]) for r in sr])
            for name in CANDIDATES
        }
        best = min(CANDIDATES, key=lambda n: (float(season_metrics[n]["mae"]), float(season_metrics[n]["rmse"]), n))
        fold_wins[best] += 1
    leader_vs_baseline = cluster_bootstrap_mae_delta(rows, leader, "baseline_last4")
    supported = leader_vs_baseline["ci95"][1] < 0.0 and fold_wins[leader] >= 3
    return {
        "developmentLeader": leader,
        "candidateOrderByMae": ordered,
        "candidateMetrics": metrics,
        "foldWinsByMae": fold_wins,
        "leaderVsLast4Baseline": leader_vs_baseline,
        "selectionStatus": "DEVELOPMENT_LEADER_SUPPORTED" if supported else "DEVELOPMENT_LEADER_INCONCLUSIVE",
        "selectionRule": "lowest pooled 2020-2024 OOF MAE; RMSE/name tie-break; support additionally requires bootstrap upper CI < 0 vs last4 baseline and >=3/5 fold wins",
    }


if __name__ == "__main__":
    print(f"NFL QB passing-yards bakeoff {VERSION} · {LINEAGE}")

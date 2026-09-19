"""MLB historical validation 0.1.0.

Read-only evaluation primitives for leakage-safe ML and pitcher-K ledgers.
No production model mutation, no market calls, no coefficient fitting.

Expected row conventions
------------------------
Common:
  game_id, game_date, season, season_type ("REG" or "POST"),
  model_variant (defaults to "PRODUCTION")

ML:
  market_type="ML", model_probability, actual_win (0/1)
  optional market_odds, closing_odds, market_probability, stage, thesis, trust

K:
  market_type="K", pitcher, side ("OVER"/"UNDER"), line, xk, actual_k
  model_probability is probability of chosen side
  optional market_odds, closing_odds, closing_line, stage, thesis, trust
"""
from __future__ import annotations

from collections import defaultdict
from math import log, sqrt
from random import Random
from statistics import fmean
from typing import Any, Iterable

VERSION = "0.1.2"
LINEAGE = "mlb-historical-validation-v0.1.2-diagnostic-splits-2026-09-19"
EPS = 1e-12


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def clamp_probability(p: float) -> float:
    return min(1.0 - EPS, max(EPS, float(p)))


def american_to_decimal(odds: float) -> float:
    o = float(odds)
    if o == 0:
        raise ValueError("American odds cannot be zero")
    return 1.0 + (o / 100.0 if o > 0 else 100.0 / abs(o))


def american_to_implied(odds: float) -> float:
    return 1.0 / american_to_decimal(odds)


def unit_profit(odds: float, outcome: float) -> float:
    """Profit for 1 unit risked; outcome 1 win, 0 loss, 0.5 push."""
    if outcome == 0.5:
        return 0.0
    if outcome not in (0.0, 1.0):
        raise ValueError(f"binary bet outcome required; got {outcome}")
    return american_to_decimal(odds) - 1.0 if outcome == 1.0 else -1.0


def brier_score(ps: list[float], ys: list[float]) -> float:
    if not ps or len(ps) != len(ys):
        raise ValueError("equal non-empty probability/outcome vectors required")
    return fmean((p - y) ** 2 for p, y in zip(ps, ys))


def log_loss(ps: list[float], ys: list[float]) -> float:
    if not ps or len(ps) != len(ys):
        raise ValueError("equal non-empty probability/outcome vectors required")
    return -fmean(
        y * log(clamp_probability(p)) + (1.0 - y) * log(1.0 - clamp_probability(p))
        for p, y in zip(ps, ys)
    )


def calibration(ps: list[float], ys: list[float], width: float = 0.10) -> dict[str, Any]:
    if not 0 < width <= 1:
        raise ValueError("calibration width must be in (0,1]")
    bins: dict[int, list[tuple[float, float]]] = defaultdict(list)
    count = int(round(1.0 / width))
    for p, y in zip(ps, ys):
        idx = min(count - 1, int(p / width))
        bins[idx].append((p, y))
    rows = []
    ece = 0.0
    n = len(ps)
    for idx in range(count):
        vals = bins.get(idx, [])
        if not vals:
            continue
        mp = fmean(p for p, _ in vals)
        my = fmean(y for _, y in vals)
        ece += len(vals) / n * abs(mp - my)
        rows.append(
            {
                "lower": round(idx * width, 6),
                "upper": round(min(1.0, (idx + 1) * width), 6),
                "n": len(vals),
                "mean_probability": mp,
                "actual_rate": my,
                "gap": mp - my,
            }
        )
    return {"ece": ece, "bins": rows}


def max_drawdown(profits: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for p in profits:
        equity += float(p)
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def _season_type(row: dict[str, Any]) -> str:
    x = _s(row.get("season_type")).upper()
    if x in {"POST", "POSTSEASON", "PLAYOFFS"}:
        return "POST"
    if x in {"REG", "REGULAR", "REGULAR_SEASON"}:
        return "REG"
    raise ValueError(f"unknown season_type: {row.get('season_type')!r}")


def _market_type(row: dict[str, Any]) -> str:
    x = _s(row.get("market_type")).upper()
    if x not in {"ML", "K"}:
        raise ValueError(f"market_type must be ML or K; got {x!r}")
    return x


def _k_outcome(row: dict[str, Any]) -> float:
    actual = float(row["actual_k"])
    line = float(row["line"])
    side = _s(row.get("side")).upper()
    if actual == line:
        return 0.5
    over = 1.0 if actual > line else 0.0
    if side == "OVER":
        return over
    if side == "UNDER":
        return 1.0 - over
    raise ValueError(f"K side must be OVER/UNDER; got {side!r}")


def _xk_only(row: dict[str, Any]) -> bool:
    return _market_type(row) == "K" and _s(row.get("evaluation_mode")).upper() == "XK_ONLY"


def _binary_outcome(row: dict[str, Any]) -> float:
    if _market_type(row) == "ML":
        y = float(row["actual_win"])
        if y not in (0.0, 1.0):
            raise ValueError("ML actual_win must be 0/1")
        return y
    if _xk_only(row):
        raise ValueError("XK_ONLY row has no binary market outcome")
    return _k_outcome(row)


def validate_row(row: dict[str, Any]) -> None:
    for key in ("game_id", "season", "season_type", "market_type"):
        if row.get(key) in (None, ""):
            raise ValueError(f"missing required field {key}")
    _season_type(row)
    mt = _market_type(row)
    if mt == "ML":
        if row.get("model_probability") in (None, ""):
            raise ValueError("ML row missing required field model_probability")
        p = float(row["model_probability"])
        if not 0 <= p <= 1:
            raise ValueError(f"model_probability outside [0,1]: {p}")
        _binary_outcome(row)
    else:
        for key in ("pitcher", "xk", "actual_k"):
            if row.get(key) in (None, ""):
                raise ValueError(f"K row missing required field {key}")
        if float(row["actual_k"]) < 0:
            raise ValueError("K actual_k must be nonnegative")
        if _xk_only(row):
            return
        for key in ("side", "line", "model_probability"):
            if row.get(key) in (None, ""):
                raise ValueError(f"K market row missing required field {key}")
        p = float(row["model_probability"])
        if not 0 <= p <= 1:
            raise ValueError(f"model_probability outside [0,1]: {p}")
        _binary_outcome(row)


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rs = [dict(r) for r in rows]
    if not rs:
        return {"n": 0}
    for r in rs:
        validate_row(r)

    scored = []
    for r in rs:
        if _xk_only(r):
            continue
        y = _binary_outcome(r)
        if y == 0.5:
            continue
        scored.append((float(r["model_probability"]), y, r))

    out: dict[str, Any] = {"n": len(rs), "scored_n": len(scored)}
    if scored:
        ps = [x[0] for x in scored]
        ys = [x[1] for x in scored]
        out.update(
            {
                "brier": brier_score(ps, ys),
                "log_loss": log_loss(ps, ys),
                "probability_bias": fmean(p - y for p, y in zip(ps, ys)),
                "accuracy": fmean(1.0 if (p >= 0.5) == bool(y) else 0.0 for p, y in zip(ps, ys)),
                "calibration": calibration(ps, ys),
            }
        )

    bet_rows = []
    for r in rs:
        if _xk_only(r):
            continue
        odds = _f(r.get("market_odds"))
        if odds is None:
            continue
        y = _binary_outcome(r)
        bet_rows.append((r, unit_profit(odds, y)))
    if bet_rows:
        profits = [
            p
            for _, p in sorted(
                bet_rows, key=lambda z: (_s(z[0].get("game_date")), _s(z[0].get("game_id")))
            )
        ]
        out["betting"] = {
            "n": len(profits),
            "profit_units": sum(profits),
            "roi": sum(profits) / len(profits),
            "max_drawdown_units": max_drawdown(profits),
        }

    clv = []
    for r in rs:
        entry = _f(r.get("market_odds"))
        close = _f(r.get("closing_odds"))
        if entry is None or close is None:
            continue
        clv.append(american_to_implied(close) - american_to_implied(entry))
    if clv:
        out["raw_implied_clv"] = {
            "n": len(clv),
            "mean_probability_points": 100.0 * fmean(clv),
            "beat_close_rate": fmean(1.0 if x > 0 else 0.0 for x in clv),
        }

    market_edges = []
    for r in rs:
        mp = _f(r.get("market_probability"))
        if mp is not None:
            market_edges.append(float(r["model_probability"]) - mp)
    if market_edges:
        out["vs_market"] = {
            "n": len(market_edges),
            "mean_edge_probability_points": 100.0 * fmean(market_edges),
        }

    krows = [r for r in rs if _market_type(r) == "K"]
    if krows:
        errs = [float(r["xk"]) - float(r["actual_k"]) for r in krows]
        out["xk"] = {
            "n": len(errs),
            "bias": fmean(errs),
            "mae": fmean(abs(e) for e in errs),
            "rmse": sqrt(fmean(e * e for e in errs)),
        }
    return out


def split_summary(rows: Iterable[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = _s(r.get(field)) or "UNKNOWN"
        groups[key].append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}


def _metric_value(rows: list[dict[str, Any]], metric: str) -> float | None:
    s = summarize(rows)
    if metric == "brier":
        return s.get("brier")
    if metric == "probability_bias":
        return s.get("probability_bias")
    if metric == "xk_mae":
        return (s.get("xk") or {}).get("mae")
    raise ValueError(metric)


def postseason_shift_bootstrap(
    rows: Iterable[dict[str, Any]],
    metric: str,
    reps: int = 2000,
    seed: int = 190926,
) -> dict[str, Any]:
    """Cluster bootstrap by season; reports POST minus REG metric difference."""
    rs = [dict(r) for r in rows]
    reg = [r for r in rs if _season_type(r) == "REG"]
    post = [r for r in rs if _season_type(r) == "POST"]
    observed_reg = _metric_value(reg, metric) if reg else None
    observed_post = _metric_value(post, metric) if post else None
    if observed_reg is None or observed_post is None:
        return {
            "metric": metric,
            "status": "INSUFFICIENT_DATA",
            "reg_n": len(reg),
            "post_n": len(post),
        }

    seasons = sorted({int(r["season"]) for r in rs})
    if len(seasons) < 2:
        return {
            "metric": metric,
            "status": "INSUFFICIENT_SEASONS",
            "reg_n": len(reg),
            "post_n": len(post),
        }

    by_season = {s: [r for r in rs if int(r["season"]) == s] for s in seasons}
    rng = Random(seed)
    diffs = []
    for _ in range(reps):
        sample = []
        for s in (rng.choice(seasons) for _ in seasons):
            sample.extend(by_season[s])
        sr = [r for r in sample if _season_type(r) == "REG"]
        sp = [r for r in sample if _season_type(r) == "POST"]
        a = _metric_value(sr, metric) if sr else None
        b = _metric_value(sp, metric) if sp else None
        if a is not None and b is not None:
            diffs.append(b - a)

    if len(diffs) < max(100, reps // 2):
        return {
            "metric": metric,
            "status": "INSUFFICIENT_BOOTSTRAP_COVERAGE",
            "bootstrap_n": len(diffs),
        }

    diffs.sort()

    def q(x: float) -> float:
        pos = (len(diffs) - 1) * x
        lo = int(pos)
        hi = min(len(diffs) - 1, lo + 1)
        frac = pos - lo
        return diffs[lo] * (1 - frac) + diffs[hi] * frac

    ci = [q(0.025), q(0.975)]
    obs = observed_post - observed_reg
    shifted = ci[0] > 0 or ci[1] < 0
    return {
        "metric": metric,
        "status": "POSTSEASON_SHIFT_DETECTED" if shifted else "NO_CLEAR_SHIFT",
        "reg_n": len(reg),
        "post_n": len(post),
        "reg_value": observed_reg,
        "post_value": observed_post,
        "post_minus_reg": obs,
        "cluster": "season",
        "bootstrap_reps": len(diffs),
        "ci95": ci,
    }


def paired_variant_comparison(
    rows: Iterable[dict[str, Any]], baseline: str, challenger: str
) -> dict[str, Any]:
    """Compare Brier loss on exactly matched non-push targets."""
    by_key: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        validate_row(r)
        if _xk_only(r):
            continue
        if _binary_outcome(r) == 0.5:
            continue
        target = _s(r.get("target"))
        if not target:
            if _market_type(r) == "ML":
                target = _s(r.get("selection_team")) or "ML_SELECTION"
            else:
                target = f"{_s(r.get('pitcher'))}|{_s(r.get('side')).upper()}|{r.get('line')}"
        by_key[(_s(r["game_id"]), target)][
            _s(r.get("model_variant")) or "PRODUCTION"
        ] = r

    diffs = []
    post_diffs = []
    for variants in by_key.values():
        if baseline not in variants or challenger not in variants:
            continue
        a = variants[baseline]
        b = variants[challenger]
        ya = _binary_outcome(a)
        yb = _binary_outcome(b)
        if ya != yb:
            raise ValueError("paired variants disagree on outcome")
        delta = (
            (float(b["model_probability"]) - yb) ** 2
            - (float(a["model_probability"]) - ya) ** 2
        )
        diffs.append(delta)
        if _season_type(a) == "POST":
            post_diffs.append(delta)

    if not diffs:
        return {
            "status": "NO_MATCHED_ROWS",
            "baseline": baseline,
            "challenger": challenger,
        }
    return {
        "status": "OK",
        "baseline": baseline,
        "challenger": challenger,
        "matched_n": len(diffs),
        "challenger_minus_baseline_brier": fmean(diffs),
        "postseason_matched_n": len(post_diffs),
        "postseason_challenger_minus_baseline_brier": (
            None if not post_diffs else fmean(post_diffs)
        ),
    }


def full_audit(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rs = [dict(r) for r in rows]
    for r in rs:
        validate_row(r)
    report = {
        "version": VERSION,
        "lineage": LINEAGE,
        "rows": len(rs),
        "overall": summarize(rs),
        "season_type": split_summary(rs, "season_type"),
        "market_type": split_summary(rs, "market_type"),
        "model_variant": split_summary(rs, "model_variant"),
        "season": split_summary(rs, "season"),
        "workload_proxy_source": split_summary(rs, "workload_proxy_source"),
        "park_resolution_method": split_summary(rs, "park_resolution_method"),
        "stage": split_summary(rs, "stage"),
        "thesis": split_summary(rs, "thesis"),
        "postseason_shift": {
            "brier": postseason_shift_bootstrap(rs, "brier"),
            "probability_bias": postseason_shift_bootstrap(rs, "probability_bias"),
        },
    }
    if any(_market_type(r) == "K" for r in rs):
        report["postseason_shift"]["xk_mae"] = postseason_shift_bootstrap(rs, "xk_mae")
    return report

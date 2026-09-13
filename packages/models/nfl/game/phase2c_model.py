"""Phase 2C feature vectorization and fast L2-logistic research fitter.

Historical-development only. 2025 remains sealed by the Phase 2C builders.
"""
from __future__ import annotations
from typing import Any, Sequence

VERSION = "0.3.1"
LINEAGE = "nfl-game-v0.3.1-qb-roster-transition-research-2026-09-10"

QB_SIMPLE_STEMS = ("qb_continuity", "qb_change_proxy", "qb_unresolved", "active_qb_count")
QB_METRICS = ("epa", "cpoe", "sack_rate", "explosive_pass_rate", "int_rate")
QB_HORIZONS = ("prior_season", "last4", "last8")
ROSTER_STEMS = (
    "offense_snap_continuity",
    "ol_snap_continuity",
    "skill_snap_continuity",
    "defense_snap_continuity",
    "active_roster_return_rate",
)


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _diff(row: dict[str, Any], stem: str) -> float | None:
    h = _num(row.get("home_" + stem))
    a = _num(row.get("away_" + stem))
    return None if h is None or a is None else h - a


def context_base_names() -> tuple[str, ...]:
    out = ["week1", "early_season"]
    out += [f"{s}_diff" for s in QB_SIMPLE_STEMS]
    for h in QB_HORIZONS:
        out += [f"{h}_qb_games_diff", f"{h}_qb_log_dropbacks_diff"]
        out += [f"{h}_qb_{m}_diff" for m in QB_METRICS]
    out += [f"{s}_diff" for s in ROSTER_STEMS]
    out += ["week1_qb_continuity_diff", "week1_qb_change_proxy_diff"]
    out += [f"week1_{s}_diff" for s in ROSTER_STEMS]
    return tuple(out)


def expanded_context_names() -> tuple[str, ...]:
    out: list[str] = []
    for n in context_base_names():
        out.extend([n, "missing__" + n])
    return tuple(out)


def vectorize_context(row: dict[str, Any]) -> tuple[float | None, ...]:
    vals: dict[str, float | None] = {}
    week = int(float(row.get("week") or 0))
    vals["week1"] = 1.0 if week == 1 else 0.0
    vals["early_season"] = 1.0 if 1 <= week <= 4 else 0.0
    for s in QB_SIMPLE_STEMS:
        vals[f"{s}_diff"] = _diff(row, s)
    for h in QB_HORIZONS:
        vals[f"{h}_qb_games_diff"] = _diff(row, f"{h}_qb_games")
        hd = _num(row.get(f"home_{h}_qb_dropbacks"))
        ad = _num(row.get(f"away_{h}_qb_dropbacks"))
        import math
        vals[f"{h}_qb_log_dropbacks_diff"] = (
            None if hd is None or ad is None else math.log1p(max(0.0, hd)) - math.log1p(max(0.0, ad))
        )
        for m in QB_METRICS:
            vals[f"{h}_qb_{m}_diff"] = _diff(row, f"{h}_qb_{m}")
    for s in ROSTER_STEMS:
        vals[f"{s}_diff"] = _diff(row, s)
    vals["week1_qb_continuity_diff"] = _diff(row, "week1_qb_continuity")
    vals["week1_qb_change_proxy_diff"] = _diff(row, "week1_qb_change_proxy")
    for s in ROSTER_STEMS:
        vals[f"week1_{s}_diff"] = _diff(row, f"week1_{s}")
    out: list[float | None] = []
    for n in context_base_names():
        v = vals[n]
        out.extend([v, 1.0 if v is None else 0.0])
    return tuple(out)


def _context_family(name: str) -> str:
    core = name[9:] if name.startswith("missing__") else name
    if any(s in core for s in ROSTER_STEMS):
        return "roster"
    if "qb_" in core:
        return "qb"
    if core in {"week1", "early_season"}:
        return "stage"
    return "other"


def combined_names(
    base_names: Sequence[str], *, include_qb: bool = True, include_roster: bool = True
) -> tuple[str, ...]:
    keep: list[str] = []
    for n in expanded_context_names():
        fam = _context_family(n)
        if fam == "qb" and include_qb:
            keep.append(n)
        elif fam == "roster" and include_roster:
            keep.append(n)
        elif fam == "stage" and (include_qb or include_roster):
            keep.append(n)
    return tuple(base_names) + tuple(keep)


def combined_vector(
    base_x: Sequence[float | None],
    row: dict[str, Any],
    base_names: Sequence[str],
    *,
    include_qb: bool = True,
    include_roster: bool = True,
) -> tuple[float | None, ...]:
    cx = vectorize_context(row)
    cn = expanded_context_names()
    selected = combined_names(base_names, include_qb=include_qb, include_roster=include_roster)
    idx = {n: i for i, n in enumerate(cn)}
    tail = [cx[idx[n]] for n in selected[len(base_names):]]
    return tuple(base_x) + tuple(tail)


class FastLogit:
    """NumPy-backed standardized L2 logistic model for Phase 2C research."""

    def __init__(self, names, means, scales, intercept, coefficients, l2, iterations, gradient_norm):
        self.names = tuple(names)
        self.means = list(means)
        self.scales = list(scales)
        self.intercept = float(intercept)
        self.coefficients = list(coefficients)
        self.l2 = float(l2)
        self.iterations = int(iterations)
        self.gradient_norm = float(gradient_norm)

    def predict(self, x):
        import math
        import numpy as np

        if len(x) != len(self.names):
            raise ValueError("feature vector length mismatch")
        a = np.asarray([np.nan if v is None else float(v) for v in x], dtype=float)
        means = np.asarray(self.means, dtype=float)
        scales = np.asarray(self.scales, dtype=float)
        a = np.where(np.isnan(a), means, a)
        z = self.intercept + float(np.dot(np.asarray(self.coefficients, dtype=float), (a - means) / scales))
        z = max(-40.0, min(40.0, z))
        return 1.0 / (1.0 + math.exp(-z))


def fit_fast_logit(xs, ys, names, *, l2: float, max_iter: int = 60, tolerance: float = 2e-6):
    """Fit standardized L2 logistic regression with damped Newton/IRLS.

    The objective is mean binary cross-entropy plus ``0.5*l2*||w||^2``;
    the intercept is not penalized. Means/scales and missing-value imputation are
    learned from the training fold only. A deterministic backtracking line search
    keeps every accepted Newton step non-increasing in objective value.
    """
    import math
    import numpy as np

    if not xs or len(xs) != len(ys):
        raise ValueError("bad design")
    if l2 < 0:
        raise ValueError("l2 must be nonnegative")
    X = np.asarray([[np.nan if v is None else float(v) for v in row] for row in xs], dtype=float)
    y = np.asarray(ys, dtype=float)
    if X.ndim != 2 or X.shape[1] != len(names):
        raise ValueError("feature dimension mismatch")
    if not np.all((y == 0.0) | (y == 1.0)):
        raise ValueError("binary target required")

    # Training-fold-only preprocessing.
    valid_counts = np.sum(~np.isnan(X), axis=0)
    sums = np.nansum(X, axis=0)
    means = np.divide(sums, valid_counts, out=np.zeros_like(sums), where=valid_counts > 0)
    X = np.where(np.isnan(X), means, X)
    scales = np.std(X, axis=0)
    scales = np.where(scales > 1e-12, scales, 1.0)
    X = (X - means) / scales

    n, p = X.shape
    Z = np.empty((n, p + 1), dtype=float)
    Z[:, 0] = 1.0
    Z[:, 1:] = X
    ybar = float(np.clip(np.mean(y), 1e-6, 1.0 - 1e-6))
    beta = np.zeros(p + 1, dtype=float)
    beta[0] = math.log(ybar / (1.0 - ybar))
    penalty = np.zeros(p + 1, dtype=float)
    penalty[1:] = float(l2)

    def objective(b):
        z = np.clip(Z @ b, -40.0, 40.0)
        # stable BCE: log(1+exp(z)) - y*z
        data = float(np.mean(np.logaddexp(0.0, z) - y * z))
        reg = 0.5 * float(l2) * float(np.dot(b[1:], b[1:]))
        return data + reg

    last_obj = objective(beta)
    grad_norm = float("inf")
    iterations = 0
    for it in range(1, max_iter + 1):
        z = np.clip(Z @ beta, -40.0, 40.0)
        prob = 1.0 / (1.0 + np.exp(-z))
        err = prob - y
        grad = (Z.T @ err) / float(n) + penalty * beta
        grad_norm = float(np.linalg.norm(grad))
        iterations = it
        if grad_norm < tolerance:
            break
        wdiag = np.maximum(prob * (1.0 - prob), 1e-8)
        hess = (Z.T @ (Z * wdiag[:, None])) / float(n)
        hess.flat[:: p + 2] += penalty
        # Tiny numerical damping only; L2 already regularizes coefficient block.
        hess.flat[:: p + 2] += 1e-10
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(hess, grad, rcond=None)[0]

        accepted = False
        alpha = 1.0
        directional = float(np.dot(grad, step))
        for _ in range(24):
            cand = beta - alpha * step
            cand_obj = objective(cand)
            if cand_obj <= last_obj - 1e-4 * alpha * max(directional, 0.0) + 1e-12:
                beta = cand
                last_obj = cand_obj
                accepted = True
                break
            alpha *= 0.5
        if not accepted:
            break

    return FastLogit(
        names,
        means.tolist(),
        scales.tolist(),
        float(beta[0]),
        beta[1:].tolist(),
        float(l2),
        iterations,
        grad_norm,
    )

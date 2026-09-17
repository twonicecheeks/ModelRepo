"""NFL QB Model 0.2.5 — frozen residual market-probability helpers.

This layer consumes an immutable 0.2.4 prospective score plus a quoted passing-yards
line/price. It never refits the QB model. Probability comes directly from the frozen
2020-2024 chronological OOF residual sample: for target projection m and line L,
P(Over) = empirical P(residual > L-m).

Initial scope intentionally accepts half-yard lines only. That makes settlement
binary and avoids inventing push mass from a continuous shifted-residual bootstrap.
Whole-number lines remain fail-closed until an explicit discrete settlement model is
validated.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Iterable, Sequence

try:
    import numpy as np
except Exception as exc:  # pragma: no cover
    np = None
    _NUMPY_IMPORT_ERROR = exc
else:
    _NUMPY_IMPORT_ERROR = None

VERSION = "0.2.5"
LINEAGE = "nfl-qb-passing-yards-frozen-oof-market-probability-v0.2.5-2026-09-16"
SOURCE_SCORE_VERSION = "0.2.4"
FROZEN_CANDIDATE = "MODEL_A_DIRECT"
BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = 20260918
ALLOWED_IDENTITY_SOURCES = frozenset({
    "DIRECT_SPORTSBOOK_MARKET",
    "OFFICIAL_STARTER_ANNOUNCEMENT",
    "USER_VERIFIED_EXTERNAL",
})
ALLOWED_MARKET_SOURCES = frozenset({
    "USER_ENTERED_DIRECT_SPORTSBOOK",
    "DIRECT_SPORTSBOOK_CAPTURE",
    "PROPSMADNESS_REFERENCE",
})


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def assert_score_ready(score: dict[str, Any]) -> None:
    if str(score.get("version")) != SOURCE_SCORE_VERSION:
        raise ValueError("QB 0.2.5 requires a 0.2.4 score")
    if score.get("status") != "PROSPECTIVE_SHADOW_SCORE_FROZEN_0.2.1":
        raise ValueError("QB 0.2.5 score status drift")
    if score.get("frozenCandidate") != FROZEN_CANDIDATE:
        raise ValueError("QB 0.2.5 frozen candidate drift")
    if score.get("coefficientRefitPerformed") is not False or score.get("candidateReselectionPerformed") is not False:
        raise ValueError("QB 0.2.5 refuses mutated prospective score")
    if int(score.get("targetOrLater2026OutcomeRowsAdmitted") or 0) != 0:
        raise ValueError("QB 0.2.5 prospective leakage detected")
    if int(score.get("marketPriceFieldsAdmitted") or 0) != 0:
        raise ValueError("QB 0.2.5 score must be model-only before market comparison")
    if int(score.get("oddsPapiRequests") or 0) != 0 or score.get("frozenOmegaMutation") is not False:
        raise ValueError("QB 0.2.5 market/OMEGA integrity drift")
    if score.get("nextGate") != "WIRE_VERIFIED_IDENTITY_BRIDGE_AND_MARKET_LINE_PROBABILITY_WITHOUT_REFIT":
        raise ValueError("QB 0.2.5 source next-gate drift")
    target = score.get("target") or {}
    if clean(target.get("identitySource")) not in ALLOWED_IDENTITY_SOURCES:
        raise ValueError("QB 0.2.5 target identity is not verified")
    if not clean(target.get("game_id")) or not clean(target.get("qb_gsis_id")):
        raise ValueError("QB 0.2.5 target identity incomplete")


def assert_half_yard_line(line: float) -> float:
    x = float(line)
    twice = round(x * 2.0)
    if abs(x * 2.0 - twice) > 1e-9 or int(twice) % 2 != 1:
        raise ValueError("QB 0.2.5 initial market bridge supports half-yard lines only; whole-number push semantics are not yet authorized")
    if x < 0.5 or x > 700.5:
        raise ValueError("passing-yards line out of supported range")
    return x


def validate_american(price: int | float) -> int:
    x = int(price)
    if x == 0 or abs(x) < 100:
        raise ValueError(f"invalid American odds: {price}")
    return x


def american_to_decimal(price: int | float) -> float:
    x = validate_american(price)
    return 1.0 + (100.0 / abs(x) if x < 0 else x / 100.0)


def implied_probability(price: int | float) -> float:
    return 1.0 / american_to_decimal(price)


def fair_american(probability: float) -> int | None:
    p = float(probability)
    if not (0.0 < p < 1.0):
        return None
    if p >= 0.5:
        return int(round(-100.0 * p / (1.0 - p)))
    return int(round(100.0 * (1.0 - p) / p))


def expected_roi(probability: float, price: int | float) -> float:
    p = float(probability)
    dec = american_to_decimal(price)
    return p * (dec - 1.0) - (1.0 - p)


def no_vig_two_way(over_price: int | float, under_price: int | float) -> dict[str, float]:
    po = implied_probability(over_price)
    pu = implied_probability(under_price)
    den = po + pu
    if den <= 0:
        raise ValueError("invalid two-way market probabilities")
    return {
        "overRawImplied": po,
        "underRawImplied": pu,
        "hold": den - 1.0,
        "overNoVig": po / den,
        "underNoVig": pu / den,
    }


def residual_rows(oof_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in oof_rows:
        season = int(raw.get("season") or 0)
        if season not in {2020, 2021, 2022, 2023, 2024}:
            raise ValueError(f"OOF residual source season drift: {season}")
        gid = clean(raw.get("game_id"))
        if not gid:
            raise ValueError("OOF residual row missing game_id")
        if raw.get("actual_passing_yards") is None or raw.get(FROZEN_CANDIDATE) is None:
            raise ValueError("OOF residual row missing actual/model value")
        residual = float(raw["actual_passing_yards"]) - float(raw[FROZEN_CANDIDATE])
        out.append({"game_id": gid, "residual": residual})
    if not out:
        raise ValueError("no frozen OOF residual rows")
    return out


def empirical_market_probability(residuals: Sequence[dict[str, Any]], point_projection: float, line: float) -> dict[str, Any]:
    ln = assert_half_yard_line(line)
    point = float(point_projection)
    threshold = ln - point
    vals = [float(r["residual"]) for r in residuals]
    over = sum(v > threshold for v in vals) / len(vals)
    under = 1.0 - over
    return {
        "n": len(vals),
        "pointProjection": point,
        "line": ln,
        "residualThresholdOver": threshold,
        "overProbability": over,
        "underProbability": under,
        "pushProbability": 0.0,
        "method": "FROZEN_CHRONOLOGICAL_OOF_EMPIRICAL_RESIDUAL_CDF",
    }


def cluster_bootstrap_probability(
    residuals: Sequence[dict[str, Any]],
    point_projection: float,
    line: float,
    *,
    reps: int = BOOTSTRAP_REPS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    if np is None:
        raise RuntimeError(f"numpy required: {_NUMPY_IMPORT_ERROR}")
    if not residuals:
        raise ValueError("no residuals for probability bootstrap")
    ln = assert_half_yard_line(line)
    threshold = ln - float(point_projection)
    by_game: dict[str, list[float]] = defaultdict(list)
    for row in residuals:
        by_game[clean(row.get("game_id"))].append(float(row["residual"]))
    gids = sorted(k for k in by_game if k)
    if not gids:
        raise ValueError("no game clusters for probability bootstrap")

    def p_over(sample: Sequence[float]) -> float:
        return sum(x > threshold for x in sample) / len(sample)

    point_vals = [x for g in gids for x in by_game[g]]
    point = p_over(point_vals)
    rng = np.random.default_rng(int(seed))
    sims: list[float] = []
    n = len(gids)
    for _ in range(int(reps)):
        chosen = rng.integers(0, n, size=n)
        sample: list[float] = []
        for idx in chosen:
            sample.extend(by_game[gids[int(idx)]])
        sims.append(p_over(sample))
    sims.sort()
    lo = sims[max(0, int(0.025 * len(sims)))]
    hi = sims[min(len(sims) - 1, int(0.975 * len(sims)))]
    return {
        "overProbability": point,
        "overCi95": [lo, hi],
        "underProbability": 1.0 - point,
        "underCi95": [1.0 - hi, 1.0 - lo],
        "reps": int(reps),
        "seed": int(seed),
        "cluster": "game_id",
    }


def market_side_summary(probability: float, price: int | None, no_vig_probability: float | None = None) -> dict[str, Any]:
    p = float(probability)
    out: dict[str, Any] = {
        "modelProbability": p,
        "modelFairAmerican": fair_american(p),
        "offeredAmerican": None,
        "offeredImpliedProbability": None,
        "expectedRoi": None,
        "expectedRoiPct": None,
        "edgeVsNoVigProbabilityPoints": None,
    }
    if price is not None:
        px = validate_american(price)
        roi = expected_roi(p, px)
        out.update({
            "offeredAmerican": px,
            "offeredImpliedProbability": implied_probability(px),
            "expectedRoi": roi,
            "expectedRoiPct": 100.0 * roi,
        })
    if no_vig_probability is not None:
        out["edgeVsNoVigProbabilityPoints"] = 100.0 * (p - float(no_vig_probability))
    return out


if __name__ == "__main__":
    print(f"NFL QB passing-yards market helpers {VERSION} · {LINEAGE}")

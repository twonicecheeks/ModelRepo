"""NFL 2.9.0 Phase 2F frozen-spec and one-shot holdout primitives.

This module contains no sportsbook dependency. Phase 2F freezes the independent
Phase 2E SAFE specification before 2025 labels are scored, then evaluates that
specification once. 2025 is never fit and never used to select features, lambda,
or stage weights.
"""
from __future__ import annotations
from math import log
from statistics import fmean
from typing import Any, Sequence

VERSION = "0.6.0"
LINEAGE = "nfl-game-v0.6.0-frozen-2025-holdout-gate-2026-09-10"
HOLDOUT_SEASON = 2025
TRAIN_SEASONS = tuple(range(2016, 2025))
SAFE_VARIANT = "safe_no_last4_no_turnover_no_rush_epa"
SAFE_L2 = 0.3
BASE_L2 = 0.3
STAGE_WEIGHTS = {"week1": 0.0, "weeks2to4": 1.0, "week5plus": 0.75}


def season_stage(week: int) -> str:
    w = int(week)
    if w == 1:
        return "week1"
    if 2 <= w <= 4:
        return "weeks2to4"
    return "week5plus"


def clip_prob(p: float) -> float:
    return min(1.0 - 1e-12, max(1e-12, float(p)))


def blend_probability(p_base: float, p_context: float, week: int) -> float:
    w = STAGE_WEIGHTS[season_stage(week)]
    return clip_prob((1.0 - w) * float(p_base) + w * float(p_context))


def selected_feature_keep(name: str) -> bool:
    """Locked Phase 2F SAFE feature rule.

    The selected Phase 2E candidate excludes last-4, turnover/takeaway/QB INT,
    and rushing-EPA feature families. Missing-indicator twins are excluded by
    the same substring rule.
    """
    n = str(name)
    if "last4_" in n:
        return False
    if any(s in n for s in ("off_turnover_rate", "def_takeaway_rate", "qb_int_rate")):
        return False
    if any(s in n for s in ("off_rush_epa", "def_rush_epa_allowed")):
        return False
    return True


def verdict(base_brier: float, primary_brier: float, base_logloss: float, primary_logloss: float,
            brier_ci_low: float | None = None, logloss_ci_low: float | None = None) -> str:
    """Precommitted one-shot 2025 verdict policy.

    STRONG_PASS: both proper scores improve and both paired weekly-bootstrap
    lower bounds are >0. DIRECTIONAL_PASS: both point estimates improve but
    strong uncertainty support is absent. FAIL_BOTH: both proper scores worsen.
    MIXED: all other outcomes. No threshold is tuned after seeing 2025.
    """
    b_ok = float(primary_brier) < float(base_brier)
    l_ok = float(primary_logloss) < float(base_logloss)
    if b_ok and l_ok:
        if brier_ci_low is not None and logloss_ci_low is not None and float(brier_ci_low) > 0.0 and float(logloss_ci_low) > 0.0:
            return "STRONG_PASS"
        return "DIRECTIONAL_PASS"
    if (not b_ok) and (not l_ok):
        return "FAIL_BOTH"
    return "MIXED"


def metric_summary(ys: Sequence[int], ps: Sequence[float]) -> dict[str, float | int]:
    if not ys or len(ys) != len(ps):
        raise ValueError("paired y/p required")
    pp = [clip_prob(x) for x in ps]
    n = len(ys)
    return {
        "n": n,
        "brier": fmean((p-int(y))**2 for y,p in zip(ys,pp)),
        "logLoss": fmean(-(int(y)*log(p)+(1-int(y))*log(1-p)) for y,p in zip(ys,pp)),
        "accuracy": fmean((p >= 0.5) == bool(y) for y,p in zip(ys,pp)),
        "meanPrediction": fmean(pp),
        "observedHomeWinRate": fmean(int(y) for y in ys),
    }

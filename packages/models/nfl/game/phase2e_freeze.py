"""NFL 2.9.0 Phase 2E safe feature-freeze primitives.

Research-only and pre-holdout. No sportsbook dependency. Phase 2E converts the
Phase 2D findings into two deliberately separate branches:

1) SAFE branch: strict-lag QB/personnel context only, with no target-week roster.
2) INFORMATION upper bound: target-week context, still provenance-gated.

Model/feature choice and season-stage blending are selected only on 2018-2021
walk-forward OOF predictions. 2022-2024 are evaluation-only for this phase.
2025 remains sealed.
"""
from __future__ import annotations

from math import log
from statistics import fmean
from typing import Any, Sequence

VERSION = "0.5.0"
LINEAGE = "nfl-game-v0.5.0-safe-freeze-candidate-2026-09-10"
HOLDOUT_SEASON = 2025
SELECTION_SEASONS = (2018, 2019, 2020, 2021)
EVALUATION_SEASONS = (2022, 2023, 2024)
L2_GRID = (0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
BLEND_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


def season_stage(week: int) -> str:
    w = int(week)
    if w == 1:
        return "week1"
    if 2 <= w <= 4:
        return "weeks2to4"
    return "week5plus"


def blend_probability(p_base: float, p_context: float, weight: float) -> float:
    w = float(weight)
    if not 0.0 <= w <= 1.0:
        raise ValueError("blend weight must be within [0,1]")
    p = (1.0 - w) * float(p_base) + w * float(p_context)
    return min(1.0 - 1e-12, max(1e-12, p))


def candidate_keep(name: str, *, no_turnover: bool = False, no_rush_epa: bool = False) -> bool:
    """Phase 2E candidate-family feature filter.

    last-4 features are always removed because Phase 2D's strongest challenger
    improved after removing that entire horizon. Turnover and rushing EPA are
    explicit selection candidates rather than hand-edited assumptions.
    """
    if "last4_" in name:
        return False
    if no_turnover and any(s in name for s in ("off_turnover_rate", "def_takeaway_rate", "qb_int_rate")):
        return False
    if no_rush_epa and any(s in name for s in ("off_rush_epa", "def_rush_epa_allowed")):
        return False
    return True


def score_summary(ys: Sequence[int], ps: Sequence[float]) -> dict[str, float]:
    if not ys or len(ys) != len(ps):
        raise ValueError("paired y/p required")
    n = len(ys)
    brier = fmean((float(p) - int(y)) ** 2 for y, p in zip(ys, ps))
    ll = fmean(-(int(y) * log(float(p)) + (1-int(y)) * log(1-float(p))) for y, p in zip(ys, ps))
    acc = fmean((float(p) >= .5) == bool(y) for y, p in zip(ys, ps))
    return {"n": n, "brier": brier, "logLoss": ll, "accuracy": acc}


def select_stage_weights(records: Sequence[dict[str, Any]], *, base_field: str, context_field: str) -> dict[str, Any]:
    """Select stage weights using only supplied selection OOF rows.

    Primary objective is log loss, then Brier, then lower context weight. The
    last tie-break deliberately prefers less complexity when scores are equal.
    """
    out: dict[str, Any] = {}
    for stage in ("week1", "weeks2to4", "week5plus"):
        rows = [r for r in records if season_stage(int(r["week"])) == stage]
        if not rows:
            raise ValueError(f"no selection rows for {stage}")
        candidates = []
        ys = [int(r["y"]) for r in rows]
        for w in BLEND_GRID:
            ps = [blend_probability(float(r[base_field]), float(r[context_field]), w) for r in rows]
            candidates.append({"contextWeight": w, **score_summary(ys, ps)})
        candidates.sort(key=lambda x: (x["logLoss"], x["brier"], x["contextWeight"]))
        out[stage] = {"selected": candidates[0], "candidates": candidates}
    return out


def apply_stage_weights(records: Sequence[dict[str, Any]], *, base_field: str, context_field: str, weights: dict[str, Any]) -> list[float]:
    out = []
    for r in records:
        stage = season_stage(int(r["week"]))
        w = float(weights[stage]["selected"]["contextWeight"])
        out.append(blend_probability(float(r[base_field]), float(r[context_field]), w))
    return out


def variant_name(prefix: str, no_turnover: bool, no_rush_epa: bool) -> str:
    bits = [prefix, "no_last4"]
    if no_turnover:
        bits.append("no_turnover")
    if no_rush_epa:
        bits.append("no_rush_epa")
    return "_".join(bits)

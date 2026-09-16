"""NFL QB State 0.1.8 — official-stat reconciliation for the final air/YAC anomaly.

Development-only. This module resolves the final 0.1.7 blocker without rewriting
source statistics. Official nflverse passing_yards remains the settlement/target
truth; air_yards + yards_after_catch is only a component decomposition and may be
quarantined when it disagrees with an otherwise coherent official receiving stat.
"""
from __future__ import annotations

from math import isnan
from typing import Any, Iterable

VERSION = "0.1.8"
LINEAGE = "nfl-qb-state-semantic-reconciliation-v0.1.8-m41-m48-m87-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025


def num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if isnan(x) else x


def flag(v: Any) -> bool:
    return num(v) == 1.0


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    vals = tuple(sorted({int(s) for s in seasons}))
    if not vals:
        raise ValueError("at least one development season is required")
    bad = [s for s in vals if s >= SEALED_HOLDOUT_SEASON]
    if bad:
        raise ValueError("0.1.8 is development-only; sealed 2025+ forbidden: " + ",".join(map(str, bad)))
    return vals


def official_receiving_reconciliation(row: dict[str, Any], *, tol: float = 1e-9) -> dict[str, Any]:
    py = num(row.get("passing_yards"))
    ry = num(row.get("receiving_yards"))
    lry = num(row.get("lateral_receiving_yards"))
    lateral = flag(row.get("lateral_reception"))
    result: dict[str, Any] = {
        "passing_yards": py,
        "receiving_yards": ry,
        "lateral_receiving_yards": lry,
        "lateral_reception": lateral,
        "official_nonlateral_match": False,
        "official_with_lateral_match": False,
    }
    if py is not None and ry is not None:
        result["official_nonlateral_match"] = (not lateral) and abs(py - ry) <= tol
        total = ry + (lry or 0.0)
        result["official_with_lateral_match"] = abs(py - total) <= tol
    return result


def reconciliation_class(row: dict[str, Any]) -> str:
    rec = official_receiving_reconciliation(row)
    if rec["official_nonlateral_match"]:
        return "OFFICIAL_STAT_COHERENT_AIR_YAC_COMPONENT_MISMATCH"
    if rec["official_with_lateral_match"]:
        return "OFFICIAL_STAT_COHERENT_LATERAL_ACCOUNTING"
    return "UNRESOLVED_OFFICIAL_STAT_MISMATCH"


def model_fit_authorized(*, prior_nonreview_conflicts: int, unresolved_rows: int, reconciled_rows: int) -> bool:
    return prior_nonreview_conflicts == 0 and unresolved_rows == 0 and reconciled_rows > 0


if __name__ == "__main__":
    print(f"NFL QB semantic reconciliation {VERSION} · {LINEAGE}")

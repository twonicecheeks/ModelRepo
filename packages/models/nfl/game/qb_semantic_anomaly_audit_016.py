"""NFL QB State 0.1.6 — semantic anomaly attribution helpers.

Development-only diagnostic. It does not fit coefficients or modify 0.1.5 artifacts.
It exists because 0.1.5 surfaced two tiny residual classes that must be understood
before model fitting: sack+scramble flag conflicts and completion air+YAC residuals.
"""
from __future__ import annotations

from math import isnan
from typing import Any, Iterable

VERSION = "0.1.6"
LINEAGE = "nfl-qb-state-semantic-anomaly-audit-v0.1.6-2026-09-16"
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
        raise ValueError("0.1.6 is development-only; sealed 2025+ forbidden: " + ",".join(map(str, bad)))
    return vals


def completion_residual(row: dict[str, Any]) -> float | None:
    py = num(row.get("passing_yards"))
    ay = num(row.get("air_yards"))
    yac = num(row.get("yards_after_catch"))
    if py is None or ay is None or yac is None:
        return None
    return py - (ay + yac)


def residual_class(row: dict[str, Any], *, tol: float = 1e-9) -> str:
    r = completion_residual(row)
    if r is None:
        return "MISSING_COMPONENT"
    if abs(r) <= tol:
        return "EXACT"
    if flag(row.get("lateral_reception")):
        return "LATERAL_RECEPTION"
    return "UNEXPLAINED_NONLATERAL"


def sack_scramble_conflict(row: dict[str, Any]) -> bool:
    return flag(row.get("sack")) and flag(row.get("qb_scramble"))


if __name__ == "__main__":
    print(f"NFL QB semantic anomaly audit {VERSION} · {LINEAGE}")

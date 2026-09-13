"""OMEGA 0.12 blind 2025 holdout ledger helpers.

This module is pinned to the explicit OMEGA 0.11 frozen specification.  It contains
no sportsbook logic and no scoring logic.  The blind ledger may contain model
predictions and strictly-prior features only; target tackle/snap outcomes are
forbidden from serialization.
"""
from __future__ import annotations

from typing import Any, Iterable

VERSION = "0.12.0"
LINEAGE = "omega-tackle-v0.12.0-blind-2025-ledger-2026-09-11"
FROZEN_SPEC_SHA256 = "c2ca80b6a144c3aa86bc41bdb82f6f5618ffa279a38f4c6d358025ed7fbd69fb"

FORBIDDEN_OUTPUT_FIELDS = {
    "actual_xtc", "actual_snap_share", "actual_defensive_snaps",
    "combined_standard_def_scrimmage", "combined_all", "solo",
    "primary_with_assist", "assists", "defense_snaps", "defense_pct",
    "actual_opportunity_plays", "actual_credit_units",
}


def assert_blind_schema(field_names: Iterable[str]) -> None:
    fields = {str(x) for x in field_names}
    bad = sorted(fields & FORBIDDEN_OUTPUT_FIELDS)
    bad += sorted(x for x in fields if x.startswith("actual_") and x not in bad)
    if bad:
        raise ValueError("blind ledger contains target/outcome field(s): " + ", ".join(sorted(set(bad))))


def truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    try:
        return int(float(v)) != 0
    except Exception:
        return str(v or "").strip().lower() in {"true", "yes", "y", "t"}


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

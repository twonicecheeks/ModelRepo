"""NFL QB State 0.1.0 — leakage-safe data/identity capability audit helpers.

This module is deliberately coefficient-free. It exists to determine whether the
current immutable nflverse snapshot can support the DEN@KC QB architecture without
opening the sealed 2025 holdout or inferring pregame starters from current-game PBP.
"""
from __future__ import annotations

from math import isnan
from typing import Any, Iterable

VERSION = "0.1.0"
LINEAGE = "nfl-qb-state-data-audit-v0.1.0-den-kc-m31-m36-m39-m41-m48-m50-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

PBP_FIELDS = (
    "game_id", "season", "week", "posteam", "defteam",
    "qb_dropback", "pass_attempt", "complete_pass", "incomplete_pass",
    "sack", "qb_scramble", "rush_attempt", "qb_kneel", "no_play", "play_type",
    "passer_player_id", "passer_player_name", "rusher_player_id", "rusher_player_name",
    "receiver_player_id", "receiver_player_name",
    "passing_yards", "air_yards", "yards_after_catch", "yards_gained",
    "cpoe", "cp", "qb_epa", "epa", "interception",
    "xyac_mean_yardage", "xyac_epa",
)

QB_CORE_FIELDS = (
    "passer_player_id", "pass_attempt", "complete_pass", "sack", "qb_scramble",
    "passing_yards", "air_yards", "yards_after_catch", "cpoe", "qb_epa",
)

STARTER_SEMANTIC_TERMS = (
    "starter", "depth", "order", "rank", "first_team", "string", "slot",
)


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    values = tuple(sorted({int(s) for s in seasons}))
    if not values:
        raise ValueError("at least one development season is required")
    forbidden = [s for s in values if s >= SEALED_HOLDOUT_SEASON]
    if forbidden:
        raise ValueError(
            "QB State 0.1.0 is development-only; sealed 2025 and prospective 2026+ are forbidden: "
            + ",".join(map(str, forbidden))
        )
    return values


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return None if isnan(x) else x


def flag(value: Any) -> bool:
    return num(value) == 1.0


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and isnan(value):
        return False
    return str(value).strip() != ""


def pct(n: int | float, d: int | float) -> float | None:
    return None if not d else 100.0 * float(n) / float(d)


def candidate_starter_fields(schema_names: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for raw in schema_names:
        name = str(raw)
        low = name.lower()
        if any(term in low for term in STARTER_SEMANTIC_TERMS):
            out.append(name)
    return tuple(sorted(set(out)))


def authoritative_order_candidates(schema_names: Iterable[str]) -> tuple[str, ...]:
    """Return fields that could encode depth ordering rather than mere position.

    `depth_chart_position` is intentionally excluded: QB merely identifies a player's
    position group and does not establish QB1/QB2 ordering by itself.
    """
    out: list[str] = []
    for raw in schema_names:
        name = str(raw)
        low = name.lower()
        if low == "depth_chart_position":
            continue
        if "starter" in low or "first_team" in low:
            out.append(name)
            continue
        if "depth" in low and any(term in low for term in ("order", "rank", "slot", "number", "string")):
            out.append(name)
    return tuple(sorted(set(out)))


def coverage_status(found: dict[str, bool]) -> str:
    missing = [f for f in QB_CORE_FIELDS if not found.get(f, False)]
    if not missing:
        return "CORE_QB_PBP_SCHEMA_AVAILABLE"
    if len(missing) <= 2:
        return "CORE_QB_PBP_SCHEMA_PARTIAL"
    return "CORE_QB_PBP_SCHEMA_INSUFFICIENT"


def identity_status(*, unique_passers: int, resolved_passers: int, attributed_dropbacks: int, resolved_dropbacks: int) -> str:
    if unique_passers <= 0 or attributed_dropbacks <= 0:
        return "NO_USABLE_PASSER_IDENTITY"
    unique_pct = resolved_passers / unique_passers
    db_pct = resolved_dropbacks / attributed_dropbacks
    if unique_pct >= 0.995 and db_pct >= 0.999:
        return "GSIS_IDENTITY_STRONG"
    if unique_pct >= 0.98 and db_pct >= 0.99:
        return "GSIS_IDENTITY_USABLE_WITH_QUARANTINE"
    return "GSIS_IDENTITY_REVIEW_REQUIRED"


def roster_starter_status(order_fields: Iterable[str]) -> str:
    return "STARTER_ORDER_FIELDS_REQUIRE_SEMANTIC_REVIEW" if tuple(order_fields) else "NO_AUTHORITATIVE_STARTER_ORDER_FIELD_OBSERVED"


def depth_chart_source_status(*, asset_present: bool, contract_status: str | None) -> str:
    if asset_present:
        return "DEPTH_CHART_ASSET_PRESENT_REQUIRES_ADAPTER_AUDIT"
    if str(contract_status or "").upper().startswith("DEFERRED"):
        return "DECLARED_BUT_NOT_CAPTURED_DEFERRED_ADAPTER"
    return "DEPTH_CHART_SOURCE_NOT_CAPTURED"


if __name__ == "__main__":
    print(f"NFL QB State data audit helpers {VERSION} · {LINEAGE}")

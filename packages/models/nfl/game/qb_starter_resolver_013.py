"""NFL QB State 0.1.3 — conservative historical pregame starter resolver.

The resolver combines only information that can be made pregame-safe for the target
team-game: a legacy weekly depth-chart QB1 proxy, the target-week roster active
proxy, and strictly lagged observed primary-QB history. Current-game PBP is never an
input to resolution; it is allowed only as a retrospective validation label in the
audit script.

The legacy nflverse depth source lacks an exact pregame publication timestamp, so
successful resolution remains a HISTORICAL_PROXY, not authoritative provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

VERSION = "0.1.3"
LINEAGE = "nfl-qb-state-starter-resolver-v0.1.3-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

STRICT_RULES = frozenset({
    "CONSENSUS_INCUMBENT_ACTIVE",
    "FORCED_CHANGE_DEPTH_ACTIVE",
    "ROSTER_SINGLETON",
})

EXTENDED_RULES = STRICT_RULES | frozenset({
    "INCUMBENT_ACTIVE_DEPTH_UNRESOLVED",
    "DEPTH_ACTIVE_NO_PRIOR",
})


@dataclass(frozen=True)
class Resolution:
    qb_gsis_id: str
    rule: str
    resolved: bool
    confidence_tier: str


def _clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    values = tuple(sorted({int(s) for s in seasons}))
    if not values:
        raise ValueError("at least one development season is required")
    bad = [s for s in values if s >= SEALED_HOLDOUT_SEASON]
    if bad:
        raise ValueError(
            "QB starter resolver is development-only; sealed 2025 / prospective 2026+ forbidden: "
            + ",".join(map(str, bad))
        )
    return values


def resolve_starter(
    *,
    prior_primary_qb: str | None,
    depth_qb1: str | None,
    active_qbs: Iterable[str],
) -> Resolution:
    """Return a deterministic pregame-safe historical starter proxy.

    Rule order is intentionally conservative and deterministic. `active_qbs` is the
    weekly-roster ACT proxy, not an official game-day inactive list.
    """
    prior = _clean(prior_primary_qb)
    depth = _clean(depth_qb1)
    active = tuple(sorted({_clean(x) for x in active_qbs if _clean(x)}))
    aset = set(active)

    if len(active) == 1:
        return Resolution(active[0], "ROSTER_SINGLETON", True, "HIGH")

    if prior and depth and prior == depth and depth in aset:
        return Resolution(depth, "CONSENSUS_INCUMBENT_ACTIVE", True, "HIGH")

    if prior and depth and prior != depth and prior not in aset and depth in aset:
        return Resolution(depth, "FORCED_CHANGE_DEPTH_ACTIVE", True, "HIGH")

    if prior and prior in aset and not depth:
        return Resolution(prior, "INCUMBENT_ACTIVE_DEPTH_UNRESOLVED", True, "MEDIUM")

    if not prior and depth and depth in aset:
        return Resolution(depth, "DEPTH_ACTIVE_NO_PRIOR", True, "MEDIUM")

    if depth and depth not in aset:
        return Resolution("", "DEPTH_QB1_NOT_ACTIVE_PROXY", False, "UNRESOLVED")

    if prior and depth and prior != depth and prior in aset and depth in aset:
        return Resolution("", "ACTIVE_QB_CONFLICT", False, "UNRESOLVED")

    if prior and prior not in aset and not depth:
        return Resolution("", "INCUMBENT_ABSENT_NO_DEPTH", False, "UNRESOLVED")

    if not prior and not depth:
        return Resolution("", "NO_PRIOR_NO_DEPTH", False, "UNRESOLVED")

    return Resolution("", "UNRESOLVED_OTHER", False, "UNRESOLVED")


def eligible_for_variant(resolution: Resolution, variant: str) -> bool:
    name = str(variant).strip().upper()
    if not resolution.resolved:
        return False
    if name == "STRICT":
        return resolution.rule in STRICT_RULES
    if name == "EXTENDED":
        return resolution.rule in EXTENDED_RULES
    if name == "ALL_RESOLVED":
        return True
    raise ValueError(f"unknown resolver variant: {variant}")


def gate(*, coverage_pct: float, first_qb_accuracy_pct: float) -> str:
    """Conservative research gate for historical development use only."""
    if coverage_pct >= 75.0 and first_qb_accuracy_pct >= 97.0:
        return "HISTORICAL_STARTER_RESOLVER_READY_FOR_QB_CHALLENGER"
    if coverage_pct >= 60.0 and first_qb_accuracy_pct >= 95.0:
        return "HISTORICAL_STARTER_RESOLVER_USABLE_WITH_QUARANTINE"
    return "HISTORICAL_STARTER_RESOLVER_NOT_READY"


if __name__ == "__main__":
    print(f"NFL QB starter resolver {VERSION} · {LINEAGE}")

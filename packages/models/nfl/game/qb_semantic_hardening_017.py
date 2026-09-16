"""NFL QB State 0.1.7 — semantic hardening after anomaly attribution.

Development-only. This module does not fit a model. It decides whether the rare
0.1.6 residual classes are attributable enough to authorize the next chronological
QB challenger with explicit quarantine rules.

Key policy:
- official/statistical totals remain authoritative settlement targets;
- rare replay flag conflicts are not force-labeled as sack or scramble for component
  training;
- air+YAC residual completions may be excluded from clean component fits only when
  they are explicitly attributed to laterals or fumble/recovery sequences;
- sealed 2025 and prospective 2026 are never read here.
"""
from __future__ import annotations

from math import isnan
from typing import Any, Iterable

VERSION = "0.1.7"
LINEAGE = "nfl-qb-state-semantic-hardening-v0.1.7-2026-09-16"
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


def present(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, float) and isnan(v):
        return False
    return str(v).strip() != ""


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    vals = tuple(sorted({int(s) for s in seasons}))
    if not vals:
        raise ValueError("at least one development season is required")
    bad = [s for s in vals if s >= SEALED_HOLDOUT_SEASON]
    if bad:
        raise ValueError("0.1.7 is development-only; sealed 2025+ forbidden: " + ",".join(map(str, bad)))
    return vals


def replay_review_evidence(row: dict[str, Any]) -> bool:
    text = clean(row.get("desc")).upper()
    return any(token in text for token in (
        "REPLAY OFFICIAL",
        "REVIEWED",
        "CHALLENGED",
        "REPLAY REVIEW",
    ))


def fumble_evidence(row: dict[str, Any]) -> dict[str, bool]:
    text = clean(row.get("desc")).upper()
    recovery_fields = (
        "fumble_recovery_1_team",
        "fumble_recovery_1_player_id",
        "fumble_recovery_1_yards",
        "fumble_recovery_2_team",
        "fumble_recovery_2_player_id",
        "fumble_recovery_2_yards",
    )
    recovery_present = any(present(row.get(k)) for k in recovery_fields)
    out = {
        "fumble_flag": flag(row.get("fumble")),
        "fumble_lost": flag(row.get("fumble_lost")),
        "fumble_out_of_bounds": flag(row.get("fumble_out_of_bounds")),
        "recovery_present": recovery_present,
        "description_fumble": "FUMBLE" in text,
    }
    out["any"] = any(out.values())
    return out


def classify_nonlateral_residual(row: dict[str, Any]) -> str:
    if flag(row.get("lateral_reception")):
        return "LATERAL_RECEPTION"
    return "FUMBLE_SEQUENCE" if fumble_evidence(row)["any"] else "UNEXPLAINED_NONFUMBLE"


def disposition(*, other_dropbacks: int, conflict_rows: int, nonreview_conflicts: int, unexplained_nonfumble: int) -> str:
    if other_dropbacks:
        return "STRUCTURAL_OTHER_REQUIRES_REVIEW"
    if nonreview_conflicts:
        return "DROPBACK_CONFLICT_REQUIRES_REVIEW"
    if unexplained_nonfumble:
        return "PASSING_RESIDUAL_REQUIRES_REVIEW"
    if conflict_rows:
        return "SEMANTICS_HARDENED_WITH_RARE_EVENT_QUARANTINE"
    return "SEMANTICS_HARDENED"


def model_fit_authorized(disposition_value: str) -> bool:
    return disposition_value in {
        "SEMANTICS_HARDENED",
        "SEMANTICS_HARDENED_WITH_RARE_EVENT_QUARANTINE",
    }


if __name__ == "__main__":
    print(f"NFL QB semantic hardening {VERSION} · {LINEAGE}")

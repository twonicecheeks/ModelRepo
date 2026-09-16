"""NFL QB State 0.1.9 — official weekly target authority helpers.

Development-only. Official-like nflverse weekly player stats are the canonical
settlement/target layer; play-by-play remains the mechanism layer. This module
contains only deterministic joins, comparisons and authorization guards.
"""
from __future__ import annotations

from math import isnan
from statistics import fmean
from typing import Any, Iterable

VERSION = "0.1.9"
LINEAGE = "nfl-qb-official-target-authority-v0.1.9-m31-m36-m41-m48-m87-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
SANITY_EXACT_MATCH_FLOOR_PCT = 90.0

REQUIRED_OFFICIAL_FIELDS = (
    "attempts", "completions", "passing_yards", "sacks_suffered",
)
COMPARISONS = (
    ("attempts", "settlement_pass_attempts", "attempts"),
    ("completions", "settlement_completions", "completions"),
    ("passing_yards", "passing_yards", "passing_yards"),
    ("sacks", "structural_sacks", "sacks_suffered"),
)


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if isnan(x) else x


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    vals = tuple(sorted({int(s) for s in seasons}))
    if not vals:
        raise ValueError("at least one development season is required")
    bad = [s for s in vals if s >= SEALED_HOLDOUT_SEASON]
    if bad:
        raise ValueError("0.1.9 is development-only; sealed 2025+ forbidden: " + ",".join(map(str, bad)))
    return vals


def target_key(row: dict[str, Any]) -> tuple[str, str]:
    return clean(row.get("game_id")), clean(row.get("observed_start_qb_gsis_id"))


def official_key(row: dict[str, Any]) -> tuple[str, str]:
    return clean(row.get("game_id")), clean(row.get("player_id"))


def attach_official_target(target: dict[str, Any], official: dict[str, Any]) -> dict[str, Any]:
    out = dict(target)
    out.update({
        "official_target_source": "NFLVERSE_PLAYER_STATS_WEEKLY",
        "official_player_id": clean(official.get("player_id")),
        "official_team": clean(official.get("team")).upper(),
        "official_attempts": num(official.get("attempts")),
        "official_completions": num(official.get("completions")),
        "official_passing_yards": num(official.get("passing_yards")),
        "official_sacks_suffered": num(official.get("sacks_suffered")),
        "official_carries": num(official.get("carries")),
        "official_rushing_yards": num(official.get("rushing_yards")),
        "official_passing_tds": num(official.get("passing_tds")),
        "official_interceptions": num(official.get("interceptions")),
        "official_passing_air_yards": num(official.get("passing_air_yards")),
        "official_passing_yards_after_catch": num(official.get("passing_yards_after_catch")),
        "official_passing_epa": num(official.get("passing_epa")),
        "official_passing_cpoe": num(official.get("passing_cpoe")),
        "official_source_sha256": clean(official.get("source_sha256")),
    })
    for name, pbp_field, official_field in COMPARISONS:
        p = num(target.get(pbp_field))
        o = num(official.get(official_field))
        out[f"pbp_vs_official_{name}_delta"] = None if p is None or o is None else p - o
    return out


def comparison_summary(rows: Iterable[dict[str, Any]], pbp_field: str, official_field: str) -> dict[str, Any]:
    deltas: list[float] = []
    n = exact = 0
    for row in rows:
        a = num(row.get(pbp_field))
        b = num(row.get(official_field))
        if a is None or b is None:
            continue
        d = a - b
        deltas.append(d)
        n += 1
        if abs(d) < 1e-9:
            exact += 1
    absd = [abs(x) for x in deltas]
    return {
        "n": n,
        "exact": exact,
        "exactPct": None if not n else 100.0 * exact / n,
        "meanDelta": None if not deltas else fmean(deltas),
        "meanAbsoluteDelta": None if not absd else fmean(absd),
        "maxAbsoluteDelta": None if not absd else max(absd),
        "nonzero": n - exact,
    }


def authorization(
    *,
    target_rows: int,
    joined_rows: int,
    duplicate_official_keys: int,
    missing_required_values: int,
    team_mismatches: int,
    comparisons: dict[str, dict[str, Any]],
) -> tuple[bool, str]:
    """Authorize only a development challenger, never holdout/prospective use.

    The 90% exact-match floor is deliberately a broad catastrophic schema/join guard,
    not a model-selection threshold. Official weekly values remain authoritative even
    when individual PBP mechanism values differ.
    """
    if target_rows <= 0 or joined_rows != target_rows:
        return False, "OFFICIAL_TARGET_JOIN_INCOMPLETE"
    if duplicate_official_keys:
        return False, "OFFICIAL_TARGET_DUPLICATE_KEYS"
    if missing_required_values:
        return False, "OFFICIAL_TARGET_REQUIRED_VALUES_MISSING"
    if team_mismatches:
        return False, "OFFICIAL_TARGET_TEAM_IDENTITY_MISMATCH"
    for name, summary in comparisons.items():
        pct = summary.get("exactPct")
        if pct is None or float(pct) < SANITY_EXACT_MATCH_FLOOR_PCT:
            return False, f"OFFICIAL_TARGET_SANITY_FAIL_{name.upper()}"
    return True, "OFFICIAL_TARGET_LAYER_READY_FOR_QB_MODELING"


if __name__ == "__main__":
    print(f"NFL QB official target authority {VERSION} · {LINEAGE}")

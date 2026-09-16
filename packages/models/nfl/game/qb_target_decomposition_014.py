"""NFL QB State 0.1.4 — observed-starter target/decomposition helpers.

This module builds coefficient-free historical QB target rows from development PBP.
It deliberately separates two jobs:

1. Historical model labels use the observed first attributed QB in the game. That is
   a retrospective target identity, not a pregame feature.
2. Prospective/pre-game starter resolution remains the responsibility of the 0.1.3
   resolver and can be quarantined independently.

This separation prevents 3%-level resolver identity noise from contaminating QB skill
estimation while preserving honest end-to-end resolver evaluation.
"""
from __future__ import annotations

from collections import Counter
from math import isnan
from statistics import fmean
from typing import Any, Iterable

VERSION = "0.1.4"
LINEAGE = "nfl-qb-state-target-decomposition-v0.1.4-m31-m36-m39-m41-m48-m50-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

REQUIRED_PBP_FIELDS = (
    "game_id", "season", "week", "posteam", "qb_dropback", "pass_attempt",
    "complete_pass", "sack", "qb_scramble", "rush_attempt", "passer_player_id",
    "rusher_player_id", "passing_yards", "air_yards", "yards_after_catch",
    "yards_gained", "play_type",
)
OPTIONAL_PBP_FIELDS = (
    "play_id", "no_play", "qb_kneel", "passer_player_name", "rusher_player_name",
    "receiver_player_id", "receiver_player_name", "interception", "qb_epa", "cpoe",
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


def flag(v: Any) -> bool:
    return num(v) == 1.0


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    vals = tuple(sorted({int(s) for s in seasons}))
    if not vals:
        raise ValueError("at least one development season is required")
    bad = [s for s in vals if s >= SEALED_HOLDOUT_SEASON]
    if bad:
        raise ValueError(
            "QB State 0.1.4 is development-only; sealed 2025 / prospective 2026+ forbidden: "
            + ",".join(map(str, bad))
        )
    return vals


def is_no_play(row: dict[str, Any]) -> bool:
    if flag(row.get("no_play")):
        return True
    return clean(row.get("play_type")).lower() == "no_play"


def is_kneel(row: dict[str, Any]) -> bool:
    if flag(row.get("qb_kneel")):
        return True
    return clean(row.get("play_type")).lower() == "qb_kneel"


def eligible_dropback(row: dict[str, Any]) -> bool:
    return flag(row.get("qb_dropback")) and not is_no_play(row) and not is_kneel(row)


def eligible_rush(row: dict[str, Any]) -> bool:
    return flag(row.get("rush_attempt")) and not is_no_play(row) and not is_kneel(row)


def qb_identity_on_dropback(row: dict[str, Any]) -> str:
    """Prefer passer identity, then rusher identity for a scramble-only schema gap."""
    pid = clean(row.get("passer_player_id"))
    if pid:
        return pid
    if flag(row.get("qb_scramble")):
        return clean(row.get("rusher_player_id"))
    return ""


def observed_qb_labels(rows: Iterable[dict[str, Any]]) -> tuple[str, str, int]:
    vals: list[tuple[float, str]] = []
    for i, row in enumerate(rows):
        if not eligible_dropback(row):
            continue
        qid = qb_identity_on_dropback(row)
        if not qid:
            continue
        order = num(row.get("play_id"))
        vals.append((float(i) if order is None else order, qid))
    if not vals:
        return "", "", 0
    vals.sort(key=lambda x: (x[0], x[1]))
    counts = Counter(q for _, q in vals)
    primary = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return vals[0][1], primary, len(vals)


def aggregate_observed_starter_team_game(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate one offense/team-game around the observed first attributed QB.

    The first attributed eligible dropback QB is a historical label only. A future
    model must receive QB identity from a pregame resolver/verified starter source.
    """
    data = [dict(r) for r in rows]
    if not data:
        return None
    first_qb, primary_qb, attributed_team_dropbacks = observed_qb_labels(data)
    if not first_qb:
        return None

    meta = data[0]
    game_id = clean(meta.get("game_id"))
    team = clean(meta.get("posteam")).upper()
    season = int(float(meta["season"]))
    week = int(float(meta["week"]))

    team_offensive_plays = 0
    team_dropbacks = 0
    team_designed_runs = 0
    starter_dropbacks = 0
    attempts = 0
    completions = 0
    sacks = 0
    scrambles = 0
    interceptions = 0
    passing_yards = 0.0
    passing_yard_rows = 0
    completed_air_yards = 0.0
    completion_yac = 0.0
    decomposable_completions = 0
    completion_yards_decomp_residual = 0.0
    designed_qb_rushes = 0
    qb_rush_yards = 0.0
    qb_rushes = 0
    qb_epas: list[float] = []
    cpoes: list[float] = []

    for row in data:
        db = eligible_dropback(row)
        rush = eligible_rush(row)
        scramble = db and flag(row.get("qb_scramble"))
        if db or rush:
            team_offensive_plays += 1
        if db:
            team_dropbacks += 1
        if rush and not flag(row.get("qb_scramble")):
            team_designed_runs += 1

        qid = qb_identity_on_dropback(row)
        is_starter_db = db and qid == first_qb
        if is_starter_db:
            starter_dropbacks += 1
            is_attempt = flag(row.get("pass_attempt"))
            is_complete = is_attempt and flag(row.get("complete_pass"))
            if is_attempt:
                attempts += 1
                py = num(row.get("passing_yards"))
                if py is not None:
                    passing_yards += py
                    passing_yard_rows += 1
                cp = num(row.get("cpoe"))
                if cp is not None:
                    cpoes.append(cp)
            if is_complete:
                completions += 1
                ay = num(row.get("air_yards"))
                yac = num(row.get("yards_after_catch"))
                if ay is not None and yac is not None:
                    completed_air_yards += ay
                    completion_yac += yac
                    decomposable_completions += 1
                    py = num(row.get("passing_yards"))
                    if py is not None:
                        completion_yards_decomp_residual += py - (ay + yac)
            if flag(row.get("sack")):
                sacks += 1
            if scramble:
                scrambles += 1
            if flag(row.get("interception")):
                interceptions += 1
            qe = num(row.get("qb_epa"))
            if qe is not None:
                qb_epas.append(qe)

        rusher = clean(row.get("rusher_player_id"))
        if rush and rusher == first_qb:
            qb_rushes += 1
            y = num(row.get("yards_gained"))
            if y is not None:
                qb_rush_yards += y
            if not flag(row.get("qb_scramble")):
                designed_qb_rushes += 1

    components = attempts + sacks + scrambles
    return {
        "game_id": game_id,
        "season": season,
        "week": week,
        "team": team,
        "observed_start_qb_gsis_id": first_qb,
        "observed_primary_qb_gsis_id": primary_qb,
        "start_equals_primary": 1 if first_qb == primary_qb else 0,
        "team_offensive_plays": team_offensive_plays,
        "team_dropbacks": team_dropbacks,
        "team_designed_runs": team_designed_runs,
        "team_attributed_dropbacks": attributed_team_dropbacks,
        "starter_dropbacks": starter_dropbacks,
        "starter_dropback_share": (starter_dropbacks / team_dropbacks) if team_dropbacks else None,
        "pass_attempts": attempts,
        "completions": completions,
        "sacks": sacks,
        "scrambles": scrambles,
        "interceptions": interceptions,
        "dropback_components_total": components,
        "dropback_component_residual": starter_dropbacks - components,
        "passing_yards": passing_yards,
        "passing_yard_rows": passing_yard_rows,
        "completed_air_yards": completed_air_yards,
        "completion_yac": completion_yac,
        "decomposable_completions": decomposable_completions,
        "completion_yards_decomp_residual": completion_yards_decomp_residual,
        "designed_qb_rush_attempts": designed_qb_rushes,
        "qb_rush_attempts": qb_rushes,
        "qb_rush_yards": qb_rush_yards,
        "mean_qb_epa": fmean(qb_epas) if qb_epas else None,
        "mean_cpoe": fmean(cpoes) if cpoes else None,
    }


def quantiles(values: Iterable[float | int | None], probs=(0.1, 0.25, 0.5, 0.75, 0.9)) -> dict[str, float | None]:
    vals = sorted(float(x) for x in values if x is not None)
    if not vals:
        return {str(p): None for p in probs}
    out: dict[str, float] = {}
    n = len(vals)
    for p in probs:
        idx = int(round((n - 1) * float(p)))
        out[str(p)] = vals[max(0, min(n - 1, idx))]
    return out


if __name__ == "__main__":
    print(f"NFL QB target decomposition {VERSION} · {LINEAGE}")

"""NFL QB State 0.1.5 — nflverse-semantic-correct QB target decomposition.

0.1.4 intentionally exposed a schema-semantics mismatch: nflfastR/nflverse
`pass_attempt` includes sacks, so `dropbacks = pass_attempts + sacks + scrambles`
double-counts sacks. This module fixes the decomposition before any QB model fit.

Two target families are kept separate:
- STRUCTURAL: normal offensive opportunity states for prediction. Excludes no-plays,
  kneels, spikes, and two-point tries.
- SETTLEMENT: box-score style player stats. Pass attempts exclude sacks/two-point
  tries but include spikes; QB rushing includes kneels when the source charges them
  as rushing attempts.

Historical starter identity remains a retrospective label only. Pregame/prospective
identity must come from the resolver or a verified starter source.
"""
from __future__ import annotations

from collections import Counter
from math import isnan
from statistics import fmean
from typing import Any, Iterable

VERSION = "0.1.5"
LINEAGE = "nfl-qb-state-target-semantics-v0.1.5-m31-m36-m41-m48-m87-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

REQUIRED_PBP_FIELDS = (
    "game_id", "season", "week", "posteam", "qb_dropback", "pass_attempt",
    "complete_pass", "sack", "qb_scramble", "qb_spike", "qb_kneel",
    "two_point_attempt", "rush_attempt", "passer_player_id", "rusher_player_id",
    "passing_yards", "rushing_yards", "air_yards", "yards_after_catch",
    "yards_gained", "play_type",
)
OPTIONAL_PBP_FIELDS = (
    "play_id", "no_play", "passer_player_name", "rusher_player_name",
    "receiver_player_id", "receiver_player_name", "interception", "qb_epa", "cpoe",
    "aborted_play",
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
            "QB State 0.1.5 is development-only; sealed 2025 / prospective 2026+ forbidden: "
            + ",".join(map(str, bad))
        )
    return vals


def is_no_play(row: dict[str, Any]) -> bool:
    if flag(row.get("no_play")):
        return True
    return clean(row.get("play_type")).lower() == "no_play"


def is_two_point(row: dict[str, Any]) -> bool:
    return flag(row.get("two_point_attempt"))


def structural_dropback(row: dict[str, Any]) -> bool:
    return (
        flag(row.get("qb_dropback"))
        and not is_no_play(row)
        and not flag(row.get("qb_kneel"))
        and not flag(row.get("qb_spike"))
        and not is_two_point(row)
    )


def structural_rush(row: dict[str, Any]) -> bool:
    return (
        flag(row.get("rush_attempt"))
        and not is_no_play(row)
        and not flag(row.get("qb_kneel"))
        and not is_two_point(row)
    )


def qb_identity_on_dropback(row: dict[str, Any]) -> str:
    pid = clean(row.get("passer_player_id"))
    if pid:
        return pid
    if flag(row.get("qb_scramble")):
        return clean(row.get("rusher_player_id"))
    return ""


def dropback_outcome(row: dict[str, Any]) -> str:
    """Mutually-exclusive structural dropback outcome using nflverse semantics."""
    if not structural_dropback(row):
        return "NOT_STRUCTURAL_DROPBACK"
    sack = flag(row.get("sack"))
    scramble = flag(row.get("qb_scramble"))
    if sack and scramble:
        return "CONFLICT"
    if sack:
        return "SACK"
    if scramble:
        return "SCRAMBLE"
    if flag(row.get("pass_attempt")):
        return "THROW"
    return "OTHER"


def settlement_pass_attempt(row: dict[str, Any]) -> bool:
    """Box-score pass attempt proxy: pass_attempt includes sacks in nflverse.

    Therefore a settlement attempt is pass_attempt minus sacks, excluding no-plays,
    scrambles and two-point tries. Spikes are intentionally retained.
    """
    return (
        flag(row.get("pass_attempt"))
        and not flag(row.get("sack"))
        and not flag(row.get("qb_scramble"))
        and not is_no_play(row)
        and not is_two_point(row)
    )


def settlement_qb_rush(row: dict[str, Any], qb_id: str) -> bool:
    return (
        flag(row.get("rush_attempt"))
        and not is_no_play(row)
        and not is_two_point(row)
        and clean(row.get("rusher_player_id")) == qb_id
    )


def observed_qb_labels(rows: Iterable[dict[str, Any]]) -> tuple[str, str, int]:
    vals: list[tuple[float, str]] = []
    for i, row in enumerate(rows):
        if not structural_dropback(row):
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


def aggregate_team_game(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
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

    team_structural_plays = team_structural_dropbacks = team_designed_runs = 0
    starter_dropbacks = throws = sacks = scrambles = db_other = db_conflict = 0
    raw_pass_indicator_on_db = raw_sack_with_pass_indicator = 0
    settlement_attempts = settlement_completions = spike_attempts = 0
    passing_yards = 0.0
    completed_air_yards = completion_yac = 0.0
    decomposable_completions = exact_decomp_completions = 0
    completion_yards_decomp_residual = 0.0
    structural_qb_rush_attempts = 0
    structural_qb_rush_yards = 0.0
    designed_qb_rush_attempts = 0
    settlement_qb_rush_attempts = 0
    settlement_qb_rush_yards = 0.0
    settlement_kneels = 0
    two_point_pass_plays_excluded = 0
    interceptions = 0
    qb_epas: list[float] = []
    cpoes: list[float] = []

    for row in data:
        db = structural_dropback(row)
        rush = structural_rush(row)
        if db or rush:
            team_structural_plays += 1
        if db:
            team_structural_dropbacks += 1
        if rush and not flag(row.get("qb_scramble")):
            team_designed_runs += 1

        qid = qb_identity_on_dropback(row)
        if db and qid == first_qb:
            starter_dropbacks += 1
            outcome = dropback_outcome(row)
            if outcome == "THROW": throws += 1
            elif outcome == "SACK": sacks += 1
            elif outcome == "SCRAMBLE": scrambles += 1
            elif outcome == "OTHER": db_other += 1
            elif outcome == "CONFLICT": db_conflict += 1
            if flag(row.get("pass_attempt")):
                raw_pass_indicator_on_db += 1
            if flag(row.get("sack")) and flag(row.get("pass_attempt")):
                raw_sack_with_pass_indicator += 1
            qe = num(row.get("qb_epa"))
            if qe is not None:
                qb_epas.append(qe)
            cp = num(row.get("cpoe"))
            if outcome == "THROW" and cp is not None:
                cpoes.append(cp)

        passer = clean(row.get("passer_player_id"))
        if is_two_point(row) and passer == first_qb and flag(row.get("pass_attempt")):
            two_point_pass_plays_excluded += 1

        if settlement_pass_attempt(row) and passer == first_qb:
            settlement_attempts += 1
            if flag(row.get("qb_spike")):
                spike_attempts += 1
            py = num(row.get("passing_yards"))
            if py is not None:
                passing_yards += py
            if flag(row.get("complete_pass")):
                settlement_completions += 1
                ay = num(row.get("air_yards"))
                yac = num(row.get("yards_after_catch"))
                if ay is not None and yac is not None:
                    decomposable_completions += 1
                    completed_air_yards += ay
                    completion_yac += yac
                    if py is not None:
                        resid = py - (ay + yac)
                        completion_yards_decomp_residual += resid
                        if abs(resid) < 1e-9:
                            exact_decomp_completions += 1
            if flag(row.get("interception")):
                interceptions += 1

        rusher = clean(row.get("rusher_player_id"))
        if rush and rusher == first_qb:
            structural_qb_rush_attempts += 1
            ry = num(row.get("rushing_yards"))
            if ry is None:
                ry = num(row.get("yards_gained"))
            if ry is not None:
                structural_qb_rush_yards += ry
            if not flag(row.get("qb_scramble")):
                designed_qb_rush_attempts += 1

        if settlement_qb_rush(row, first_qb):
            settlement_qb_rush_attempts += 1
            if flag(row.get("qb_kneel")):
                settlement_kneels += 1
            ry = num(row.get("rushing_yards"))
            if ry is None:
                ry = num(row.get("yards_gained"))
            if ry is not None:
                settlement_qb_rush_yards += ry

    classified = throws + sacks + scrambles
    return {
        "game_id": game_id,
        "season": season,
        "week": week,
        "team": team,
        "observed_start_qb_gsis_id": first_qb,
        "observed_primary_qb_gsis_id": primary_qb,
        "start_equals_primary": 1 if first_qb == primary_qb else 0,
        "team_structural_plays": team_structural_plays,
        "team_structural_dropbacks": team_structural_dropbacks,
        "team_designed_runs": team_designed_runs,
        "team_attributed_dropbacks": attributed_team_dropbacks,
        "starter_structural_dropbacks": starter_dropbacks,
        "starter_dropback_share": (starter_dropbacks / team_structural_dropbacks) if team_structural_dropbacks else None,
        "structural_throw_attempts": throws,
        "structural_sacks": sacks,
        "structural_scrambles": scrambles,
        "structural_dropback_other": db_other,
        "structural_dropback_conflict": db_conflict,
        "structural_classified_total": classified,
        "structural_dropback_residual": starter_dropbacks - classified,
        "raw_pass_attempt_indicator_on_structural_db": raw_pass_indicator_on_db,
        "raw_sacks_with_pass_attempt_indicator": raw_sack_with_pass_indicator,
        "settlement_pass_attempts": settlement_attempts,
        "settlement_completions": settlement_completions,
        "settlement_spike_attempts": spike_attempts,
        "two_point_pass_plays_excluded": two_point_pass_plays_excluded,
        "passing_yards": passing_yards,
        "interceptions": interceptions,
        "completed_air_yards": completed_air_yards,
        "completion_yac": completion_yac,
        "decomposable_completions": decomposable_completions,
        "exact_decomp_completions": exact_decomp_completions,
        "completion_yards_decomp_residual": completion_yards_decomp_residual,
        "structural_qb_rush_attempts": structural_qb_rush_attempts,
        "structural_qb_rush_yards": structural_qb_rush_yards,
        "designed_qb_rush_attempts": designed_qb_rush_attempts,
        "settlement_qb_rush_attempts": settlement_qb_rush_attempts,
        "settlement_qb_rush_yards": settlement_qb_rush_yards,
        "settlement_kneels": settlement_kneels,
        "mean_qb_epa": fmean(qb_epas) if qb_epas else None,
        "mean_cpoe": fmean(cpoes) if cpoes else None,
    }


def quantiles(values: Iterable[float | int | None], probs=(0.1, 0.25, 0.5, 0.75, 0.9)) -> dict[str, float | None]:
    vals = sorted(float(x) for x in values if x is not None)
    if not vals:
        return {str(p): None for p in probs}
    n = len(vals)
    out: dict[str, float] = {}
    for p in probs:
        idx = int(round((n - 1) * float(p)))
        out[str(p)] = vals[max(0, min(n - 1, idx))]
    return out


if __name__ == "__main__":
    print(f"NFL QB target semantics {VERSION} · {LINEAGE}")

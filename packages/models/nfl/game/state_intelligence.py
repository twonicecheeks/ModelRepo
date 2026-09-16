"""NFL State Intelligence 0.1.0.

Deterministic, coefficient-free snap/drive context primitives derived from the
DEN@KC M01-M88 development ledger. This module is research infrastructure only:
it does not mutate frozen OMEGA forecasts, fit a model, or consume sportsbook
data.

The primary contract is to separate pre-snap state, called-play intent, realized
outcome, and data-hygiene labels so downstream game/QB/prop challengers can use
the same causal representation.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

VERSION = "0.1.0"
LINEAGE = "nfl-state-intelligence-v0.1.0-den-kc-m01-m88-2026-09-16"
CALIBRATION_STATUS = "UNFIT_RESEARCH_INFRASTRUCTURE"
FROZEN_OMEGA_MUTATION_ALLOWED = False

COMPETITIVE_STATES = (
    "COMPETITIVE",
    "CLOSEOUT_CANDIDATE",
    "COMEBACK_FORCED_CANDIDATE",
    "VICTORY_FORMATION",
    "TERMINAL",
)

PLAY_INTENTS = (
    "NO_PLAY",
    "VICTORY_FORMATION",
    "DROPBACK_SACK",
    "DROPBACK_SCRAMBLE",
    "DESIGNED_PASS",
    "DESIGNED_RUN",
    "SPECIAL_TEAMS",
    "OTHER",
)


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _flag(row: dict[str, Any], key: str) -> bool:
    return _num(row.get(key)) == 1.0


def _text(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip().lower()


def classify_play_intent(row: dict[str, Any]) -> str:
    """Classify called-play intent without confusing scrambles/sacks with runs.

    M01/M02/M39/M86: a scramble or sack originates from a dropback. Kneels and
    nullified plays are explicitly separated from ordinary offensive tendency.
    """
    play_type = _text(row, "play_type")
    if _flag(row, "no_play") or play_type == "no_play":
        return "NO_PLAY"
    if _flag(row, "qb_kneel") or play_type == "qb_kneel":
        return "VICTORY_FORMATION"

    if _flag(row, "punt") or _flag(row, "field_goal_attempt") or _flag(row, "kickoff_attempt"):
        return "SPECIAL_TEAMS"
    if play_type in {"punt", "field_goal", "kickoff", "extra_point"}:
        return "SPECIAL_TEAMS"

    dropback = _flag(row, "qb_dropback")
    sack = _flag(row, "sack")
    scramble = _flag(row, "qb_scramble") or play_type == "qb_scramble"
    rush = _flag(row, "rush")

    if dropback or sack or scramble:
        if sack:
            return "DROPBACK_SACK"
        if scramble:
            return "DROPBACK_SCRAMBLE"
        return "DESIGNED_PASS"
    if rush or play_type == "run":
        return "DESIGNED_RUN"
    if play_type == "pass":
        return "DESIGNED_PASS"
    return "OTHER"


def down_distance_bucket(row: dict[str, Any]) -> str | None:
    """Return a pre-snap distance bucket, preserving down as part of the label."""
    down = _num(row.get("down"))
    distance = _num(row.get("ydstogo"))
    if down is None or distance is None:
        return None
    d = int(down)
    if distance <= 3:
        band = "SHORT"
    elif distance <= 6:
        band = "MEDIUM"
    elif distance <= 10:
        band = "LONG"
    else:
        band = "VERY_LONG"
    return f"D{d}_{band}"


def third_down_distance_bucket(row: dict[str, Any]) -> str | None:
    """M19: distinguish third-down conversion environments explicitly."""
    down = _num(row.get("down"))
    distance = _num(row.get("ydstogo"))
    if down != 3 or distance is None:
        return None
    if distance <= 2:
        return "THIRD_SHORT"
    if distance <= 6:
        return "THIRD_MEDIUM"
    if distance <= 10:
        return "THIRD_LONG"
    return "THIRD_VERY_LONG"


def field_position_bucket(row: dict[str, Any]) -> str | None:
    """M29/M64/M69/M76: classify field-position risk environments."""
    y100 = _num(row.get("yardline_100"))
    if y100 is None:
        return None
    if _flag(row, "goal_to_go"):
        return "GOAL_TO_GO"
    if y100 <= 20:
        return "RED_ZONE"
    if y100 <= 40:
        return "PLUS_TERRITORY"
    if y100 < 60:
        return "MIDFIELD"
    if y100 < 90:
        return "OWN_TERRITORY"
    return "BACKED_UP"


def pressure_opportunity_bucket(row: dict[str, Any]) -> str | None:
    """Structural pass-rush exposure proxy from *pre-snap* state only.

    This is not observed pressure and is intentionally coefficient-free.
    M04/M05/M06/M07/M19 motivate later historical calibration.
    """
    down = _num(row.get("down"))
    distance = _num(row.get("ydstogo"))
    if down is None or distance is None:
        return None
    if down in (3, 4) and distance >= 7:
        return "HIGH_STRUCTURAL_EXPOSURE"
    if (down == 2 and distance >= 8) or (down in (3, 4) and distance >= 4):
        return "ELEVATED_STRUCTURAL_EXPOSURE"
    return "BASE_STRUCTURAL_EXPOSURE"


def first_down_source(row: dict[str, Any], play_intent: str | None = None) -> str | None:
    """M37: identify how a first down was created."""
    if _flag(row, "first_down_penalty"):
        return "PENALTY"
    if _flag(row, "first_down_rush"):
        return "RUSH"
    if _flag(row, "first_down_pass"):
        return "PASS"
    if not _flag(row, "first_down"):
        return None
    intent = play_intent or classify_play_intent(row)
    if intent == "DROPBACK_SCRAMBLE":
        return "SCRAMBLE"
    if intent == "DESIGNED_RUN":
        return "RUSH"
    if intent in {"DESIGNED_PASS", "DROPBACK_SACK"}:
        return "PASS"
    return "OTHER"


def disruption_types(row: dict[str, Any], play_intent: str | None = None) -> tuple[str, ...]:
    """M27/M61-M63/M72-M74: explicit nonlinear disruption labels."""
    intent = play_intent or classify_play_intent(row)
    out: list[str] = []
    if _flag(row, "penalty"):
        out.append("PENALTY")
    if intent == "DROPBACK_SACK":
        out.append("SACK")
    if _flag(row, "tackled_for_loss"):
        out.append("TFL")
    if _flag(row, "interception"):
        out.append("INTERCEPTION")
    if _flag(row, "fumble"):
        out.append("FUMBLE")
    if _flag(row, "fumble_lost"):
        out.append("FUMBLE_LOST")
    if _flag(row, "aborted_play") or "aborted" in _text(row, "desc"):
        out.append("ABORTED_PLAY")
    if _flag(row, "qb_hit"):
        out.append("QB_HIT")
    return tuple(out)


def turnover_type(row: dict[str, Any]) -> str | None:
    if _flag(row, "interception"):
        return "INTERCEPTION"
    if _flag(row, "fumble_lost"):
        return "FUMBLE_LOST"
    return None


def competitive_state(row: dict[str, Any], play_intent: str | None = None) -> str:
    """M77-M80/M84-M88: isolate terminal/clock-management states.

    CLOSEOUT/COMEBACK labels are conservative *candidates* based on supplied WP.
    They are research hygiene labels, not model coefficients or asserted optimal
    thresholds.
    """
    intent = play_intent or classify_play_intent(row)
    if intent == "VICTORY_FORMATION":
        return "VICTORY_FORMATION"

    if _flag(row, "terminal_state"):
        return "TERMINAL"

    qtr = _num(row.get("qtr"))
    wp = _num(row.get("wp"))
    if qtr is not None and qtr >= 4 and wp is not None:
        if wp >= 0.97:
            return "CLOSEOUT_CANDIDATE"
        if wp <= 0.03:
            return "COMEBACK_FORCED_CANDIDATE"
    return "COMPETITIVE"


def functional_completion(row: dict[str, Any]) -> str | None:
    """M34: classify completion quality relative to the line to gain.

    Requires complete_pass plus yards_gained and ydstogo. It does not attempt
    receiver/QB attribution.
    """
    if not _flag(row, "complete_pass"):
        return None
    distance = _num(row.get("ydstogo"))
    gained = _num(row.get("yards_gained"))
    if distance is None or gained is None:
        return "COMPLETION_UNGRADED"
    if gained >= distance:
        return "FUNCTIONAL_CONVERSION"
    return "SHORT_OF_STICKS"


def snap_state_features(row: dict[str, Any]) -> dict[str, Any]:
    """Build coefficient-free state/intent/outcome labels for one snap."""
    intent = classify_play_intent(row)
    comp_state = competitive_state(row, intent)
    disruptions = disruption_types(row, intent)
    turnover = turnover_type(row)
    eligible = (
        intent not in {"NO_PLAY", "VICTORY_FORMATION", "SPECIAL_TEAMS", "OTHER"}
        and comp_state not in {"TERMINAL", "VICTORY_FORMATION"}
    )
    return {
        "play_intent": intent,
        "down_distance_bucket": down_distance_bucket(row),
        "third_down_distance_bucket": third_down_distance_bucket(row),
        "field_position_bucket": field_position_bucket(row),
        "pressure_opportunity_bucket": pressure_opportunity_bucket(row),
        "first_down_source": first_down_source(row, intent),
        "disruption_types": disruptions,
        "disruption_count": len(disruptions),
        "turnover_type": turnover,
        "competitive_state": comp_state,
        "functional_completion": functional_completion(row),
        "football_tendency_eligible": eligible,
        "official_stat_qb_kneel": intent == "VICTORY_FORMATION",
        "dropback_origin": intent in {"DESIGNED_PASS", "DROPBACK_SCRAMBLE", "DROPBACK_SACK"},
        "designed_run_origin": intent == "DESIGNED_RUN",
    }


def annotate_game_states(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate one game's snaps and derive chronology-sensitive labels.

    M68/M71/M81/M83 require chronology. Sorting uses play_id when available;
    otherwise input order is retained. Replay-provisional rows can be flagged
    with replay_or_challenge_result_pending and will not be silently finalized.
    """
    materialized = [dict(r) for r in rows]
    if not materialized:
        return []

    game_ids = {str(r.get("game_id")) for r in materialized if r.get("game_id") not in (None, "")}
    if len(game_ids) > 1:
        raise ValueError("annotate_game_states expects rows from one game")

    indexed = list(enumerate(materialized))
    if all(_num(r.get("play_id")) is not None for _, r in indexed):
        indexed.sort(key=lambda item: (_num(item[1].get("play_id")) or 0, item[0]))

    prior_turnover: dict[str, Any] | None = None
    prior_posteam: str | None = None
    prior_drive: str | None = None
    out: list[dict[str, Any]] = []

    for input_index, row in indexed:
        feat = snap_state_features(row)
        posteam = str(row.get("posteam") or "").upper() or None
        drive = str(row.get("drive") or "") or None

        possession_changed = prior_posteam is not None and posteam is not None and posteam != prior_posteam
        drive_changed = prior_drive is not None and drive is not None and drive != prior_drive
        sudden_change = bool(prior_turnover and possession_changed)

        feat.update({
            "input_index": input_index,
            "sudden_change_offense": sudden_change,
            "inherited_turnover_type": prior_turnover.get("turnover_type") if sudden_change else None,
            "drive_changed_from_prior_snap": drive_changed,
            "ruling_state": (
                "PROVISIONAL"
                if _flag(row, "replay_or_challenge_result_pending")
                else "FINAL_OR_UNMARKED"
            ),
        })

        combined = dict(row)
        combined["state_intelligence"] = feat
        out.append(combined)

        current_turnover = feat["turnover_type"]
        prior_turnover = ({"turnover_type": current_turnover, "posteam": posteam} if current_turnover else None)
        prior_posteam = posteam
        prior_drive = drive

    return out


def aggregate_state_profile(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate annotated or raw snaps into a descriptive diagnostic profile."""
    counts: dict[str, defaultdict[str, int]] = {
        "play_intent": defaultdict(int),
        "competitive_state": defaultdict(int),
        "pressure_opportunity_bucket": defaultdict(int),
        "field_position_bucket": defaultdict(int),
        "first_down_source": defaultdict(int),
    }
    eligible = 0
    disruptions = 0
    turnovers = 0
    total = 0

    for raw in rows:
        total += 1
        feat = raw.get("state_intelligence") if isinstance(raw.get("state_intelligence"), dict) else snap_state_features(raw)
        if feat.get("football_tendency_eligible"):
            eligible += 1
        disruptions += int(feat.get("disruption_count") or 0)
        turnovers += 1 if feat.get("turnover_type") else 0
        for key in counts:
            val = feat.get(key)
            if val:
                counts[key][str(val)] += 1

    return {
        "version": VERSION,
        "lineage": LINEAGE,
        "total_snaps": total,
        "football_tendency_eligible_snaps": eligible,
        "disruption_events": disruptions,
        "turnovers": turnovers,
        **{k: dict(sorted(v.items())) for k, v in counts.items()},
    }


if __name__ == "__main__":
    print(f"NFL State Intelligence {VERSION} · {LINEAGE} · {CALIBRATION_STATUS}")

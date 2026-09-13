"""OMEGA tackle-event primitives.

This module does not fit a betting model and does not read market prices.  It turns
nflverse play-by-play tackle-credit columns into an explicit event ledger while
preserving the distinctions the NFL source exposes:

* SOLO               -> solo tackle credit
* PRIMARY_WITH_ASSIST -> tackle made while another defender is credited with assist
* ASSIST              -> assist to another player's tackle

No sportsbook settlement convention is assumed.  Downstream market adapters must
explicitly declare whether they settle solo, tackles-with-assist, assists, special
teams, stat corrections, etc.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

CREDIT_SLOTS = []
for i in (1, 2):
    CREDIT_SLOTS.append((
        "SOLO", i,
        f"solo_tackle_{i}_player_id",
        f"solo_tackle_{i}_player_name",
        f"solo_tackle_{i}_team",
    ))
for i in (1, 2):
    CREDIT_SLOTS.append((
        "PRIMARY_WITH_ASSIST", i,
        f"tackle_with_assist_{i}_player_id",
        f"tackle_with_assist_{i}_player_name",
        f"tackle_with_assist_{i}_team",
    ))
for i in (1, 2, 3, 4):
    CREDIT_SLOTS.append((
        "ASSIST", i,
        f"assist_tackle_{i}_player_id",
        f"assist_tackle_{i}_player_name",
        f"assist_tackle_{i}_team",
    ))

TACKLE_ID_COLUMNS = tuple(x[2] for x in CREDIT_SLOTS)
TACKLE_NAME_COLUMNS = tuple(x[3] for x in CREDIT_SLOTS)
TACKLE_TEAM_COLUMNS = tuple(x[4] for x in CREDIT_SLOTS)


def _clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _flag(v: Any) -> bool:
    x = _num(v)
    if x is not None:
        return bool(int(x))
    return _clean(v).lower() in {"true", "yes", "y"}


def validate_tackle_schema(columns: Iterable[str]) -> dict[str, Any]:
    cols = set(columns)
    present = [c for c in TACKLE_ID_COLUMNS if c in cols]
    if not present:
        raise ValueError(
            "PBP schema has no recognized tackle-credit player columns; "
            "need solo_tackle_*, tackle_with_assist_*, or assist_tackle_*"
        )
    families = {
        "solo": any(c.startswith("solo_tackle_") for c in present),
        "primary_with_assist": any(c.startswith("tackle_with_assist_") for c in present),
        "assist": any(c.startswith("assist_tackle_") for c in present),
    }
    return {"presentIdColumns": present, "families": families}


def classify_play(row: dict[str, Any]) -> str:
    play_type = _clean(row.get("play_type")).lower()
    if _flag(row.get("special_teams_play")) or play_type in {
        "kickoff", "punt", "field_goal", "extra_point",
    }:
        return "SPECIAL_TEAMS"
    if _flag(row.get("sack")):
        return "SACK"
    if _flag(row.get("interception")):
        return "TURNOVER_RETURN"
    if _flag(row.get("fumble")) and _flag(row.get("fumble_lost")):
        return "FUMBLE_TURNOVER"
    if _flag(row.get("qb_scramble")):
        return "SCRAMBLE"
    if _flag(row.get("rush_attempt")) or play_type == "run" or _flag(row.get("rush")):
        return "RUSH"
    if _flag(row.get("complete_pass")):
        return "COMPLETE_PASS"
    if play_type == "pass" or _flag(row.get("pass_attempt")) or _flag(row.get("qb_dropback")):
        return "OTHER_PASS"
    if play_type in {"qb_kneel", "qb_spike"}:
        return play_type.upper()
    return "OTHER"


def is_nullified(row: dict[str, Any]) -> bool:
    return (
        _flag(row.get("play_deleted"))
        or _flag(row.get("no_play"))
        or _clean(row.get("play_type")).lower() == "no_play"
    )


def extract_credit_events(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Return raw credit events from one PBP row.

    We deliberately preserve slot-level events.  A single play can contain multiple
    tackle events because of fumbles/laterals, and rare plays can contain multiple
    credits for the same person.  Deduplication belongs in reconciliation, not here.
    """
    posteam = _clean(row.get("posteam"))
    defteam = _clean(row.get("defteam"))
    play_family = classify_play(row)
    nullified = is_nullified(row)
    out: list[dict[str, Any]] = []
    for role, slot, id_col, name_col, team_col in CREDIT_SLOTS:
        pid = _clean(row.get(id_col))
        if not pid:
            continue
        team = _clean(row.get(team_col))
        if team and defteam and team == defteam:
            team_role = "ORIGINAL_DEFENSE"
        elif team and posteam and team == posteam:
            team_role = "ORIGINAL_OFFENSE"
        else:
            team_role = "UNKNOWN"
        standard_def_scrimmage = (
            team_role == "ORIGINAL_DEFENSE"
            and not nullified
            and play_family not in {"SPECIAL_TEAMS", "TURNOVER_RETURN", "FUMBLE_TURNOVER"}
            and _clean(row.get("play_type")).lower() not in {"qb_kneel", "qb_spike"}
        )
        out.append({
            "game_id": _clean(row.get("game_id")),
            "play_id": row.get("play_id"),
            "season": row.get("season"),
            "week": row.get("week"),
            "posteam": posteam,
            "defteam": defteam,
            "player_id": pid,
            "player_name_source": _clean(row.get(name_col)),
            "credit_team": team,
            "credit_team_role": team_role,
            "credit_role": role,
            "source_slot": slot,
            "solo_tackle_credit": 1 if role == "SOLO" else 0,
            "tackle_with_assist_credit": 1 if role == "PRIMARY_WITH_ASSIST" else 0,
            "assist_credit": 1 if role == "ASSIST" else 0,
            "combined_credit_unit": 1,
            "play_family": play_family,
            "is_special_teams": 1 if play_family == "SPECIAL_TEAMS" else 0,
            "is_nullified_or_deleted": 1 if nullified else 0,
            "is_original_defense_credit": 1 if team_role == "ORIGINAL_DEFENSE" else 0,
            "is_standard_def_scrimmage_credit": 1 if standard_def_scrimmage else 0,
        })
    return out


def build_play_opportunity_row(row: dict[str, Any], credit_events: list[dict[str, Any]]) -> dict[str, Any]:
    play_family = classify_play(row)
    nullified = is_nullified(row)
    def_credits = [e for e in credit_events if e["credit_team_role"] == "ORIGINAL_DEFENSE"]
    all_credits = list(credit_events)
    return {
        "game_id": _clean(row.get("game_id")),
        "play_id": row.get("play_id"),
        "season": row.get("season"),
        "week": row.get("week"),
        "posteam": _clean(row.get("posteam")),
        "defteam": _clean(row.get("defteam")),
        "play_type": _clean(row.get("play_type")),
        "play_family": play_family,
        "down": row.get("down"),
        "ydstogo": row.get("ydstogo"),
        "yardline_100": row.get("yardline_100"),
        "qtr": row.get("qtr"),
        "game_seconds_remaining": row.get("game_seconds_remaining"),
        "score_differential": row.get("score_differential"),
        "score_differential_post": row.get("score_differential_post"),
        "yards_gained": row.get("yards_gained"),
        "air_yards": row.get("air_yards"),
        "yards_after_catch": row.get("yards_after_catch"),
        "run_location": _clean(row.get("run_location")),
        "run_gap": _clean(row.get("run_gap")),
        "pass_location": _clean(row.get("pass_location")),
        "pass_length": _clean(row.get("pass_length")),
        "shotgun": row.get("shotgun"),
        "no_huddle": row.get("no_huddle"),
        "qb_scramble": row.get("qb_scramble"),
        "sack": row.get("sack"),
        "complete_pass": row.get("complete_pass"),
        "interception": row.get("interception"),
        "fumble": row.get("fumble"),
        "fumble_lost": row.get("fumble_lost"),
        "special_teams_play": row.get("special_teams_play"),
        "is_nullified_or_deleted": 1 if nullified else 0,
        "all_credit_units": len(all_credits),
        "original_defense_credit_units": len(def_credits),
        "original_defense_solo": sum(e["solo_tackle_credit"] for e in def_credits),
        "original_defense_primary_with_assist": sum(e["tackle_with_assist_credit"] for e in def_credits),
        "original_defense_assists": sum(e["assist_credit"] for e in def_credits),
    }


def aggregate_player_games(
    events: Iterable[dict[str, Any]],
    player_meta: dict[str, dict[str, Any]] | None = None,
    game_meta: dict[str, dict[str, Any]] | None = None,
    snap_meta: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    player_meta = player_meta or {}
    game_meta = game_meta or {}
    snap_meta = snap_meta or {}
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in events:
        key = (str(e.get("game_id") or ""), str(e.get("player_id") or ""), str(e.get("credit_team") or ""))
        if not key[0] or not key[1]:
            continue
        g = groups.setdefault(key, {
            "game_id": key[0], "player_id": key[1], "team": key[2],
            "solo": 0, "primary_with_assist": 0, "assists": 0,
            "combined_all": 0, "combined_original_defense": 0,
            "combined_standard_def_scrimmage": 0, "combined_special_teams": 0,
            "rush_credits": 0, "complete_pass_credits": 0, "sack_credits": 0,
            "scramble_credits": 0, "turnover_return_credits": 0,
        })
        g["solo"] += int(e.get("solo_tackle_credit") or 0)
        g["primary_with_assist"] += int(e.get("tackle_with_assist_credit") or 0)
        g["assists"] += int(e.get("assist_credit") or 0)
        g["combined_all"] += 1
        if int(e.get("is_original_defense_credit") or 0):
            g["combined_original_defense"] += 1
        if int(e.get("is_standard_def_scrimmage_credit") or 0):
            g["combined_standard_def_scrimmage"] += 1
        if int(e.get("is_special_teams") or 0):
            g["combined_special_teams"] += 1
        fam = str(e.get("play_family") or "")
        if fam == "RUSH": g["rush_credits"] += 1
        elif fam == "COMPLETE_PASS": g["complete_pass_credits"] += 1
        elif fam == "SACK": g["sack_credits"] += 1
        elif fam == "SCRAMBLE": g["scramble_credits"] += 1
        elif fam in {"TURNOVER_RETURN", "FUMBLE_TURNOVER"}: g["turnover_return_credits"] += 1

    out = []
    for (game_id, pid, team), g in groups.items():
        pm = player_meta.get(pid, {})
        gm = game_meta.get(game_id, {})
        sm = snap_meta.get((game_id, pid), {})
        row = {
            **g,
            "season": gm.get("season"), "week": gm.get("week"), "game_type": gm.get("game_type"),
            "gameday": gm.get("gameday"), "away_team": gm.get("away_team"), "home_team": gm.get("home_team"),
            "display_name": pm.get("display_name", ""), "position": pm.get("position", ""),
            "position_group": pm.get("position_group", ""), "pfr_id": pm.get("pfr_id", ""),
            "defense_snaps": sm.get("defense_snaps"), "defense_pct": sm.get("defense_pct"),
            "special_teams_snaps": sm.get("special_teams_snaps"), "special_teams_pct": sm.get("special_teams_pct"),
        }
        ds = _num(row.get("defense_snaps"))
        row["combined_standard_per_def_snap"] = None if not ds or ds <= 0 else row["combined_standard_def_scrimmage"] / ds
        out.append(row)
    out.sort(key=lambda r: (
        int(r.get("season") or 0), int(r.get("week") or 0), str(r.get("game_id") or ""), str(r.get("player_id") or "")
    ))
    return out


def duplicate_credit_anomalies(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface repeated same-player/same-role credits on a play for manual review.

    We do not automatically delete these. Multiple tackle events can be legitimate on
    a possession-changing play. The audit is meant to force explicit review.
    """
    seen: dict[tuple[str, Any, str, str], int] = defaultdict(int)
    for e in events:
        k = (str(e.get("game_id") or ""), e.get("play_id"), str(e.get("player_id") or ""), str(e.get("credit_role") or ""))
        seen[k] += 1
    out = []
    for (game_id, play_id, pid, role), n in seen.items():
        if n > 1:
            out.append({"game_id": game_id, "play_id": play_id, "player_id": pid, "credit_role": role, "count": n})
    out.sort(key=lambda r: (r["game_id"], str(r["play_id"]), r["player_id"], r["credit_role"]))
    return out

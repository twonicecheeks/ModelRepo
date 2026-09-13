"""OMEGA 0.1.1 exposure-universe hardening.

Purpose: prevent zero-outcome selection bias before any tackle model is fit.
The 0.1 event ledger is immutable and remains the source of observed tackle credits.
This module expands player-game outcomes to include defenders who logged defensive
snaps but received zero standard defensive scrimmage tackle credits.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Iterable

VERSION = "0.1.1"
LINEAGE = "omega-tackle-exposure-universe-v0.1.1-2026-09-11"


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _int(v: Any) -> int:
    x = _num(v)
    return 0 if x is None else int(round(x))


def aggregate_event_player_games(events: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Aggregate immutable 0.1 event rows by game/player/credit team."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for e in events:
        game_id = str(e.get("game_id") or "").strip()
        player_id = str(e.get("player_id") or "").strip()
        team = str(e.get("credit_team") or "").strip()
        if not game_id or not player_id or not team:
            continue
        k = (game_id, player_id)
        g = out.setdefault(k, {
            "credit_team": team,
            "solo": 0,
            "primary_with_assist": 0,
            "assists": 0,
            "combined_all": 0,
            "combined_original_defense": 0,
            "combined_standard_def_scrimmage": 0,
            "combined_special_teams": 0,
        })
        g["solo"] += _int(e.get("solo_tackle_credit"))
        g["primary_with_assist"] += _int(e.get("tackle_with_assist_credit"))
        g["assists"] += _int(e.get("assist_credit"))
        g["combined_all"] += _int(e.get("combined_credit_unit") or 1)
        g["combined_original_defense"] += _int(e.get("is_original_defense_credit"))
        if _int(e.get("is_standard_def_scrimmage_credit")):
            g["combined_standard_def_scrimmage"] += _int(e.get("combined_credit_unit") or 1)
        if _int(e.get("is_special_teams")):
            g["combined_special_teams"] += _int(e.get("combined_credit_unit") or 1)
    return out


def build_expanded_rows(
    snap_rows: Iterable[dict[str, Any]],
    event_groups: dict[tuple[str, str], dict[str, Any]],
    *,
    pfr_to_gsis: dict[str, str],
    player_meta: dict[str, dict[str, Any]] | None = None,
    allowed_game_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Union defensive-snap exposure rows with all event-positive rows.

    Rows with defensive snaps and zero tackle credits are retained with an explicit
    zero target. Event-positive rows lacking a snap join are retained for audit but
    marked ineligible for exposure-rate fitting.
    """
    player_meta = player_meta or {}
    allowed_game_ids = allowed_game_ids or set()
    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    unresolved_snap_rows = 0
    snap_def_rows = 0
    resolved_snap_def_rows = 0

    for r in snap_rows:
        game_id = str(r.get("game_id") or "").strip()
        if not game_id or (allowed_game_ids and game_id not in allowed_game_ids):
            continue
        ds = _num(r.get("defense_snaps"))
        if ds is None or ds <= 0:
            continue
        snap_def_rows += 1
        pfr = str(r.get("pfr_player_id") or "").strip()
        gsis = pfr_to_gsis.get(pfr, "")
        if not gsis:
            unresolved_snap_rows += 1
            # Preserve the exposure row for audit, but never train player identity
            # models on a synthetic identifier.
            pid = f"PFR:{pfr}" if pfr else ""
            identity_resolved = 0
        else:
            pid = gsis
            identity_resolved = 1
            resolved_snap_def_rows += 1
        team = str(r.get("team") or "").strip()
        if not pid or not team:
            continue
        k = (game_id, pid)
        pm = player_meta.get(gsis, {}) if gsis else {}
        ev = event_groups.get(k, {})
        event_team = str(ev.get("credit_team") or "").strip()
        rows_by_key[k] = {
            "game_id": game_id,
            "season": _int(r.get("season")),
            "week": _int(r.get("week")),
            "game_type": str(r.get("game_type") or ""),
            "team": event_team or team,
            "opponent": str(r.get("opponent") or ""),
            "player_id": pid,
            "pfr_player_id": pfr,
            "display_name": str(pm.get("display_name") or r.get("player") or ""),
            "position": str(pm.get("position") or r.get("position") or ""),
            "position_group": str(pm.get("position_group") or ""),
            "defense_snaps": ds,
            "defense_pct": _num(r.get("defense_pct")),
            "special_teams_snaps": _num(r.get("special_teams_snaps")),
            "special_teams_pct": _num(r.get("special_teams_pct")),
            "identity_resolved": identity_resolved,
            "exposure_source": "SNAP_COUNTS",
            "eligible_standard_rate_fit": 1 if identity_resolved else 0,
            "solo": int(ev.get("solo", 0)),
            "primary_with_assist": int(ev.get("primary_with_assist", 0)),
            "assists": int(ev.get("assists", 0)),
            "combined_all": int(ev.get("combined_all", 0)),
            "combined_original_defense": int(ev.get("combined_original_defense", 0)),
            "combined_standard_def_scrimmage": int(ev.get("combined_standard_def_scrimmage", 0)),
            "combined_special_teams": int(ev.get("combined_special_teams", 0)),
        }

    event_only = 0
    for (game_id, pid), ev in event_groups.items():
        team = str(ev.get("credit_team") or "").strip()
        if allowed_game_ids and game_id not in allowed_game_ids:
            continue
        if int(ev.get("combined_standard_def_scrimmage", 0)) <= 0:
            continue
        k = (game_id, pid)
        if k in rows_by_key:
            continue
        event_only += 1
        pm = player_meta.get(pid, {})
        rows_by_key[k] = {
            "game_id": game_id,
            "season": None,
            "week": None,
            "game_type": "REG",
            "team": team,
            "opponent": "",
            "player_id": pid,
            "pfr_player_id": str(pm.get("pfr_id") or ""),
            "display_name": str(pm.get("display_name") or ""),
            "position": str(pm.get("position") or ""),
            "position_group": str(pm.get("position_group") or ""),
            "defense_snaps": None,
            "defense_pct": None,
            "special_teams_snaps": None,
            "special_teams_pct": None,
            "identity_resolved": 1,
            "exposure_source": "EVENT_ONLY_NO_SNAP",
            "eligible_standard_rate_fit": 0,
            "solo": int(ev.get("solo", 0)),
            "primary_with_assist": int(ev.get("primary_with_assist", 0)),
            "assists": int(ev.get("assists", 0)),
            "combined_all": int(ev.get("combined_all", 0)),
            "combined_original_defense": int(ev.get("combined_original_defense", 0)),
            "combined_standard_def_scrimmage": int(ev.get("combined_standard_def_scrimmage", 0)),
            "combined_special_teams": int(ev.get("combined_special_teams", 0)),
        }

    out = list(rows_by_key.values())
    out.sort(key=lambda x: (int(x.get("season") or 0), int(x.get("week") or 0), x["game_id"], x["team"], x["player_id"]))
    zero_standard = sum(1 for r in out if r.get("exposure_source") == "SNAP_COUNTS" and int(r.get("combined_standard_def_scrimmage") or 0) == 0)
    fit_rows = sum(int(r.get("eligible_standard_rate_fit") or 0) for r in out)
    audit = {
        "snapDefensiveExposureRows": snap_def_rows,
        "resolvedSnapDefensiveExposureRows": resolved_snap_def_rows,
        "unresolvedSnapDefensiveExposureRows": unresolved_snap_rows,
        "eventOnlyPositiveRows": event_only,
        "expandedRows": len(out),
        "fitEligibleRows": fit_rows,
        "zeroStandardCreditSnapRows": zero_standard,
        "zeroStandardCreditRatePct": round(100.0 * zero_standard / resolved_snap_def_rows, 4) if resolved_snap_def_rows else None,
    }
    return out, audit

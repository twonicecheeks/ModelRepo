"""NFL State Intelligence 0.1.5 — Thursday interaction research pack.

Development-only, coefficient-free diagnostics motivated by DET@BUF (2026 Week 2)
and the earlier DEN@KC drive ledger. This module deliberately does *not* mutate
frozen OMEGA forecasts, fit production coefficients, consume sportsbook data, or
open the sealed 2025 holdout.

The goal is to turn qualitative drive-ledger findings into reproducible historical
features that current nflverse State Intelligence can actually support:

* pass/run intent by score state (scrambles/sacks remain pass-origin plays),
* QB scramble drive-survival rather than rushing yards alone,
* sack-vs-scramble outcome geometry on dropbacks,
* explosive-play concentration and suppression,
* drive-to-drive offensive mechanism adaptation,
* response-drive scoring,
* nullified high-impact plays erased by penalties,
* penalty leverage using observed WPA/EPA when available,
* early-down run success -> later structural pass-rush exposure.

Several Thursday findings require tracking/player-identity data that the current
State Intelligence snapshot does not contain. They are reported explicitly through
DATA_GAPS rather than fabricated from play-by-play proxies.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Iterable
import math
import re

VERSION = "0.1.5"
LINEAGE = "nfl-state-thursday-interactions-v0.1.5-det-buf-2026-09-17"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

DROPBACK_INTENTS = {"DESIGNED_PASS", "DROPBACK_SCRAMBLE", "DROPBACK_SACK"}
SCRIMMAGE_INTENTS = DROPBACK_INTENTS | {"DESIGNED_RUN"}

DATA_GAPS = {
    "TRUE_PRESSURE_GEOMETRY": "Requires charted/tracking pressure paths; PBP only supports sack/scramble outcome proxies.",
    "RUSH_LANE_INTEGRITY": "Requires defender tracking or charting; cannot be inferred safely from sacks/scrambles alone.",
    "TIME_TO_THROW": "Not present in the current State Intelligence normalized snapshot.",
    "RECEIVER_SEPARATION": "Requires tracking/charting data; Amon-Ra-style separator effect cannot be measured from current PBP.",
    "COVERAGE_SHELL": "Requires charting/tracking; current PBP does not identify Cover 1/3/4/6 reliably.",
    "DESIGNED_QB_RUN_GRAVITY": "Current State snapshot lacks rusher identity, so designed QB rushes cannot be separated from RB runs.",
    "TACKLER_IDENTITY_REDISTRIBUTION": "Current State snapshot lacks tackler identity; player-level OMEGA opportunity redistribution needs a richer results layer.",
    "RECEIVER_POSITION_ROUTE_LOCATION": "Current State snapshot lacks receiver identity/position and pass-location charting needed for TE/deep-middle interaction tests.",
}

_YARD_RE = re.compile(r"\bfor\s+(-?\d+)\s+yards?\b", re.IGNORECASE)


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _flag(row: dict[str, Any], key: str) -> bool:
    return _num(row.get(key)) == 1.0


def _feat(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("state_intelligence")
    return value if isinstance(value, dict) else {}


def _intent(row: dict[str, Any]) -> str:
    return str(_feat(row).get("play_intent") or "")


def _desc(row: dict[str, Any]) -> str:
    return str(row.get("desc") or "")


def _competitive(row: dict[str, Any]) -> bool:
    feat = _feat(row)
    return bool(
        feat.get("football_tendency_eligible")
        and feat.get("competitive_state") == "COMPETITIVE"
        and _intent(row) in SCRIMMAGE_INTENTS
    )


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    seasons = tuple(sorted({int(s) for s in seasons}))
    if not seasons:
        raise ValueError("at least one development season is required")
    forbidden = [s for s in seasons if s >= SEALED_HOLDOUT_SEASON]
    if forbidden:
        raise ValueError(
            "Thursday interaction discovery is development-only; sealed 2025 holdout and 2026 prospective data are forbidden: "
            + ",".join(map(str, forbidden))
        )
    return seasons


def score_margin_bucket(row: dict[str, Any]) -> str | None:
    """Possession-team score state from pre-snap score differential."""
    margin = _num(row.get("score_differential"))
    if margin is None:
        return None
    if margin >= 9:
        return "LEADING_9_PLUS"
    if margin >= 1:
        return "LEADING_1_8"
    if margin == 0:
        return "TIED"
    if margin <= -9:
        return "TRAILING_9_PLUS"
    return "TRAILING_1_8"


def _desc_yards(row: dict[str, Any]) -> int | None:
    m = _YARD_RE.search(_desc(row))
    return int(m.group(1)) if m else None


def nullified_impact_types(row: dict[str, Any]) -> tuple[str, ...]:
    """Recover meaningful football events hidden by official no-play grading.

    M19/M20 from DET@BUF: an interception and a sack erased by defensive holding
    should disappear from official stats but not from diagnostic QB/defense grading.
    This parser is intentionally conservative and only operates on rows explicitly
    marked no-play (or play_type=no_play).
    """
    feat = _feat(row)
    no_play = _flag(row, "no_play") or str(feat.get("play_intent") or "") == "NO_PLAY" or str(row.get("play_type") or "").lower() == "no_play"
    if not no_play:
        return ()
    d = _desc(row).lower()
    out: list[str] = []
    if "intercepted" in d:
        out.append("NULLIFIED_INTERCEPTION")
    if "sacked" in d or " sack" in d:
        out.append("NULLIFIED_SACK")
    if "fumble" in d:
        out.append("NULLIFIED_FUMBLE")
    yards = _desc_yards(row)
    if yards is not None and yards >= 20:
        out.append("NULLIFIED_EXPLOSIVE")
    return tuple(dict.fromkeys(out))


def penalty_leverage(row: dict[str, Any], *, wpa_candidate_threshold: float = 0.05) -> dict[str, Any]:
    """Describe penalty leverage without inventing an EPA/WPA model.

    high_leverage_candidate is a research flag, not a fitted coefficient.
    """
    erased = nullified_impact_types(row)
    epa = _num(row.get("epa"))
    wpa = _num(row.get("wpa"))
    y100 = _num(row.get("yardline_100"))
    red_zone = y100 is not None and y100 <= 20
    goal_to_go = _flag(row, "goal_to_go")
    candidate = bool(
        erased
        or red_zone
        or goal_to_go
        or (wpa is not None and abs(wpa) >= float(wpa_candidate_threshold))
    )
    return {
        "penalty": _flag(row, "penalty") or bool(erased),
        "erased_impact_types": erased,
        "epa": epa,
        "abs_epa": abs(epa) if epa is not None else None,
        "wpa": wpa,
        "abs_wpa": abs(wpa) if wpa is not None else None,
        "red_zone": red_zone,
        "goal_to_go": goal_to_go,
        "high_leverage_candidate": candidate,
        "wpa_candidate_threshold": float(wpa_candidate_threshold),
    }


def _play_sort_key(item: tuple[int, dict[str, Any]]) -> tuple[float, int]:
    i, row = item
    pid = _num(row.get("play_id"))
    return (pid if pid is not None else float(i), i)


def _drive_scored(rows: list[dict[str, Any]]) -> bool:
    """Conservative text/field detector for an offensive scoring drive."""
    for row in rows:
        d = _desc(row).lower()
        if "touchdown" in d and not _flag(row, "interception") and not _flag(row, "fumble_lost"):
            return True
        if "field goal" in d and ("is good" in d or "good" in d):
            return True
    return False


def _mechanism_vector(rec: dict[str, Any]) -> tuple[float, float, float]:
    n = max(1, int(rec.get("scrimmage_plays") or 0))
    return (
        float(rec.get("designed_runs") or 0) / n,
        float(rec.get("designed_passes") or 0) / n,
        float(rec.get("scrambles") or 0) / n,
    )


def build_drive_records(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate competitive scrimmage snaps into offense-drive diagnostics."""
    materialized = [dict(r) for r in rows]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    order: dict[tuple[str, str, str], float] = {}

    for idx, row in enumerate(materialized):
        gid = str(row.get("game_id") or "")
        team = str(row.get("posteam") or "").upper()
        drive = str(row.get("drive") or "")
        if not gid or not team or not drive:
            continue
        key = (gid, team, drive)
        groups[key].append(row)
        pid = _num(row.get("play_id"))
        marker = pid if pid is not None else float(idx)
        order[key] = min(marker, order.get(key, marker))

    out: list[dict[str, Any]] = []
    for (gid, team, drive), raw_rows in groups.items():
        raw_rows = [r for _i, r in sorted(enumerate(raw_rows), key=_play_sort_key)]
        plays = [r for r in raw_rows if _competitive(r)]
        if not plays:
            continue

        intents = [_intent(r) for r in plays]
        designed_runs = sum(i == "DESIGNED_RUN" for i in intents)
        designed_passes = sum(i == "DESIGNED_PASS" for i in intents)
        scrambles = sum(i == "DROPBACK_SCRAMBLE" for i in intents)
        sacks = sum(i == "DROPBACK_SACK" for i in intents)
        dropbacks = designed_passes + scrambles + sacks

        explosive = [r for r in plays if (_num(r.get("yards_gained")) or 0.0) >= 20.0]
        positive_yards = sum(max(0.0, _num(r.get("yards_gained")) or 0.0) for r in plays)
        first_scrimmage = plays[0]
        start_yardline_100 = _num(first_scrimmage.get("yardline_100"))
        start_game_seconds = _num(first_scrimmage.get("game_seconds_remaining"))
        explosive_yards = sum(max(0.0, _num(r.get("yards_gained")) or 0.0) for r in explosive)

        scramble_first_downs = sum(
            _intent(r) == "DROPBACK_SCRAMBLE" and _flag(r, "first_down") for r in plays
        )
        scramble_late_down_conversions = sum(
            _intent(r) == "DROPBACK_SCRAMBLE"
            and (_num(r.get("down")) in (3.0, 4.0))
            and _flag(r, "first_down")
            for r in plays
        )
        high_exposure_dropbacks = sum(
            _intent(r) in DROPBACK_INTENTS
            and str(_feat(r).get("pressure_opportunity_bucket") or "") == "HIGH_STRUCTURAL_EXPOSURE"
            for r in plays
        )

        early_runs = [r for r in plays if _intent(r) == "DESIGNED_RUN" and _num(r.get("down")) in (1.0, 2.0)]
        early_run_success_vals: list[float] = []
        for r in early_runs:
            success = _num(r.get("success"))
            if success is not None:
                early_run_success_vals.append(1.0 if success >= 0.5 else 0.0)
            else:
                epa = _num(r.get("epa"))
                if epa is not None:
                    early_run_success_vals.append(1.0 if epa > 0 else 0.0)

        catastrophic = [
            r for r in plays
            if _intent(r) == "DROPBACK_SACK"
            or _flag(r, "fumble")
            or _flag(r, "fumble_lost")
            or _flag(r, "interception")
            or _flag(r, "aborted_play")
            or "aborted" in _desc(r).lower()
        ]
        penalties = [r for r in raw_rows if _flag(r, "penalty") or nullified_impact_types(r)]
        leverage = [penalty_leverage(r) for r in penalties]
        nullified = [x for r in raw_rows for x in nullified_impact_types(r)]

        sack_or_scramble = sacks + scrambles
        out.append({
            "game_id": gid,
            "posteam": team,
            "drive": drive,
            "start_play_id": order[(gid, team, drive)],
            "scrimmage_plays": len(plays),
            "start_yardline_100": start_yardline_100,
            "start_game_seconds_remaining": start_game_seconds,
            "designed_runs": designed_runs,
            "designed_passes": designed_passes,
            "scrambles": scrambles,
            "sacks": sacks,
            "dropbacks": dropbacks,
            "pass_intent_rate": dropbacks / len(plays),
            "run_intent_rate": designed_runs / len(plays),
            "scramble_rate_per_dropback": scrambles / dropbacks if dropbacks else None,
            "sack_rate_per_dropback": sacks / dropbacks if dropbacks else None,
            "sack_share_of_sack_or_scramble_outcomes": sacks / sack_or_scramble if sack_or_scramble else None,
            "scramble_first_downs": scramble_first_downs,
            "scramble_late_down_conversions": scramble_late_down_conversions,
            "high_exposure_dropbacks": high_exposure_dropbacks,
            "high_exposure_dropback_rate": high_exposure_dropbacks / dropbacks if dropbacks else None,
            "explosive_plays_20_plus": len(explosive),
            "explosive_yards": explosive_yards,
            "positive_yards": positive_yards,
            "explosive_positive_yard_share": explosive_yards / positive_yards if positive_yards > 0 else None,
            "early_down_designed_runs": len(early_runs),
            "early_down_run_success_rate": fmean(early_run_success_vals) if early_run_success_vals else None,
            "scoring_drive": _drive_scored(raw_rows),
            "penalties": len(penalties),
            "high_leverage_penalty_candidates": sum(bool(x["high_leverage_candidate"]) for x in leverage),
            "nullified_impact_events": len(nullified),
            "catastrophic_negative_events": len(catastrophic),
            "nullified_impact_types": tuple(sorted(nullified)),
        })

    out.sort(key=lambda r: (str(r["game_id"]), float(r["start_play_id"]), str(r["posteam"]), str(r["drive"])))
    return out


def attach_response_drive_flags(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark possessions immediately following an opponent scoring drive."""
    rows = [dict(r) for r in records]
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_game[str(r.get("game_id") or "")].append(r)

    out: list[dict[str, Any]] = []
    for gid, game_rows in by_game.items():
        game_rows.sort(key=lambda r: (float(r.get("start_play_id") or 0.0), str(r.get("drive") or "")))
        prev: dict[str, Any] | None = None
        for r in game_rows:
            response = bool(
                prev
                and prev.get("scoring_drive")
                and str(prev.get("posteam") or "") != str(r.get("posteam") or "")
            )
            x = dict(r)
            x["response_to_opponent_score"] = response
            x["response_drive_scored"] = bool(response and r.get("scoring_drive"))
            out.append(x)
            prev = r
    out.sort(key=lambda r: (str(r["game_id"]), float(r["start_play_id"]), str(r["posteam"])))
    return out


def attach_game_sequence_context(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add cumulative defensive-load and prior-drive context proxies.

    This is a snap-load/field-position proxy, not a claim of physiological fatigue.
    """
    rows=[dict(r) for r in records]
    by_game: dict[str,list[dict[str,Any]]]=defaultdict(list)
    for r in rows:
        by_game[str(r.get("game_id") or "")].append(r)
    out=[]
    for gid,rs in by_game.items():
        rs.sort(key=lambda r:(float(r.get("start_play_id") or 0.0),str(r.get("drive") or "")))
        prior_offense_plays: dict[str,int]=defaultdict(int)
        prev: dict[str,Any]|None=None
        for r in rs:
            team=str(r.get("posteam") or "")
            x=dict(r)
            x["opponent_defensive_snap_load_before_drive"]=prior_offense_plays[team]
            x["prior_drive_team"]=str(prev.get("posteam") or "") if prev else None
            x["prior_drive_scored"]=bool(prev.get("scoring_drive")) if prev else None
            x["prior_drive_start_yardline_100"]=prev.get("start_yardline_100") if prev else None
            out.append(x)
            prior_offense_plays[team]+=int(r.get("scrimmage_plays") or 0)
            prev=r
    out.sort(key=lambda r:(str(r.get("game_id") or ""),float(r.get("start_play_id") or 0.0)))
    return out


def post_first_sack_adaptation(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Team-game diagnostic for performance before vs after first sack."""
    by: dict[tuple[str,str],list[dict[str,Any]]]=defaultdict(list)
    for r in rows:
        if _competitive(r) and _intent(r) in DROPBACK_INTENTS:
            by[(str(r.get("game_id") or ""),str(r.get("posteam") or "").upper())].append(dict(r))
    out={}
    for (gid,team),rs in by.items():
        rs=[r for _i,r in sorted(enumerate(rs),key=_play_sort_key)]
        first_sack=next((i for i,r in enumerate(rs) if _intent(r)=="DROPBACK_SACK"),None)
        if first_sack is None:
            continue
        pre=[_num(r.get("epa")) for r in rs[:first_sack+1]]
        post=[_num(r.get("epa")) for r in rs[first_sack+1:]]
        pre=[x for x in pre if x is not None]
        post=[x for x in post if x is not None]
        out[f"{gid}|{team}"]={
            "game_id":gid,"team":team,"first_sack_dropback_index":first_sack,
            "pre_through_first_sack_dropbacks":first_sack+1,"post_first_sack_dropbacks":len(rs)-first_sack-1,
            "pre_through_first_sack_mean_epa":fmean(pre) if pre else None,
            "post_first_sack_mean_epa":fmean(post) if post else None,
            "epa_change_post_minus_pre":(fmean(post)-fmean(pre)) if pre and post else None,
        }
    return out


def _intent_by_score(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    c: dict[str, dict[str, float]] = defaultdict(lambda: {"plays": 0.0, "pass_origin": 0.0, "designed_run": 0.0})
    for r in rows:
        if not _competitive(r):
            continue
        bucket = score_margin_bucket(r)
        if bucket is None:
            continue
        intent = _intent(r)
        c[bucket]["plays"] += 1
        if intent in DROPBACK_INTENTS:
            c[bucket]["pass_origin"] += 1
        elif intent == "DESIGNED_RUN":
            c[bucket]["designed_run"] += 1
    out: dict[str, dict[str, Any]] = {}
    for bucket, x in sorted(c.items()):
        n = x["plays"]
        out[bucket] = {
            "plays": int(n),
            "pass_intent_rate": x["pass_origin"] / n if n else None,
            "run_intent_rate": x["designed_run"] / n if n else None,
        }
    return out


def _adaptation_by_team(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_team: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_team[(str(r["game_id"]), str(r["posteam"]))].append(r)
    out: dict[str, dict[str, Any]] = {}
    for (gid, team), rs in by_team.items():
        rs.sort(key=lambda r: float(r.get("start_play_id") or 0.0))
        shifts: list[float] = []
        for a, b in zip(rs, rs[1:]):
            av = _mechanism_vector(a)
            bv = _mechanism_vector(b)
            shifts.append(0.5 * sum(abs(x - y) for x, y in zip(av, bv)))
        key = f"{gid}|{team}"
        out[key] = {
            "game_id": gid,
            "team": team,
            "drives": len(rs),
            "consecutive_drive_pairs": len(shifts),
            "mean_mechanism_shift_tv": fmean(shifts) if shifts else None,
            "max_mechanism_shift_tv": max(shifts) if shifts else None,
        }
    return out


def summarize_game_interactions(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize one or more games without fitting coefficients."""
    rows = [dict(r) for r in rows]
    drives = attach_game_sequence_context(attach_response_drive_flags(build_drive_records(rows)))
    nullified_rows = []
    penalty_rows = []
    for r in rows:
        erased = nullified_impact_types(r)
        if erased:
            nullified_rows.append({
                "game_id": r.get("game_id"),
                "play_id": r.get("play_id"),
                "posteam": r.get("posteam"),
                "defteam": r.get("defteam"),
                "types": erased,
                "desc": _desc(r),
            })
        if _flag(r, "penalty") or erased:
            penalty_rows.append(penalty_leverage(r))

    response = [r for r in drives if r.get("response_to_opponent_score")]
    scramble_drives = [r for r in drives if int(r.get("scrambles") or 0) > 0]
    explosive_drives = [r for r in drives if int(r.get("explosive_plays_20_plus") or 0) > 0]
    clean_containment_drives = [
        r for r in drives
        if int(r.get("scramble_late_down_conversions") or 0) == 0
        and int(r.get("explosive_plays_20_plus") or 0) == 0
    ]

    return {
        "version": VERSION,
        "lineage": LINEAGE,
        "games": len({str(r.get("game_id") or "") for r in rows if r.get("game_id")}),
        "drive_records": drives,
        "intent_by_score_state": _intent_by_score(rows),
        "adaptation_by_game_team": _adaptation_by_team(drives),
        "post_first_sack_adaptation": post_first_sack_adaptation(rows),
        "nullified_impact_events": nullified_rows,
        "penalty_leverage": {
            "penalty_or_nullified_rows": len(penalty_rows),
            "high_leverage_candidates": sum(bool(x["high_leverage_candidate"]) for x in penalty_rows),
            "rows_with_wpa": sum(x["wpa"] is not None for x in penalty_rows),
            "rows_with_erased_major_event": sum(bool(x["erased_impact_types"]) for x in penalty_rows),
        },
        "response_drives": {
            "n": len(response),
            "scored": sum(bool(r.get("response_drive_scored")) for r in response),
            "score_rate": (sum(bool(r.get("response_drive_scored")) for r in response) / len(response)) if response else None,
        },
        "qb_scramble_drive_survival": {
            "drives_with_scramble": len(scramble_drives),
            "scramble_first_downs": sum(int(r.get("scramble_first_downs") or 0) for r in drives),
            "late_down_scramble_conversions": sum(int(r.get("scramble_late_down_conversions") or 0) for r in drives),
        },
        "explosive_concentration": {
            "drives_with_20_plus_play": len(explosive_drives),
            "explosive_plays_20_plus": sum(int(r.get("explosive_plays_20_plus") or 0) for r in drives),
            "explosive_yards": sum(float(r.get("explosive_yards") or 0.0) for r in drives),
            "positive_yards": sum(float(r.get("positive_yards") or 0.0) for r in drives),
        },
        "containment_x_explosive_suppression_proxy": {
            "drives_with_no_late_down_scramble_conversion_and_no_20_plus_play": len(clean_containment_drives),
            "scoring_rate_on_those_drives": (
                sum(bool(r.get("scoring_drive")) for r in clean_containment_drives) / len(clean_containment_drives)
                if clean_containment_drives else None
            ),
            "interpretation": "PBP proxy only; true containment/rush-lane geometry requires tracking data.",
        },
        "data_gaps": DATA_GAPS,
        "market_dependency": False,
        "frozen_omega_mutation": False,
        "training_or_refit_performed": False,
    }


def build_historical_game_team_records(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact one-row-per-game-team dataset for later challenger work."""
    rows = [dict(r) for r in rows]
    drives = attach_game_sequence_context(attach_response_drive_flags(build_drive_records(rows)))
    by_team: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for d in drives:
        by_team[(str(d["game_id"]), str(d["posteam"]))].append(d)

    out: list[dict[str, Any]] = []
    for (gid, team), ds in sorted(by_team.items()):
        plays = sum(int(d["scrimmage_plays"]) for d in ds)
        dropbacks = sum(int(d["dropbacks"]) for d in ds)
        scrambles = sum(int(d["scrambles"]) for d in ds)
        sacks = sum(int(d["sacks"]) for d in ds)
        explosive_yards = sum(float(d["explosive_yards"]) for d in ds)
        positive_yards = sum(float(d["positive_yards"]) for d in ds)
        response = [d for d in ds if d.get("response_to_opponent_score")]
        early = [d for d in ds if d.get("early_down_run_success_rate") is not None]
        high_exp = sum(int(d["high_exposure_dropbacks"]) for d in ds)
        shifts = []
        ordered = sorted(ds, key=lambda d: float(d.get("start_play_id") or 0.0))
        for a, b in zip(ordered, ordered[1:]):
            shifts.append(0.5 * sum(abs(x-y) for x,y in zip(_mechanism_vector(a), _mechanism_vector(b))))
        out.append({
            "game_id": gid,
            "team": team,
            "drives": len(ds),
            "scrimmage_plays": plays,
            "dropbacks": dropbacks,
            "scrambles": scrambles,
            "sacks": sacks,
            "scramble_rate_per_dropback": scrambles / dropbacks if dropbacks else None,
            "sack_rate_per_dropback": sacks / dropbacks if dropbacks else None,
            "late_down_scramble_conversions": sum(int(d["scramble_late_down_conversions"]) for d in ds),
            "explosive_plays_20_plus": sum(int(d["explosive_plays_20_plus"]) for d in ds),
            "explosive_positive_yard_share": explosive_yards / positive_yards if positive_yards > 0 else None,
            "high_exposure_dropback_rate": high_exp / dropbacks if dropbacks else None,
            "early_down_run_success_rate": fmean(float(d["early_down_run_success_rate"]) for d in early) if early else None,
            "response_drives": len(response),
            "response_drive_score_rate": sum(bool(d.get("response_drive_scored")) for d in response) / len(response) if response else None,
            "mean_drive_mechanism_shift_tv": fmean(shifts) if shifts else None,
            "scoring_drive_rate": sum(bool(d.get("scoring_drive")) for d in ds) / len(ds) if ds else None,
            "nullified_impact_events": sum(int(d.get("nullified_impact_events") or 0) for d in ds),
            "catastrophic_negative_events": sum(int(d.get("catastrophic_negative_events") or 0) for d in ds),
            "mean_start_yardline_100": fmean(float(d["start_yardline_100"]) for d in ds if d.get("start_yardline_100") is not None) if any(d.get("start_yardline_100") is not None for d in ds) else None,
            "max_opponent_defensive_snap_load_before_drive": max(int(d.get("opponent_defensive_snap_load_before_drive") or 0) for d in ds) if ds else 0,
            "high_leverage_penalty_candidates": sum(int(d.get("high_leverage_penalty_candidates") or 0) for d in ds),
        })
    return out


if __name__ == "__main__":
    print(f"NFL State Intelligence {VERSION} · {LINEAGE}")

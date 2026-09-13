"""OMEGA 0.8 — H005 venue/year official-credit environment challenger.

This module tests a pre-registered scoring-environment hypothesis without using any
sportsbook data.  Because the frozen Phase1 schedule artifact does not contain an
actual stadium or scorer identifier, H005 uses ``source_home_team`` on games whose
``location`` is Home as a *home-franchise venue proxy*.  Neutral-site games receive
no venue adjustment.

H004 is not promoted as the T+A champion: its credit-class decomposition is used as
a research scaffold because H005 is specifically about assist-credit behavior.
H008 remains the frozen T+A champion unless H005 beats it under the pre-committed
combined-count gate.
"""
from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.8.0"
LINEAGE = "omega-tackle-v0.8.0-h005-venue-year-credit-environment-2026-09-11"
HOLDOUT_SEASON = 2025
VENUE_FULL_WEIGHT_GAMES = 24.0  # about three regular seasons of home games
DEV_VENUE_SEASONS = (2021, 2022, 2023)
YEAR_ANCHOR_SEASON = 2023


def num(v: Any, default: float | None = None) -> float | None:
    if v in (None, ""):
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x else x


def as_int(v: Any) -> int:
    return int(round(float(num(v, 0.0) or 0.0)))


def is_home_location(v: Any) -> bool:
    return str(v or "").strip().lower() == "home"


def build_game_identity_map(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        season = as_int(r.get("season"))
        if season == HOLDOUT_SEASON:
            # Identity rows may exist in the Phase1 artifact, but H005 must not use
            # the 2025 schedule while the OMEGA holdout is sealed.
            continue
        if season < 2016 or season > 2024:
            continue
        gid = str(r.get("game_id") or "")
        if not gid:
            continue
        out[gid] = {
            "game_id": gid,
            "season": season,
            "week": as_int(r.get("week")),
            "source_home_team": str(r.get("source_home_team") or r.get("home_team") or ""),
            "home_team": str(r.get("home_team") or ""),
            "away_team": str(r.get("away_team") or ""),
            "location": str(r.get("location") or ""),
        }
    return out


def aggregate_game_credit_predictions(player_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate H004 player predictions/actuals to one game-level credit record."""
    by: dict[str, dict[str, Any]] = {}
    for r in player_rows:
        gid = str(r.get("game_id") or "")
        if not gid:
            continue
        g = by.setdefault(gid, {
            "game_id": gid,
            "season": as_int(r.get("season")),
            "week": as_int(r.get("week")),
            "actual_primary": 0.0,
            "actual_assist": 0.0,
            "pred_primary": 0.0,
            "pred_assist": 0.0,
            "actual_xtc": 0.0,
            "pred_h004_xtc": 0.0,
            "player_rows": 0,
        })
        g["actual_primary"] += float(num(r.get("actual_primary_total"), 0.0) or 0.0)
        g["actual_assist"] += float(num(r.get("actual_assist_total"), 0.0) or 0.0)
        g["pred_primary"] += float(num(r.get("pred_primary_total"), 0.0) or 0.0)
        g["pred_assist"] += float(num(r.get("pred_assist_total"), 0.0) or 0.0)
        g["actual_xtc"] += float(num(r.get("actual_xtc"), 0.0) or 0.0)
        g["pred_h004_xtc"] += float(num(r.get("h004_xtc"), 0.0) or 0.0)
        g["player_rows"] += 1
    return sorted(by.values(), key=lambda x: (x["season"], x["week"], x["game_id"]))


def _ratio(actual: float, predicted: float) -> float:
    return actual / predicted if predicted > 0 else 1.0


def build_environment_prior(
    game_rows: Sequence[dict[str, Any]],
    game_identity: dict[str, dict[str, Any]],
    *,
    venue_seasons: Sequence[int] = DEV_VENUE_SEASONS,
    year_anchor_season: int = YEAR_ANCHOR_SEASON,
) -> dict[str, Any]:
    """Build a parameter-free, strictly pre-2024 venue/year assist environment.

    * Year factor = league-wide actual/predicted assist ratio in the immediately
      preceding season (2023 for 2024 confirmation).
    * Venue factor = a venue-proxy assist residual over 2021-2023, normalized by the
      league-wide residual over those same seasons. It is linearly credibility-
      weighted toward 1.0 until roughly 24 prior home games are available.

    The venue proxy is source_home_team and applies only to standard Home-location
    games. This is deliberately labeled a proxy, not an actual stadium/scorer ID.
    """
    vset = {int(x) for x in venue_seasons}
    dev = [r for r in game_rows if as_int(r.get("season")) in vset]
    anchor = [r for r in game_rows if as_int(r.get("season")) == int(year_anchor_season)]
    dev_actual = sum(float(num(r.get("actual_assist"), 0.0) or 0.0) for r in dev)
    dev_pred = sum(float(num(r.get("pred_assist"), 0.0) or 0.0) for r in dev)
    anchor_actual = sum(float(num(r.get("actual_assist"), 0.0) or 0.0) for r in anchor)
    anchor_pred = sum(float(num(r.get("pred_assist"), 0.0) or 0.0) for r in anchor)
    dev_global_ratio = _ratio(dev_actual, dev_pred)
    year_multiplier = _ratio(anchor_actual, anchor_pred)

    by_venue: dict[str, dict[str, float]] = defaultdict(lambda: {
        "games": 0.0, "actual_assist": 0.0, "pred_assist": 0.0,
    })
    excluded_nonhome = 0
    for r in dev:
        meta = game_identity.get(str(r.get("game_id") or ""), {})
        if not is_home_location(meta.get("location")):
            excluded_nonhome += 1
            continue
        venue = str(meta.get("source_home_team") or "")
        if not venue:
            excluded_nonhome += 1
            continue
        v = by_venue[venue]
        v["games"] += 1.0
        v["actual_assist"] += float(num(r.get("actual_assist"), 0.0) or 0.0)
        v["pred_assist"] += float(num(r.get("pred_assist"), 0.0) or 0.0)

    venue_profiles: dict[str, dict[str, float]] = {}
    for venue, v in sorted(by_venue.items()):
        raw_ratio = _ratio(v["actual_assist"], v["pred_assist"])
        relative = raw_ratio / dev_global_ratio if dev_global_ratio > 0 else 1.0
        weight = min(1.0, v["games"] / VENUE_FULL_WEIGHT_GAMES)
        shrunk_relative = 1.0 + weight * (relative - 1.0)
        venue_profiles[venue] = {
            "games": v["games"],
            "actual_assist": v["actual_assist"],
            "pred_assist": v["pred_assist"],
            "raw_assist_ratio": raw_ratio,
            "league_dev_assist_ratio": dev_global_ratio,
            "relative_assist_ratio": relative,
            "credibility_weight": weight,
            "shrunk_relative_assist_multiplier": shrunk_relative,
        }
    return {
        "development_seasons": list(venue_seasons),
        "year_anchor_season": int(year_anchor_season),
        "development_global_assist_ratio": dev_global_ratio,
        "year_assist_multiplier": year_multiplier,
        "venue_profiles": venue_profiles,
        "excluded_nonhome_or_unknown_games": excluded_nonhome,
    }


def apply_environment(
    player_rows: Sequence[dict[str, Any]],
    game_identity: dict[str, dict[str, Any]],
    prior: dict[str, Any],
) -> list[dict[str, Any]]:
    """Apply year and venue assist environment while leaving primary prediction fixed."""
    year_mult = float(prior.get("year_assist_multiplier", 1.0))
    vp = prior.get("venue_profiles", {})
    out: list[dict[str, Any]] = []
    for r in player_rows:
        z = dict(r)
        meta = game_identity.get(str(r.get("game_id") or ""), {})
        is_home = is_home_location(meta.get("location"))
        venue = str(meta.get("source_home_team") or "") if is_home else ""
        venue_mult = float(vp.get(venue, {}).get("shrunk_relative_assist_multiplier", 1.0)) if venue else 1.0
        pa = float(num(r.get("pred_assist_total"), 0.0) or 0.0)
        pp = float(num(r.get("pred_primary_total"), 0.0) or 0.0)
        year_assist = max(0.0, pa * year_mult)
        env_assist = max(0.0, year_assist * venue_mult)
        z["venue_proxy"] = venue
        z["venue_proxy_applied"] = 1 if venue else 0
        z["h005_year_assist_multiplier"] = year_mult
        z["h005_venue_relative_multiplier"] = venue_mult
        z["h005_year_only_assist"] = year_assist
        z["h005_assist"] = env_assist
        z["h005_primary"] = pp
        z["h005_year_only_xtc"] = pp + year_assist
        z["h005_xtc"] = pp + env_assist
        out.append(z)
    return out


def mae(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> float:
    if not rows:
        raise ValueError("empty rows")
    return fmean(abs(float(r[actual]) - float(r[pred])) for r in rows)


def rmse(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> float:
    if not rows:
        raise ValueError("empty rows")
    return sqrt(fmean((float(r[actual]) - float(r[pred])) ** 2 for r in rows))

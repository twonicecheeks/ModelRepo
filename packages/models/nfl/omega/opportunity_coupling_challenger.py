"""OMEGA 0.3 — H011 opportunity-coupling challenger.

Single mechanism under test:
    xTC = predicted_xTO * predicted_player_snap_share * shrunk_credit_rate_per_opportunity_exposure

An opportunity-exposure unit is a strictly historical approximation:
    realized team tackle-opportunity plays * realized player defensive snap share.

This keeps sportsbook data, settlement rules, special teams, postseason, and the
sealed 2025 OMEGA holdout outside the model.  The approximation is deliberately
transparent: it does not claim exact on-field opportunity participation.
"""
from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import fmean
from typing import Any, Sequence

VERSION = "0.3.0"
LINEAGE = "omega-tackle-v0.3.0-opportunity-coupling-challenger-2026-09-11"
HOLDOUT_SEASON = 2025
RATE_WINDOW = 8
ALPHA_GRID = (10.0, 25.0, 50.0, 100.0, 200.0, 400.0)


def num(v: Any, default: float | None = None) -> float | None:
    if v in (None, ""):
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x else x


def truthy(v: Any) -> bool:
    x = num(v)
    if x is not None:
        return int(x) != 0
    return str(v or "").strip().lower() in {"true", "yes", "y", "t"}


def normalize_pct(v: Any) -> float | None:
    x = num(v)
    if x is None or x < 0:
        return None
    if x > 1.5:
        x /= 100.0
    if x > 1.05:
        return None
    return min(1.0, x)


def as_int(v: Any) -> int:
    x = num(v, 0.0)
    return int(round(float(x or 0.0)))


def canonical_position_group(r: dict[str, Any]) -> str:
    pg = str(r.get("position_group") or "").strip().upper()
    if pg:
        if pg in {"DB", "CB", "S", "SAFETY", "FS", "SS"}: return "DB"
        if pg in {"LB", "ILB", "OLB", "MLB"}: return "LB"
        if pg in {"DL", "DE", "DT", "NT", "EDGE"}: return "DL"
        return pg
    pos = str(r.get("position") or "").strip().upper()
    if pos in {"CB", "S", "FS", "SS", "DB"}: return "DB"
    if pos in {"LB", "ILB", "OLB", "MLB"}: return "LB"
    if pos in {"DE", "DT", "NT", "DL", "EDGE"}: return "DL"
    return pos or "UNK"


def _snap_share(r: dict[str, Any], team_snap_totals: dict[tuple[str, str], float]) -> float | None:
    pct = normalize_pct(r.get("defense_pct"))
    if pct is not None:
        return pct
    snaps = num(r.get("defense_snaps"))
    total = team_snap_totals.get((str(r.get("game_id") or ""), str(r.get("team") or "")))
    if snaps is None or total is None or total <= 0:
        return None
    return max(0.0, min(1.0, float(snaps) / float(total)))


def build_opportunity_player_rows(
    exposure_rows: Sequence[dict[str, Any]],
    team_outcomes: Sequence[dict[str, Any]],
    team_snap_totals: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    """Build strictly lagged player opportunity-rate rows.

    Histories are updated only after an entire week is emitted, so a target game can
    never contribute to its own rate features.  The realized opportunity exposure in
    a historical game is team opportunity plays × player defensive snap share.
    """
    opp_map = {
        (str(r.get("game_id") or ""), str(r.get("defense_team") or "")):
        float(num(r.get("opportunity_plays"), 0.0) or 0.0)
        for r in team_outcomes
    }
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in exposure_rows:
        if not truthy(r.get("eligible_standard_rate_fit")):
            continue
        season = as_int(r.get("season")); week = as_int(r.get("week"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 row entered OMEGA 0.3 opportunity histories")
        if 2016 <= season <= 2024:
            by_week[(season, week)].append(r)

    hist: dict[str, list[dict[str, float]]] = defaultdict(list)
    pos_credits: dict[str, float] = defaultdict(float)
    pos_opp_exp: dict[str, float] = defaultdict(float)
    out: list[dict[str, Any]] = []

    for season, week in sorted(by_week):
        batch = by_week[(season, week)]
        if season >= 2017:
            for r in batch:
                game = str(r.get("game_id") or "")
                team = str(r.get("team") or "")
                pid = str(r.get("player_id") or "")
                if not game or not team or not pid:
                    continue
                actual_team_opp = opp_map.get((game, team))
                actual_share = _snap_share(r, team_snap_totals)
                if actual_team_opp is None or actual_share is None:
                    continue
                pg = canonical_position_group(r)
                ph = hist[pid]
                last8 = ph[-RATE_WINDOW:]
                prior_credits = sum(x["credits"] for x in last8)
                prior_opp_exp = sum(x["opportunity_exposure"] for x in last8)
                pos_rate = pos_credits[pg] / pos_opp_exp[pg] if pos_opp_exp[pg] > 0 else 0.15
                out.append({
                    "game_id": game,
                    "season": season,
                    "week": week,
                    "team": team,
                    "opponent": str(r.get("opponent") or ""),
                    "player_id": pid,
                    "display_name": str(r.get("display_name") or ""),
                    "position": str(r.get("position") or ""),
                    "position_group": pg,
                    "actual_xtc": float(as_int(r.get("combined_standard_def_scrimmage"))),
                    "actual_defensive_snaps": float(num(r.get("defense_snaps"), 0.0) or 0.0),
                    "actual_snap_share": float(actual_share),
                    "actual_team_opportunities": float(actual_team_opp),
                    "actual_opportunity_exposure": float(actual_team_opp) * float(actual_share),
                    "prior_games": len(ph),
                    "prior_last8_credits": float(prior_credits),
                    "prior_last8_opportunity_exposure": float(prior_opp_exp),
                    "position_prior_credit_per_opportunity_exposure": float(pos_rate),
                })
        # update after every row in the target week has been emitted
        for r in batch:
            game = str(r.get("game_id") or "")
            team = str(r.get("team") or "")
            pid = str(r.get("player_id") or "")
            if not game or not team or not pid:
                continue
            actual_team_opp = opp_map.get((game, team))
            actual_share = _snap_share(r, team_snap_totals)
            if actual_team_opp is None or actual_share is None:
                continue
            opp_exp = float(actual_team_opp) * float(actual_share)
            credits = float(as_int(r.get("combined_standard_def_scrimmage")))
            pg = canonical_position_group(r)
            hist[pid].append({"credits": credits, "opportunity_exposure": opp_exp})
            pos_credits[pg] += credits
            pos_opp_exp[pg] += opp_exp
    return out


def score_rows(
    rows: Sequence[dict[str, Any]],
    *,
    alpha: float,
    xto_predictions: dict[tuple[str, str], float],
    exposure_predictions: dict[tuple[str, str, str], float],
    out_key: str = "opportunity_coupled_xtc",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        game = str(r.get("game_id") or "")
        team = str(r.get("team") or "")
        pid = str(r.get("player_id") or "")
        x_to = xto_predictions.get((game, team))
        snap_share = exposure_predictions.get((game, team, pid))
        if x_to is None or snap_share is None:
            continue
        prior_exp = float(r["prior_last8_opportunity_exposure"])
        prior_credits = float(r["prior_last8_credits"])
        prior_rate = float(r["position_prior_credit_per_opportunity_exposure"])
        den = prior_exp + float(alpha)
        rate = (prior_credits + float(alpha) * prior_rate) / den if den > 0 else prior_rate
        pred_exp = max(0.0, float(x_to) * max(0.0, min(1.0, float(snap_share))))
        pred = max(0.0, pred_exp * rate)
        z = dict(r)
        z["predicted_xto"] = float(x_to)
        z["predicted_snap_share"] = float(snap_share)
        z["predicted_opportunity_exposure"] = pred_exp
        z["shrunk_credit_rate_per_opportunity_exposure"] = rate
        z["opportunity_shrinkage_alpha"] = float(alpha)
        z[out_key] = pred
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

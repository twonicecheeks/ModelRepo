"""OMEGA 0.4 — H008 tackle-opportunity-footprint challenger.

Pre-registered mechanism H008 from OMEGA 0.1:
    offensive tackle-opportunity topology (rush, completed pass, scramble, sack,
    rare other-pass) changes which defenders receive official tackle credit.

The challenger keeps H012 exposure and the 0.2 total xTO model frozen. It splits
predicted xTO into strictly-lagged play-family shares, then applies player- and
position-shrunk credit rates per family-opportunity exposure.

No market data, sportsbook settlement convention, postseason, or OMEGA 2025 data
is used here.
"""
from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.4.0"
LINEAGE = "omega-tackle-v0.4.0-h008-tackle-opportunity-footprint-2026-09-11"
HOLDOUT_SEASON = 2025
RATE_WINDOW = 8
TEAM_WINDOW = 8
FAMILIES = ("RUSH", "COMPLETE_PASS", "SCRAMBLE", "SACK", "OTHER_PASS")
ALPHA_GRID = (5.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0)


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


def as_int(v: Any) -> int:
    return int(round(float(num(v, 0.0) or 0.0)))


def normalize_pct(v: Any) -> float | None:
    x = num(v)
    if x is None or x < 0:
        return None
    if x > 1.5:
        x /= 100.0
    if x > 1.05:
        return None
    return min(1.0, x)


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


def aggregate_team_family_opportunities(play_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate standard tackle-opportunity plays by play family and defense game.

    Opportunity = a non-nullified standard family play with at least one original-
    defense tackle credit. This exactly decomposes the 0.2 xTO target across FAMILIES.
    """
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in play_rows:
        season = as_int(r.get("season"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 row entered H008 team-family opportunities")
        if truthy(r.get("is_nullified_or_deleted")):
            continue
        fam = str(r.get("play_family") or "")
        if fam not in FAMILIES:
            continue
        game = str(r.get("game_id") or "")
        off = str(r.get("posteam") or "")
        deff = str(r.get("defteam") or "")
        if not game or not off or not deff:
            continue
        key = (game, off, deff)
        g = groups.setdefault(key, {
            "game_id": game,
            "season": season,
            "week": as_int(r.get("week")),
            "offense_team": off,
            "defense_team": deff,
            "total_opportunity_plays": 0,
            **{f"opp_{f}": 0 for f in FAMILIES},
        })
        if as_int(r.get("original_defense_credit_units")) > 0:
            g["total_opportunity_plays"] += 1
            g[f"opp_{fam}"] += 1
    out = list(groups.values())
    out.sort(key=lambda r: (r["season"], r["week"], r["game_id"], r["defense_team"]))
    return out


def _family_shares(history: Sequence[dict[str, Any]]) -> dict[str, float] | None:
    h = list(history[-TEAM_WINDOW:])
    total = sum(float(r.get("total_opportunity_plays") or 0.0) for r in h)
    if total <= 0:
        return None
    return {f: sum(float(r.get(f"opp_{f}") or 0.0) for r in h) / total for f in FAMILIES}


def build_team_family_share_pregame_rows(outcomes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strictly lagged offense/defense family-share forecasts.

    For each target game, predicted opportunity-family share is the mean of the
    opponent offense's recent generated share and the target defense's recent allowed
    share. Missing sides fall back to the strictly-prior league distribution. Shares
    are normalized to one. All games in a week are emitted before that week updates
    any history.
    """
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in outcomes:
        season = as_int(r.get("season")); week = as_int(r.get("week"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 row entered H008 family-share histories")
        if 2016 <= season <= 2024:
            by_week[(season, week)].append(r)

    off_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    def_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    league_counts = {f: 0.0 for f in FAMILIES}
    league_total = 0.0
    rows: list[dict[str, Any]] = []

    for season, week in sorted(by_week):
        batch = by_week[(season, week)]
        if season >= 2017:
            league_share = {
                f: (league_counts[f] / league_total if league_total > 0 else 1.0 / len(FAMILIES))
                for f in FAMILIES
            }
            for g in batch:
                os = _family_shares(off_hist[str(g.get("offense_team") or "")])
                ds = _family_shares(def_hist[str(g.get("defense_team") or "")])
                raw = {}
                for f in FAMILIES:
                    a = os[f] if os is not None else league_share[f]
                    b = ds[f] if ds is not None else league_share[f]
                    raw[f] = max(0.0, 0.5 * (a + b))
                s = sum(raw.values())
                pred = {f: (raw[f] / s if s > 0 else league_share[f]) for f in FAMILIES}
                row = {
                    "game_id": str(g.get("game_id") or ""),
                    "season": season,
                    "week": week,
                    "offense_team": str(g.get("offense_team") or ""),
                    "defense_team": str(g.get("defense_team") or ""),
                    "actual_total_opportunity_plays": float(g.get("total_opportunity_plays") or 0.0),
                }
                for f in FAMILIES:
                    row[f"pred_share_{f}"] = pred[f]
                    row[f"actual_opp_{f}"] = float(g.get(f"opp_{f}") or 0.0)
                    row[f"actual_share_{f}"] = (
                        float(g.get(f"opp_{f}") or 0.0) / float(g.get("total_opportunity_plays") or 1.0)
                        if float(g.get("total_opportunity_plays") or 0.0) > 0 else 0.0
                    )
                rows.append(row)
        # Update histories only after all target rows for the week were emitted.
        for g in batch:
            off_hist[str(g.get("offense_team") or "")].append(g)
            def_hist[str(g.get("defense_team") or "")].append(g)
            total = float(g.get("total_opportunity_plays") or 0.0)
            league_total += total
            for f in FAMILIES:
                league_counts[f] += float(g.get(f"opp_{f}") or 0.0)
    return rows


def aggregate_player_family_credits(event_rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
    """Standard-defensive player credits by play family from immutable event ledger."""
    out: dict[tuple[str, str], dict[str, float]] = {}
    for e in event_rows:
        season = as_int(e.get("season"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 event row entered H008 family-credit aggregation")
        if not truthy(e.get("is_standard_def_scrimmage_credit")):
            continue
        fam = str(e.get("play_family") or "")
        if fam not in FAMILIES:
            continue
        game = str(e.get("game_id") or "")
        pid = str(e.get("player_id") or "")
        if not game or not pid:
            continue
        g = out.setdefault((game, pid), {f: 0.0 for f in FAMILIES})
        g[fam] += float(num(e.get("combined_credit_unit"), 1.0) or 1.0)
    return out


def build_player_topology_rows(
    exposure_rows: Sequence[dict[str, Any]],
    family_outcomes: Sequence[dict[str, Any]],
    player_family_credits: dict[tuple[str, str], dict[str, float]],
    team_snap_totals: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    """Strictly lagged player family-rate rows with explicit zero outcomes."""
    fam_map = {
        (str(r.get("game_id") or ""), str(r.get("defense_team") or "")): r
        for r in family_outcomes
    }
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in exposure_rows:
        if not truthy(r.get("eligible_standard_rate_fit")):
            continue
        season = as_int(r.get("season")); week = as_int(r.get("week"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 exposure row entered H008 player histories")
        if 2016 <= season <= 2024:
            by_week[(season, week)].append(r)

    hist: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(lambda: defaultdict(list))
    pos_credits: dict[tuple[str, str], float] = defaultdict(float)
    pos_exp: dict[tuple[str, str], float] = defaultdict(float)
    out: list[dict[str, Any]] = []

    for season, week in sorted(by_week):
        batch = by_week[(season, week)]
        if season >= 2017:
            for r in batch:
                game = str(r.get("game_id") or "")
                team = str(r.get("team") or "")
                pid = str(r.get("player_id") or "")
                fg = fam_map.get((game, team))
                share = _snap_share(r, team_snap_totals)
                if not game or not team or not pid or fg is None or share is None:
                    continue
                pg = canonical_position_group(r)
                actual_fc = player_family_credits.get((game, pid), {f: 0.0 for f in FAMILIES})
                row: dict[str, Any] = {
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
                    "actual_snap_share": float(share),
                    "actual_defensive_snaps": float(num(r.get("defense_snaps"), 0.0) or 0.0),
                    "prior_games": max((len(hist[pid][f]) for f in FAMILIES), default=0),
                }
                actual_family_sum = 0.0
                for f in FAMILIES:
                    fh = hist[pid][f][-RATE_WINDOW:]
                    prior_c = sum(x["credits"] for x in fh)
                    prior_e = sum(x["exposure"] for x in fh)
                    pr = pos_credits[(pg, f)] / pos_exp[(pg, f)] if pos_exp[(pg, f)] > 0 else 0.15
                    actual_opp = float(fg.get(f"opp_{f}") or 0.0)
                    actual_c = float(actual_fc.get(f, 0.0))
                    actual_family_sum += actual_c
                    row[f"prior_last8_credits_{f}"] = prior_c
                    row[f"prior_last8_exposure_{f}"] = prior_e
                    row[f"position_prior_rate_{f}"] = pr
                    row[f"actual_team_opp_{f}"] = actual_opp
                    row[f"actual_credit_{f}"] = actual_c
                row["actual_family_credit_sum"] = actual_family_sum
                out.append(row)
        # Update only after full week emitted.
        for r in batch:
            game = str(r.get("game_id") or "")
            team = str(r.get("team") or "")
            pid = str(r.get("player_id") or "")
            fg = fam_map.get((game, team))
            share = _snap_share(r, team_snap_totals)
            if not game or not team or not pid or fg is None or share is None:
                continue
            pg = canonical_position_group(r)
            actual_fc = player_family_credits.get((game, pid), {f: 0.0 for f in FAMILIES})
            for f in FAMILIES:
                exp = float(fg.get(f"opp_{f}") or 0.0) * float(share)
                cr = float(actual_fc.get(f, 0.0))
                hist[pid][f].append({"credits": cr, "exposure": exp})
                pos_credits[(pg, f)] += cr
                pos_exp[(pg, f)] += exp
    return out


def score_rows(
    rows: Sequence[dict[str, Any]],
    *,
    alpha: float,
    xto_predictions: dict[tuple[str, str], float],
    exposure_predictions: dict[tuple[str, str, str], float],
    family_share_predictions: dict[tuple[str, str], dict[str, float]],
    out_key: str = "topology_xtc",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        game = str(r.get("game_id") or "")
        team = str(r.get("team") or "")
        pid = str(r.get("player_id") or "")
        x_to = xto_predictions.get((game, team))
        snap_share = exposure_predictions.get((game, team, pid))
        shares = family_share_predictions.get((game, team))
        if x_to is None or snap_share is None or not shares:
            continue
        ss = max(0.0, min(1.0, float(snap_share)))
        total_pred = 0.0
        z = dict(r)
        z["predicted_xto"] = float(x_to)
        z["predicted_snap_share"] = ss
        for f in FAMILIES:
            sh = max(0.0, float(shares.get(f, 0.0)))
            pred_opp = max(0.0, float(x_to) * sh)
            prior_e = float(r[f"prior_last8_exposure_{f}"])
            prior_c = float(r[f"prior_last8_credits_{f}"])
            prior_rate = float(r[f"position_prior_rate_{f}"])
            den = prior_e + float(alpha)
            rate = (prior_c + float(alpha) * prior_rate) / den if den > 0 else prior_rate
            contribution = pred_opp * ss * rate
            z[f"pred_share_{f}"] = sh
            z[f"pred_opp_{f}"] = pred_opp
            z[f"shrunk_rate_{f}"] = rate
            z[f"pred_credit_{f}"] = contribution
            total_pred += contribution
        z["topology_shrinkage_alpha"] = float(alpha)
        z[out_key] = max(0.0, total_pred)
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

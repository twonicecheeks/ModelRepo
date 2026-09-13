"""OMEGA 0.5 — H002 tackle-funnel rigidity / allocation challenger.

Pre-registered mechanism H002 from OMEGA 0.1:
    some defenses allocate tackle credit to a stable set of players across opponents.

This module tests whether a strictly-lagged, role-adjusted share of a defense's
expected tackle-credit mass adds predictive value beyond frozen OMEGA 0.4 H008.
It intentionally does NOT normalize over the target game's realized participant
set; doing so would leak who actually played in the target game.

No market data, sportsbook settlement convention, postseason, or OMEGA 2025 data
is used here.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.5.0"
LINEAGE = "omega-tackle-v0.5.0-h002-funnel-rigidity-allocation-2026-09-11"
HOLDOUT_SEASON = 2025
WINDOW = 8
CONFIDENCE_GAMES = 4
LAMBDA_GRID = (0.0, 0.25, 0.50, 0.75, 1.0)
FAMILIES = ("RUSH", "COMPLETE_PASS", "SCRAMBLE", "SACK", "OTHER_PASS")


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


def total_variation_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Similarity of two player-credit-share vectors in [0,1]."""
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    l1 = sum(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0))) for k in keys)
    return max(0.0, min(1.0, 1.0 - 0.5 * l1))


def aggregate_team_player_credit_distributions(
    event_rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Exact standard-defensive credit distribution by game/team from event ledger."""
    tmp: dict[tuple[str, str], dict[str, Any]] = {}
    for e in event_rows:
        season = as_int(e.get("season"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 event row entered H002 credit distributions")
        if not truthy(e.get("is_standard_def_scrimmage_credit")):
            continue
        game = str(e.get("game_id") or "")
        team = str(e.get("credit_team") or "")
        pid = str(e.get("player_id") or "")
        if not game or not team or not pid:
            continue
        key = (game, team)
        g = tmp.setdefault(key, {
            "game_id": game,
            "team": team,
            "season": season,
            "week": as_int(e.get("week")),
            "total_credits": 0.0,
            "player_credits": defaultdict(float),
            "family_credits": defaultdict(float),
        })
        c = float(num(e.get("combined_credit_unit"), 1.0) or 1.0)
        g["total_credits"] += c
        g["player_credits"][pid] += c
        fam = str(e.get("play_family") or "")
        if fam in FAMILIES:
            g["family_credits"][fam] += c
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for k, g in tmp.items():
        total = float(g["total_credits"])
        shares = {pid: c / total for pid, c in g["player_credits"].items()} if total > 0 else {}
        out[k] = {
            **{kk: vv for kk, vv in g.items() if kk not in {"player_credits", "family_credits"}},
            "player_credits": dict(g["player_credits"]),
            "player_shares": shares,
            "family_credits": dict(g["family_credits"]),
        }
    return out


def aggregate_team_family_opportunities(
    play_rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, float]]:
    """Opportunity counts by family for the exact 0.4 standard-opportunity universe."""
    out: dict[tuple[str, str], dict[str, float]] = {}
    for r in play_rows:
        season = as_int(r.get("season"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 play row entered H002 opportunity aggregation")
        if truthy(r.get("is_nullified_or_deleted")):
            continue
        fam = str(r.get("play_family") or "")
        if fam not in FAMILIES:
            continue
        game = str(r.get("game_id") or "")
        team = str(r.get("defteam") or "")
        if not game or not team:
            continue
        if as_int(r.get("original_defense_credit_units")) <= 0:
            continue
        g = out.setdefault((game, team), {f: 0.0 for f in FAMILIES})
        g[fam] += 1.0
    return out


def _snap_share(r: dict[str, Any], team_snap_totals: dict[tuple[str, str], float]) -> float | None:
    pct = normalize_pct(r.get("defense_pct"))
    if pct is not None:
        return pct
    snaps = num(r.get("defense_snaps"))
    total = team_snap_totals.get((str(r.get("game_id") or ""), str(r.get("team") or "")))
    if snaps is None or total is None or total <= 0:
        return None
    return max(0.0, min(1.0, float(snaps) / float(total)))


def build_funnel_pregame_rows(
    exposure_rows: Sequence[dict[str, Any]],
    event_rows: Sequence[dict[str, Any]],
    play_rows: Sequence[dict[str, Any]],
    team_snap_totals: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    """Build strictly-lagged H002 allocation features.

    Features are emitted before target-week outcomes update history. No target-game
    participant-set normalization is performed.
    """
    dist = aggregate_team_player_credit_distributions(event_rows)
    opp = aggregate_team_family_opportunities(play_rows)

    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in exposure_rows:
        if not truthy(r.get("eligible_standard_rate_fit")):
            continue
        season = as_int(r.get("season")); week = as_int(r.get("week"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 exposure row entered H002 histories")
        if 2016 <= season <= 2024:
            by_week[(season, week)].append(r)

    # Team distribution history for rigidity.
    team_dist_hist: dict[str, list[dict[str, float]]] = defaultdict(list)
    # Player appearance history: actual player credits, exact team credit mass, snap share.
    player_hist: dict[tuple[str, str], list[dict[str, float]]] = defaultdict(list)
    # Strictly-prior league family credits/opportunities for a neutral team-credit scale anchor.
    league_family_credits = {f: 0.0 for f in FAMILIES}
    league_family_opps = {f: 0.0 for f in FAMILIES}

    rows: list[dict[str, Any]] = []

    for season, week in sorted(by_week):
        batch = by_week[(season, week)]
        if season >= 2017:
            for r in batch:
                game = str(r.get("game_id") or "")
                team = str(r.get("team") or "")
                pid = str(r.get("player_id") or "")
                if not game or not team or not pid:
                    continue
                actual_share = _snap_share(r, team_snap_totals)
                if actual_share is None:
                    continue

                dh = team_dist_hist[team][-WINDOW:]
                sims = [total_variation_similarity(dh[i-1], dh[i]) for i in range(1, len(dh))]
                rigidity = fmean(sims) if sims else 0.0

                ph = player_hist[(team, pid)][-WINDOW:]
                prior_games = len(ph)
                prior_player_credits = sum(x["player_credits"] for x in ph)
                prior_team_credits = sum(x["team_credits"] for x in ph)
                prior_credit_share = prior_player_credits / prior_team_credits if prior_team_credits > 0 else 0.0
                prior_snap_share = fmean(x["snap_share"] for x in ph) if ph else 0.0
                confidence = min(1.0, prior_games / float(CONFIDENCE_GAMES))

                row: dict[str, Any] = {
                    "game_id": game,
                    "season": season,
                    "week": week,
                    "team": team,
                    "opponent": str(r.get("opponent") or ""),
                    "player_id": pid,
                    "display_name": str(r.get("display_name") or ""),
                    "position": str(r.get("position") or ""),
                    "position_group": str(r.get("position_group") or ""),
                    "actual_xtc": float(as_int(r.get("combined_standard_def_scrimmage"))),
                    "actual_snap_share": float(actual_share),
                    "prior_games": prior_games,
                    "prior_credit_share": prior_credit_share,
                    "prior_mean_snap_share": prior_snap_share,
                    "history_confidence": confidence,
                    "team_funnel_rigidity": rigidity,
                }
                for f in FAMILIES:
                    row[f"league_credit_per_opp_{f}"] = (
                        league_family_credits[f] / league_family_opps[f]
                        if league_family_opps[f] > 0 else 1.0
                    )
                rows.append(row)

        # Update only after the whole week was emitted.
        seen_team_games: set[tuple[str, str]] = set()
        for r in batch:
            game = str(r.get("game_id") or "")
            team = str(r.get("team") or "")
            pid = str(r.get("player_id") or "")
            if not game or not team or not pid:
                continue
            share = _snap_share(r, team_snap_totals)
            dg = dist.get((game, team))
            if share is not None and dg is not None:
                pc = float(dg["player_credits"].get(pid, 0.0))
                tc = float(dg["total_credits"])
                player_hist[(team, pid)].append({"player_credits": pc, "team_credits": tc, "snap_share": float(share)})
            key = (game, team)
            if key not in seen_team_games:
                seen_team_games.add(key)
                if dg is not None:
                    team_dist_hist[team].append(dict(dg["player_shares"]))
                    og = opp.get(key, {})
                    for f in FAMILIES:
                        league_family_credits[f] += float(dg["family_credits"].get(f, 0.0))
                        league_family_opps[f] += float(og.get(f, 0.0))
    return rows


def allocation_prediction(
    feature_row: dict[str, Any],
    topology_row: dict[str, Any],
) -> dict[str, float]:
    """Compute role-adjusted lagged allocation prediction without target roster normalization."""
    pred_snap = max(0.0, min(1.0, float(num(topology_row.get("predicted_snap_share"), 0.0) or 0.0)))
    prior_snap = float(num(feature_row.get("prior_mean_snap_share"), 0.0) or 0.0)
    prior_share = max(0.0, float(num(feature_row.get("prior_credit_share"), 0.0) or 0.0))
    if prior_snap > 1e-9:
        role_adjusted_share = prior_share * (pred_snap / prior_snap)
    else:
        role_adjusted_share = 0.0
    # A single player cannot own more than all expected team credit mass.
    role_adjusted_share = max(0.0, min(1.0, role_adjusted_share))

    pred_team_credits = 0.0
    for f in FAMILIES:
        pred_opp = max(0.0, float(num(topology_row.get(f"pred_opp_{f}"), 0.0) or 0.0))
        league_rate = max(0.0, float(num(feature_row.get(f"league_credit_per_opp_{f}"), 1.0) or 1.0))
        pred_team_credits += pred_opp * league_rate
    alloc_xtc = pred_team_credits * role_adjusted_share
    return {
        "predicted_team_credit_mass": pred_team_credits,
        "role_adjusted_credit_share": role_adjusted_share,
        "allocation_xtc": alloc_xtc,
    }


def score_rows(
    topology_rows: Sequence[dict[str, Any]],
    funnel_features: dict[tuple[str, str, str], dict[str, Any]],
    *,
    lam: float,
    out_key: str = "funnel_xtc",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tr in topology_rows:
        key = (str(tr.get("game_id") or ""), str(tr.get("team") or ""), str(tr.get("player_id") or ""))
        fr = funnel_features.get(key)
        if fr is None:
            continue
        ap = allocation_prediction(fr, tr)
        rigidity = max(0.0, min(1.0, float(num(fr.get("team_funnel_rigidity"), 0.0) or 0.0)))
        conf = max(0.0, min(1.0, float(num(fr.get("history_confidence"), 0.0) or 0.0)))
        weight = max(0.0, min(1.0, float(lam) * rigidity * conf))
        base = max(0.0, float(num(tr.get("topology_xtc"), 0.0) or 0.0))
        pred = (1.0 - weight) * base + weight * ap["allocation_xtc"]
        z = dict(tr)
        for k, v in fr.items():
            if k not in z:
                z[k] = v
        z.update(ap)
        z["funnel_lambda"] = float(lam)
        z["funnel_effective_weight"] = weight
        z[out_key] = max(0.0, pred)
        out.append(z)
    return out


def mae(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> float:
    return fmean(abs(float(num(r.get(actual), 0.0) or 0.0) - float(num(r.get(pred), 0.0) or 0.0)) for r in rows) if rows else 0.0


def rmse(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> float:
    if not rows:
        return 0.0
    return (fmean((float(num(r.get(actual), 0.0) or 0.0) - float(num(r.get(pred), 0.0) or 0.0)) ** 2 for r in rows)) ** 0.5

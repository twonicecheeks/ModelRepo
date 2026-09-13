"""OMEGA 0.10 — H009 game-script elasticity challenger.

Pre-registered H009 from the OMEGA 0.1 registry:
    score state changes offensive play mix and defensive personnel, so tackle
    opportunity composition can be nonlinear in projected game script.

This challenger does not use sportsbook spread/total information. It builds a
strictly-lagged, football-data-only score-state mixture from prior opportunity
plays, then asks whether that state-conditioned mixture improves the frozen H008
family-share forecast. beta=0 is an exact null that collapses to H008.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.10.0"
LINEAGE = "omega-tackle-v0.10.0-h009-game-script-elasticity-2026-09-11"
HOLDOUT_SEASON = 2025
TEAM_WINDOW = 8
STATES = ("TRAILING_7P", "NEUTRAL", "LEADING_7P")
FAMILIES = ("RUSH", "COMPLETE_PASS", "SCRAMBLE", "SACK", "OTHER_PASS")
BETA_GRID = (0.0, 0.25, 0.50, 0.75, 1.0)


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


def score_state(score_differential: Any) -> str:
    """Offense-perspective pre-play score state."""
    d = float(num(score_differential, 0.0) or 0.0)
    if d <= -7.0:
        return "TRAILING_7P"
    if d >= 7.0:
        return "LEADING_7P"
    return "NEUTRAL"


def aggregate_state_family_opportunities(play_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Game/team opportunity counts by score-state and H008 family.

    An opportunity is exactly the H008 target: a non-nullified standard-family
    play with >=1 original-defense tackle credit. Score state is read before the
    play from the offense's perspective.
    """
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in play_rows:
        season = as_int(r.get("season"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 row entered H009 state-family aggregation")
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
            **{f"opp_state_{s}": 0 for s in STATES},
            **{f"opp_{s}_{f}": 0 for s in STATES for f in FAMILIES},
        })
        if as_int(r.get("original_defense_credit_units")) <= 0:
            continue
        state = score_state(r.get("score_differential"))
        g["total_opportunity_plays"] += 1
        g[f"opp_state_{state}"] += 1
        g[f"opp_{state}_{fam}"] += 1
    out = list(groups.values())
    out.sort(key=lambda r: (r["season"], r["week"], r["game_id"], r["defense_team"]))
    return out


def _recent_state_counts(history: Sequence[dict[str, Any]]) -> tuple[dict[str, float], float]:
    h = list(history[-TEAM_WINDOW:])
    counts = {s: sum(float(r.get(f"opp_state_{s}") or 0.0) for r in h) for s in STATES}
    total = sum(counts.values())
    return counts, total


def _recent_state_family_counts(history: Sequence[dict[str, Any]], state: str) -> tuple[dict[str, float], float]:
    h = list(history[-TEAM_WINDOW:])
    counts = {f: sum(float(r.get(f"opp_{state}_{f}") or 0.0) for r in h) for f in FAMILIES}
    total = sum(counts.values())
    return counts, total


def _normalized(raw: dict[str, float], fallback: dict[str, float]) -> dict[str, float]:
    vals = {k: max(0.0, float(v)) for k, v in raw.items()}
    s = sum(vals.values())
    if s > 0:
        return {k: v / s for k, v in vals.items()}
    fs = sum(max(0.0, float(v)) for v in fallback.values())
    if fs > 0:
        return {k: max(0.0, float(fallback[k])) / fs for k in fallback}
    return {k: 1.0 / len(raw) for k in raw}


def build_script_family_pregame_rows(outcomes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build strictly-lagged predicted score-state and family mixtures.

    State share = normalized mean of recent offense-generated and defense-allowed
    opportunity-state distributions, falling back to strictly-prior league state
    shares. Within each state, family share is the analogous offense/defense mean.
    The final script family share is the mixture over predicted score states.
    """
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in outcomes:
        season = as_int(r.get("season")); week = as_int(r.get("week"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 row entered H009 pregame histories")
        if 2016 <= season <= 2024:
            by_week[(season, week)].append(r)

    off_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    def_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    league_state = {s: 0.0 for s in STATES}
    league_sf = {(s, f): 0.0 for s in STATES for f in FAMILIES}
    rows: list[dict[str, Any]] = []

    for season, week in sorted(by_week):
        batch = by_week[(season, week)]
        if season >= 2017:
            league_state_total = sum(league_state.values())
            league_state_share = {
                s: league_state[s] / league_state_total if league_state_total > 0 else 1.0 / len(STATES)
                for s in STATES
            }
            league_family_by_state: dict[str, dict[str, float]] = {}
            for s in STATES:
                tot = sum(league_sf[(s, f)] for f in FAMILIES)
                league_family_by_state[s] = {
                    f: league_sf[(s, f)] / tot if tot > 0 else 1.0 / len(FAMILIES)
                    for f in FAMILIES
                }

            for g in batch:
                off = str(g.get("offense_team") or "")
                deff = str(g.get("defense_team") or "")
                oc, ot = _recent_state_counts(off_hist[off])
                dc, dt = _recent_state_counts(def_hist[deff])
                state_raw: dict[str, float] = {}
                for s in STATES:
                    a = oc[s] / ot if ot > 0 else league_state_share[s]
                    b = dc[s] / dt if dt > 0 else league_state_share[s]
                    state_raw[s] = 0.5 * (a + b)
                pred_state = _normalized(state_raw, league_state_share)

                pred_family_state: dict[str, dict[str, float]] = {}
                for s in STATES:
                    ofc, oft = _recent_state_family_counts(off_hist[off], s)
                    dfc, dft = _recent_state_family_counts(def_hist[deff], s)
                    raw: dict[str, float] = {}
                    for f in FAMILIES:
                        a = ofc[f] / oft if oft > 0 else league_family_by_state[s][f]
                        b = dfc[f] / dft if dft > 0 else league_family_by_state[s][f]
                        raw[f] = 0.5 * (a + b)
                    pred_family_state[s] = _normalized(raw, league_family_by_state[s])

                script_family_raw = {
                    f: sum(pred_state[s] * pred_family_state[s][f] for s in STATES)
                    for f in FAMILIES
                }
                script_family = _normalized(script_family_raw, {f: 1.0 / len(FAMILIES) for f in FAMILIES})
                actual_total = float(g.get("total_opportunity_plays") or 0.0)
                row: dict[str, Any] = {
                    "game_id": str(g.get("game_id") or ""),
                    "season": season,
                    "week": week,
                    "offense_team": off,
                    "defense_team": deff,
                    "actual_total_opportunity_plays": actual_total,
                }
                for s in STATES:
                    row[f"pred_state_share_{s}"] = pred_state[s]
                    row[f"actual_state_share_{s}"] = (float(g.get(f"opp_state_{s}") or 0.0) / actual_total) if actual_total > 0 else 0.0
                    for f in FAMILIES:
                        row[f"pred_family_share_{s}_{f}"] = pred_family_state[s][f]
                for f in FAMILIES:
                    actual_f = sum(float(g.get(f"opp_{s}_{f}") or 0.0) for s in STATES)
                    row[f"script_share_{f}"] = script_family[f]
                    row[f"actual_family_share_{f}"] = actual_f / actual_total if actual_total > 0 else 0.0
                rows.append(row)
        # Update only after all target rows for the week are emitted.
        for g in batch:
            off_hist[str(g.get("offense_team") or "")].append(g)
            def_hist[str(g.get("defense_team") or "")].append(g)
            for s in STATES:
                c = float(g.get(f"opp_state_{s}") or 0.0)
                league_state[s] += c
                for f in FAMILIES:
                    league_sf[(s, f)] += float(g.get(f"opp_{s}_{f}") or 0.0)
    return rows


def blend_family_shares(
    h008: dict[str, float],
    script: dict[str, float],
    beta: float,
) -> dict[str, float]:
    b = max(0.0, min(1.0, float(beta)))
    raw = {f: (1.0 - b) * max(0.0, float(h008.get(f, 0.0))) + b * max(0.0, float(script.get(f, 0.0))) for f in FAMILIES}
    return _normalized(raw, h008)


def family_share_l1(rows: Sequence[dict[str, Any]], prefix: str) -> float:
    if not rows:
        return 0.0
    vals = []
    for r in rows:
        vals.append(sum(abs(float(r.get(f"actual_family_share_{f}") or 0.0) - float(r.get(f"{prefix}_{f}") or 0.0)) for f in FAMILIES))
    return fmean(vals)

"""NFL State Intelligence 0.1.3 — state-component persistence research.

Development-only, coefficient-free follow-up to the DEN@KC M04/M05/M06/M19
mechanism work. The 0.1.2 interaction audit showed that structural exposure itself
was strong, while a defense tier built from broad lagged sack rate did not show a
stable interaction. This module asks a more basic pregame question before any
feature promotion:

1. Is an offense's tendency to reach elevated/high third-down states persistent
   from prior same-season weeks into its next game?
2. Is a defense's sack conversion specifically on elevated/high third-down
   dropbacks persistent into its next game?

All pregame states use week < target week only. Same-week games are excluded from
history. 2025 remains sealed and 2026 is prospective-only.
"""
from __future__ import annotations

from collections import defaultdict
import random
from typing import Any, Iterable

VERSION = "0.1.3"
LINEAGE = "nfl-state-component-persistence-v0.1.3-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

SCRIMMAGE_INTENTS = {"DESIGNED_PASS", "DESIGNED_RUN", "DROPBACK_SCRAMBLE", "DROPBACK_SACK"}
DROPBACK_INTENTS = {"DESIGNED_PASS", "DROPBACK_SCRAMBLE", "DROPBACK_SACK"}
EXPOSED_BUCKETS = {"ELEVATED_STRUCTURAL_EXPOSURE", "HIGH_STRUCTURAL_EXPOSURE"}
TIERS = ("LOW", "MID", "HIGH")


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


def _feat(row: dict[str, Any]) -> dict[str, Any]:
    v = row.get("state_intelligence")
    return v if isinstance(v, dict) else {}


def _eligible_third_down(row: dict[str, Any]) -> bool:
    feat = _feat(row)
    return bool(
        feat.get("football_tendency_eligible")
        and feat.get("competitive_state") == "COMPETITIVE"
        and feat.get("play_intent") in SCRIMMAGE_INTENTS
        and _num(row.get("down")) == 3
    )


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def _empty_counts() -> dict[str, float]:
    return {
        "third_downs": 0.0,
        "exposed_third_downs": 0.0,
        "dropbacks": 0.0,
        "sacks": 0.0,
        "conversions": 0.0,
        "exposed_dropbacks": 0.0,
        "exposed_sacks": 0.0,
    }


def _add_snap(c: dict[str, float], row: dict[str, Any]) -> None:
    feat = _feat(row)
    intent = str(feat.get("play_intent") or "")
    pressure = str(feat.get("pressure_opportunity_bucket") or "")
    exposed = pressure in EXPOSED_BUCKETS
    dropback = intent in DROPBACK_INTENTS
    sack = intent == "DROPBACK_SACK"

    c["third_downs"] += 1
    if exposed:
        c["exposed_third_downs"] += 1
    if dropback:
        c["dropbacks"] += 1
    if sack:
        c["sacks"] += 1
    if _flag(row, "first_down"):
        c["conversions"] += 1
    if exposed and dropback:
        c["exposed_dropbacks"] += 1
    if exposed and sack:
        c["exposed_sacks"] += 1


def _add_counts(dst: dict[str, float], src: dict[str, float]) -> None:
    for k in dst:
        dst[k] += float(src.get(k, 0.0))


def _rates(c: dict[str, float]) -> dict[str, Any]:
    td = c["third_downs"]
    db = c["dropbacks"]
    edb = c["exposed_dropbacks"]
    return {
        **{k: int(v) for k, v in c.items()},
        "exposure_rate": c["exposed_third_downs"] / td if td else None,
        "third_down_dropback_rate": db / td if td else None,
        "third_down_sack_rate": c["sacks"] / db if db else None,
        "third_down_conversion_rate": c["conversions"] / td if td else None,
        "exposed_sack_rate": c["exposed_sacks"] / edb if edb else None,
    }


def _assign_terciles(values: dict[str, tuple[float, int]]) -> dict[str, dict[str, Any]]:
    """Cross-sectional LOW/MID/HIGH tiers with no fitted coefficients."""
    if len(values) < 3:
        return {}
    rates = [rate for rate, _n in values.values()]
    q1 = _percentile(rates, 1 / 3)
    q2 = _percentile(rates, 2 / 3)
    if q1 is None or q2 is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for team, (rate, n) in values.items():
        tier = "LOW" if rate <= q1 else ("HIGH" if rate >= q2 else "MID")
        out[team] = {"tier": tier, "rate": rate, "prior_n": n, "q1": q1, "q2": q2}
    return out


def _game_team_counts(rows: Iterable[dict[str, Any]]) -> dict[tuple[int, int, str, str], dict[str, float]]:
    """Return target-game third-down counts keyed by season/week/game/posteam."""
    out: dict[tuple[int, int, str, str], dict[str, float]] = defaultdict(_empty_counts)
    for raw in rows:
        row = dict(raw)
        if not _eligible_third_down(row):
            continue
        season = int(_num(row.get("season")) or 0)
        week = int(_num(row.get("week")) or 0)
        game_id = str(row.get("game_id") or "")
        offense = str(row.get("posteam") or "").upper()
        if season <= 0 or week <= 0 or not game_id or not offense:
            continue
        _add_snap(out[(season, week, game_id, offense)], row)
    return dict(out)


def build_persistence_records(
    rows: Iterable[dict[str, Any]], *, min_prior_third_downs: int = 20,
    min_prior_exposed_dropbacks: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Build next-game records from strictly lagged same-season component states.

    Offensive tier = prior elevated/high third-down share.
    Defensive tier = prior sack rate on elevated/high third-down dropbacks.
    Histories are updated only after every game in a target week has been scored.
    """
    rows = [dict(r) for r in rows]
    team_games = _game_team_counts(rows)
    game_defense: dict[tuple[int, int, str, str], str] = {}
    for row in rows:
        if not _eligible_third_down(row):
            continue
        season = int(_num(row.get("season")) or 0)
        week = int(_num(row.get("week")) or 0)
        game_id = str(row.get("game_id") or "")
        offense = str(row.get("posteam") or "").upper()
        defense = str(row.get("defteam") or "").upper()
        if season and week and game_id and offense and defense:
            game_defense[(season, week, game_id, offense)] = defense

    offense_records: list[dict[str, Any]] = []
    defense_records: list[dict[str, Any]] = []
    seasons = sorted({k[0] for k in team_games})

    for season in seasons:
        off_hist: dict[str, dict[str, float]] = defaultdict(_empty_counts)
        def_hist: dict[str, dict[str, float]] = defaultdict(_empty_counts)
        weeks = sorted({k[1] for k in team_games if k[0] == season})

        for week in weeks:
            off_values: dict[str, tuple[float, int]] = {}
            for team, c in off_hist.items():
                td = int(c["third_downs"])
                if td >= min_prior_third_downs:
                    off_values[team] = (c["exposed_third_downs"] / td, td)
            off_tiers = _assign_terciles(off_values)

            def_values: dict[str, tuple[float, int]] = {}
            for team, c in def_hist.items():
                edb = int(c["exposed_dropbacks"])
                if edb >= min_prior_exposed_dropbacks:
                    def_values[team] = (c["exposed_sacks"] / edb, edb)
            def_tiers = _assign_terciles(def_values)

            week_keys = sorted(k for k in team_games if k[0] == season and k[1] == week)
            for key in week_keys:
                _season, _week, game_id, offense = key
                defense = game_defense.get(key)
                target = _rates(team_games[key])

                off_info = off_tiers.get(offense)
                if off_info:
                    offense_records.append({
                        "game_id": game_id,
                        "season": season,
                        "week": week,
                        "team": offense,
                        "opponent": defense,
                        "pregame_tier": off_info["tier"],
                        "pregame_exposure_rate": off_info["rate"],
                        "prior_third_downs": off_info["prior_n"],
                        **{f"target_{k}": v for k, v in target.items()},
                    })

                if defense:
                    def_info = def_tiers.get(defense)
                    if def_info:
                        defense_records.append({
                            "game_id": game_id,
                            "season": season,
                            "week": week,
                            "team": defense,
                            "opponent": offense,
                            "pregame_tier": def_info["tier"],
                            "pregame_exposed_sack_rate": def_info["rate"],
                            "prior_exposed_dropbacks": def_info["prior_n"],
                            **{f"target_{k}": v for k, v in target.items()},
                        })

            # Strict week boundary: update histories only after every Week-N game
            # has been evaluated with Week < N information.
            for key in week_keys:
                _season, _week, _game_id, offense = key
                defense = game_defense.get(key)
                counts = team_games[key]
                _add_counts(off_hist[offense], counts)
                if defense:
                    # The target offense's observed dropbacks are the opponent
                    # defense's opportunities faced.
                    _add_counts(def_hist[defense], counts)

    return {"offense": offense_records, "defense": defense_records}


def _weighted_group_summary(records: Iterable[dict[str, Any]], *, mode: str) -> dict[str, Any]:
    groups: dict[str, dict[str, float]] = {tier: _empty_counts() for tier in TIERS}
    games: dict[str, int] = {tier: 0 for tier in TIERS}
    for r in records:
        tier = str(r.get("pregame_tier") or "")
        if tier not in groups:
            continue
        games[tier] += 1
        for k in groups[tier]:
            groups[tier][k] += float(r.get(f"target_{k}") or 0)
    out = {tier: {"games": games[tier], **_rates(groups[tier])} for tier in TIERS}
    metric = "exposure_rate" if mode == "offense" else "exposed_sack_rate"
    low, high = out["LOW"].get(metric), out["HIGH"].get(metric)
    high_low = None if low is None or high is None else high - low
    return {"groups": out, "primary_metric": metric, "high_minus_low": high_low}


def summarize_persistence(records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    offense = _weighted_group_summary(records["offense"], mode="offense")
    defense = _weighted_group_summary(records["defense"], mode="defense")

    by_season: dict[str, Any] = {}
    seasons = sorted({int(r["season"]) for r in records["offense"] + records["defense"]})
    for season in seasons:
        off = [r for r in records["offense"] if int(r["season"]) == season]
        deff = [r for r in records["defense"] if int(r["season"]) == season]
        by_season[str(season)] = {
            "offense": _weighted_group_summary(off, mode="offense"),
            "defense": _weighted_group_summary(deff, mode="defense"),
        }
    return {"offense": offense, "defense": defense, "by_season": by_season}


def _bootstrap_high_low(
    records: list[dict[str, Any]], *, mode: str, reps: int, seed: int
) -> dict[str, Any]:
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if r.get("game_id"):
            by_game[str(r["game_id"])].append(r)
    game_ids = sorted(by_game)
    if len(game_ids) < 2:
        raise ValueError("component persistence bootstrap requires at least two games")
    if reps < 100:
        raise ValueError("bootstrap reps must be >= 100")
    observed = _weighted_group_summary(records, mode=mode)["high_minus_low"]
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(reps):
        sampled: list[dict[str, Any]] = []
        for _j in range(len(game_ids)):
            sampled.extend(by_game[rng.choice(game_ids)])
        value = _weighted_group_summary(sampled, mode=mode)["high_minus_low"]
        if value is not None:
            draws.append(value)
    return {
        "cluster": "game_id",
        "reps": reps,
        "seed": seed,
        "observed": observed,
        "ci95_low": _percentile(draws, 0.025),
        "ci95_high": _percentile(draws, 0.975),
    }


def cluster_bootstrap_persistence(
    records: dict[str, list[dict[str, Any]]], *, reps: int = 1000, seed: int = 20260916
) -> dict[str, Any]:
    return {
        "offense_exposure_high_minus_low": _bootstrap_high_low(
            records["offense"], mode="offense", reps=reps, seed=seed
        ),
        "defense_exposed_sack_high_minus_low": _bootstrap_high_low(
            records["defense"], mode="defense", reps=reps, seed=seed + 1
        ),
    }


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    seasons = tuple(sorted({int(s) for s in seasons}))
    if not seasons:
        raise ValueError("at least one development season is required")
    forbidden = [s for s in seasons if s >= SEALED_HOLDOUT_SEASON]
    if forbidden:
        raise ValueError(
            "component persistence discovery is development-only; sealed 2025 holdout and 2026 prospective data are forbidden: "
            + ",".join(map(str, forbidden))
        )
    return seasons

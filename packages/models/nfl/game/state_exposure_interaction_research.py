"""NFL State Intelligence 0.1.2 — exposure x opponent pass-rush research.

Development-only, coefficient-free diagnostic for DEN@KC M05/M06/M07/M19:
structural down-distance exposure should determine how strongly an opponent's
pass-rush ability can express itself.

The opponent pass-rush state is strictly lagged within season (week < target
week). 2025 remains sealed and 2026 prospective data is forbidden.
"""
from __future__ import annotations

from collections import defaultdict
import random
from typing import Any, Iterable

VERSION = "0.1.2"
LINEAGE = "nfl-state-exposure-passrush-interaction-v0.1.2-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

DROPBACK_INTENTS = {"DESIGNED_PASS", "DROPBACK_SCRAMBLE", "DROPBACK_SACK"}
EXPOSURE_MAP = {
    "BASE_STRUCTURAL_EXPOSURE": "BASE",
    "ELEVATED_STRUCTURAL_EXPOSURE": "ELEVATED_PLUS",
    "HIGH_STRUCTURAL_EXPOSURE": "ELEVATED_PLUS",
}
PRESSURE_TIERS = ("LOW", "MID", "HIGH")


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
    value = row.get("state_intelligence")
    return value if isinstance(value, dict) else {}


def _eligible_competitive_dropback(row: dict[str, Any]) -> bool:
    feat = _feat(row)
    return bool(
        feat.get("football_tendency_eligible")
        and feat.get("competitive_state") == "COMPETITIVE"
        and feat.get("play_intent") in DROPBACK_INTENTS
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


def assign_pressure_tiers(prior: dict[str, dict[str, float]], *, min_prior_dropbacks: int = 20) -> dict[str, dict[str, Any]]:
    """Assign LOW/MID/HIGH tiers from pregame lagged sack rates only.

    Cut points are cross-sectional terciles for the target week. The tiering is
    descriptive, not a fitted coefficient. Teams below the minimum prior
    dropback count remain unclassified rather than receiving a fabricated prior.
    """
    usable: list[tuple[str, float, int]] = []
    for team, counts in prior.items():
        db = int(counts.get("dropbacks", 0))
        sacks = int(counts.get("sacks", 0))
        if db >= min_prior_dropbacks:
            usable.append((team, sacks / db, db))
    rates = [x[1] for x in usable]
    q1 = _percentile(rates, 1 / 3)
    q2 = _percentile(rates, 2 / 3)
    if q1 is None or q2 is None:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for team, rate, db in usable:
        if rate <= q1:
            tier = "LOW"
        elif rate >= q2:
            tier = "HIGH"
        else:
            tier = "MID"
        out[team] = {
            "tier": tier,
            "pregame_sack_rate": rate,
            "prior_dropbacks": db,
            "q1": q1,
            "q2": q2,
        }
    return out


def build_exposure_records(rows: Iterable[dict[str, Any]], *, min_prior_dropbacks: int = 20) -> list[dict[str, Any]]:
    """Build third-down dropback records with strictly lagged opponent pass-rush state.

    Defensive history is accumulated only after all games in a week are scored,
    matching MODEL's week-level leakage boundary: same-week earlier games never
    enter another game's pregame state.
    """
    rows = [dict(r) for r in rows]
    seasons = sorted({int(_num(r.get("season")) or 0) for r in rows if _num(r.get("season"))})
    out: list[dict[str, Any]] = []

    for season in seasons:
        season_rows = [r for r in rows if int(_num(r.get("season")) or 0) == season]
        weeks = sorted({int(_num(r.get("week")) or 0) for r in season_rows if _num(r.get("week"))})
        history: dict[str, dict[str, float]] = defaultdict(lambda: {"dropbacks": 0.0, "sacks": 0.0})

        for week in weeks:
            week_rows = [r for r in season_rows if int(_num(r.get("week")) or 0) == week]
            tiers = assign_pressure_tiers(history, min_prior_dropbacks=min_prior_dropbacks)

            for row in week_rows:
                if not _eligible_competitive_dropback(row):
                    continue
                down = _num(row.get("down"))
                if down != 3:
                    continue
                defense = str(row.get("defteam") or "").upper()
                tier_info = tiers.get(defense)
                if not tier_info:
                    continue
                pressure = str(_feat(row).get("pressure_opportunity_bucket") or "")
                exposure = EXPOSURE_MAP.get(pressure)
                if exposure is None:
                    continue
                epa = _num(row.get("epa"))
                out.append({
                    "game_id": str(row.get("game_id") or ""),
                    "season": season,
                    "week": week,
                    "posteam": str(row.get("posteam") or "").upper(),
                    "defteam": defense,
                    "pressure_tier": tier_info["tier"],
                    "pregame_def_sack_rate": tier_info["pregame_sack_rate"],
                    "prior_def_dropbacks": tier_info["prior_dropbacks"],
                    "exposure": exposure,
                    "high_exposure": 1 if pressure == "HIGH_STRUCTURAL_EXPOSURE" else 0,
                    "sack": 1 if _feat(row).get("play_intent") == "DROPBACK_SACK" else 0,
                    "conversion": 1 if _flag(row, "first_down") else 0,
                    "epa": epa,
                })

            # Update defensive histories only after the full target week has been
            # evaluated, so no same-week leakage can occur.
            for row in week_rows:
                if not _eligible_competitive_dropback(row):
                    continue
                defense = str(row.get("defteam") or "").upper()
                if not defense:
                    continue
                history[defense]["dropbacks"] += 1
                if _feat(row).get("play_intent") == "DROPBACK_SACK":
                    history[defense]["sacks"] += 1
    return out


def _counter() -> dict[str, float]:
    return {"dropbacks": 0.0, "sacks": 0.0, "conversions": 0.0, "epa_n": 0.0, "epa_sum": 0.0}


def _add(c: dict[str, float], row: dict[str, Any]) -> None:
    c["dropbacks"] += 1
    c["sacks"] += int(row.get("sack") or 0)
    c["conversions"] += int(row.get("conversion") or 0)
    epa = _num(row.get("epa"))
    if epa is not None:
        c["epa_n"] += 1
        c["epa_sum"] += epa


def _render(c: dict[str, float]) -> dict[str, Any]:
    db = c["dropbacks"]
    return {
        "dropbacks": int(db),
        "sacks": int(c["sacks"]),
        "conversions": int(c["conversions"]),
        "sack_rate": c["sacks"] / db if db else None,
        "conversion_rate": c["conversions"] / db if db else None,
        "mean_epa": c["epa_sum"] / c["epa_n"] if c["epa_n"] else None,
    }


def summarize_exposure_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    grid: dict[str, dict[str, dict[str, float]]] = {
        tier: {"BASE": _counter(), "ELEVATED_PLUS": _counter()} for tier in PRESSURE_TIERS
    }
    by_season: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        tier = str(row.get("pressure_tier"))
        exposure = str(row.get("exposure"))
        if tier not in grid or exposure not in grid[tier]:
            continue
        _add(grid[tier][exposure], row)
        by_season[int(row.get("season") or 0)].append(row)

    rendered = {
        tier: {exp: _render(c) for exp, c in exps.items()}
        for tier, exps in grid.items()
    }

    def rate(tier: str, exposure: str, metric: str) -> float | None:
        return rendered[tier][exposure].get(metric)

    def diff(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else a - b

    base_high_low = diff(rate("HIGH", "BASE", "sack_rate"), rate("LOW", "BASE", "sack_rate"))
    exposed_high_low = diff(rate("HIGH", "ELEVATED_PLUS", "sack_rate"), rate("LOW", "ELEVATED_PLUS", "sack_rate"))
    interaction = diff(exposed_high_low, base_high_low)

    season_interactions: dict[str, Any] = {}
    for season, rows in sorted(by_season.items()):
        if season <= 0:
            continue
        sub = summarize_exposure_records_no_seasons(rows)
        season_interactions[str(season)] = sub["interaction"]

    return {
        "grid": rendered,
        "interaction": {
            "base_high_minus_low_sack_rate": base_high_low,
            "exposed_high_minus_low_sack_rate": exposed_high_low,
            "difference_in_differences": interaction,
            "high_tier_exposed_minus_base_sack_rate": diff(
                rate("HIGH", "ELEVATED_PLUS", "sack_rate"), rate("HIGH", "BASE", "sack_rate")
            ),
            "low_tier_exposed_minus_base_sack_rate": diff(
                rate("LOW", "ELEVATED_PLUS", "sack_rate"), rate("LOW", "BASE", "sack_rate")
            ),
        },
        "by_season_interaction": season_interactions,
    }


def summarize_exposure_records_no_seasons(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    grid: dict[str, dict[str, dict[str, float]]] = {
        tier: {"BASE": _counter(), "ELEVATED_PLUS": _counter()} for tier in PRESSURE_TIERS
    }
    for row in records:
        tier = str(row.get("pressure_tier"))
        exposure = str(row.get("exposure"))
        if tier in grid and exposure in grid[tier]:
            _add(grid[tier][exposure], row)
    rendered = {tier: {exp: _render(c) for exp, c in exps.items()} for tier, exps in grid.items()}

    def sr(tier: str, exp: str) -> float | None:
        return rendered[tier][exp]["sack_rate"]

    def diff(a, b):
        return None if a is None or b is None else a - b

    base = diff(sr("HIGH", "BASE"), sr("LOW", "BASE"))
    exposed = diff(sr("HIGH", "ELEVATED_PLUS"), sr("LOW", "ELEVATED_PLUS"))
    return {
        "grid": rendered,
        "interaction": {
            "base_high_minus_low_sack_rate": base,
            "exposed_high_minus_low_sack_rate": exposed,
            "difference_in_differences": diff(exposed, base),
            "high_tier_exposed_minus_base_sack_rate": diff(sr("HIGH", "ELEVATED_PLUS"), sr("HIGH", "BASE")),
            "low_tier_exposed_minus_base_sack_rate": diff(sr("LOW", "ELEVATED_PLUS"), sr("LOW", "BASE")),
        },
    }


def cluster_bootstrap_interaction(records: Iterable[dict[str, Any]], *, reps: int = 1000, seed: int = 20260916) -> dict[str, Any]:
    records = list(records)
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        game_id = str(row.get("game_id") or "")
        if game_id:
            by_game[game_id].append(row)
    game_ids = sorted(by_game)
    if len(game_ids) < 2:
        raise ValueError("interaction bootstrap requires at least two games")
    if reps < 100:
        raise ValueError("bootstrap reps must be >= 100")

    observed = summarize_exposure_records_no_seasons(records)["interaction"]
    keys = tuple(observed)
    draws: dict[str, list[float]] = {k: [] for k in keys}
    rng = random.Random(seed)
    for _ in range(reps):
        sampled: list[dict[str, Any]] = []
        for _j in range(len(game_ids)):
            sampled.extend(by_game[rng.choice(game_ids)])
        got = summarize_exposure_records_no_seasons(sampled)["interaction"]
        for key in keys:
            value = got.get(key)
            if value is not None:
                draws[key].append(value)

    return {
        "cluster": "game_id",
        "reps": reps,
        "seed": seed,
        "metrics": {
            key: {
                "observed": observed.get(key),
                "ci95_low": _percentile(values, 0.025),
                "ci95_high": _percentile(values, 0.975),
            }
            for key, values in draws.items()
        },
    }


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    seasons = tuple(sorted({int(s) for s in seasons}))
    if not seasons:
        raise ValueError("at least one development season is required")
    forbidden = [s for s in seasons if s >= SEALED_HOLDOUT_SEASON]
    if forbidden:
        raise ValueError(
            "exposure interaction discovery is development-only; sealed 2025 holdout and 2026 prospective data are forbidden: "
            + ",".join(map(str, forbidden))
        )
    return seasons

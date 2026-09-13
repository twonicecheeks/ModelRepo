"""Leakage-safe historical NFL feature primitives for MODEL 2.9.0 Phase 1.

This is a research/training core, not a production betting model. It accepts already
materialized game-level team metrics and builds pregame rows using strictly prior
same-season games plus optional prior-season priors. It contains no sportsbook data
and fits no coefficients.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Iterable

VERSION = "0.1.0"
LINEAGE = "nfl-game-foundation-v0.1.0-leakage-safe-2026-09-08"
CALIBRATION_STATUS = "UNFIT_RESEARCH_FOUNDATION"
HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
EARLY_SEASON_STATE = "EARLY_SEASON_PRIOR_HEAVY"

# Candidate research metrics only. Inclusion in a trained model must be justified
# out-of-sample later; these are not weights and are not coefficients.
DEFAULT_TEAM_METRICS = (
    "off_dropback_epa",
    "off_rush_epa",
    "off_success_rate",
    "off_cpoe",
    "off_sack_rate",
    "off_explosive_pass_rate",
    "off_explosive_rush_rate",
    "off_turnover_rate",
    "def_dropback_epa_allowed",
    "def_rush_epa_allowed",
    "def_success_rate_allowed",
    "def_sack_rate_generated",
    "def_explosive_pass_rate_allowed",
    "def_explosive_rush_rate_allowed",
    "def_takeaway_rate",
)


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:  # NaN
        return None
    return x


def _mean(rows: list[dict[str, Any]], metric: str) -> float | None:
    vals = [_num(r.get(metric)) for r in rows]
    good = [x for x in vals if x is not None]
    return fmean(good) if good else None


def _summary(rows: list[dict[str, Any]], metrics: Iterable[str], windows: tuple[int, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {"games_available": len(rows)}
    for metric in metrics:
        out[f"std_{metric}"] = _mean(rows, metric)
        for n in windows:
            out[f"last{n}_{metric}"] = _mean(rows[-n:], metric) if rows else None
    return out


def _prior_season_summary(
    history_by_team: dict[str, list[dict[str, Any]]],
    team: str,
    season: int,
    metrics: Iterable[str],
) -> dict[str, float | None]:
    rows = [r for r in history_by_team.get(team, []) if int(r["season"]) == season - 1]
    return {f"prior_season_{m}": _mean(rows, m) for m in metrics}


def build_pregame_feature_rows(
    games: Iterable[dict[str, Any]],
    team_game_metrics: Iterable[dict[str, Any]],
    *,
    metrics: Iterable[str] = DEFAULT_TEAM_METRICS,
    windows: tuple[int, ...] = (4, 8),
) -> list[dict[str, Any]]:
    """Build one feature object per game with strict pregame leakage isolation.

    Same-season team performance uses only metrics rows with week < target week.
    Current-game outcomes are returned in a separate ``target`` object and never
    appear inside ``features``. Market columns are ignored entirely.
    """
    metrics = tuple(metrics)
    if any(int(n) <= 0 for n in windows):
        raise ValueError("rolling windows must be positive")

    history_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_team_game: set[tuple[str, str]] = set()
    for raw in team_game_metrics:
        r = dict(raw)
        for required in ("game_id", "season", "week", "team"):
            if r.get(required) in (None, ""):
                raise ValueError(f"team metric row missing {required}")
        key = (str(r["game_id"]), str(r["team"]).upper())
        if key in seen_team_game:
            raise ValueError(f"duplicate team-game metric row: {key}")
        seen_team_game.add(key)
        r["team"] = str(r["team"]).upper()
        r["season"] = int(r["season"])
        r["week"] = int(r["week"])
        history_by_team[r["team"]].append(r)

    for rows in history_by_team.values():
        rows.sort(key=lambda r: (int(r["season"]), int(r["week"]), str(r["game_id"])))

    ordered_games = sorted(
        (dict(g) for g in games),
        key=lambda g: (int(g["season"]), int(g["week"]), str(g.get("gameday") or ""), str(g["game_id"])),
    )

    out: list[dict[str, Any]] = []
    for g in ordered_games:
        season = int(g["season"])
        week = int(g["week"])
        home = str(g["home_team"]).upper()
        away = str(g["away_team"]).upper()
        game_id = str(g["game_id"])

        # Strict same-season lag: even if another game in the same NFL week occurred
        # earlier in clock time, it is not admitted into a Week-N team history row.
        home_prior = [r for r in history_by_team.get(home, []) if r["season"] == season and r["week"] < week]
        away_prior = [r for r in history_by_team.get(away, []) if r["season"] == season and r["week"] < week]

        home_features = _summary(home_prior, metrics, windows)
        away_features = _summary(away_prior, metrics, windows)
        home_features.update(_prior_season_summary(history_by_team, home, season, metrics))
        away_features.update(_prior_season_summary(history_by_team, away, season, metrics))

        features: dict[str, Any] = {
            "home_rest_days": _num(g.get("home_rest")),
            "away_rest_days": _num(g.get("away_rest")),
            "neutral_site": str(g.get("location") or "").strip().lower() == "neutral",
        }
        for k, v in home_features.items():
            features[f"home_{k}"] = v
        for k, v in away_features.items():
            features[f"away_{k}"] = v

        home_score = _num(g.get("home_score"))
        away_score = _num(g.get("away_score"))
        if home_score is None or away_score is None:
            target = {"home_win": None, "home_margin": None}
        else:
            margin = home_score - away_score
            target = {"home_win": 1 if margin > 0 else (0 if margin < 0 else None), "home_margin": margin}

        if season == HOLDOUT_SEASON:
            split_state = "HOLDOUT_NEVER_FIT"
        elif season == PROSPECTIVE_SEASON:
            split_state = "PROSPECTIVE_ONLY"
        elif season < HOLDOUT_SEASON:
            split_state = "DEVELOPMENT_CANDIDATE"
        else:
            split_state = "FUTURE"

        out.append({
            "game_id": game_id,
            "season": season,
            "week": week,
            "game_type": g.get("game_type"),
            "gameday": g.get("gameday"),
            "away_team": away,
            "home_team": home,
            "feature_state": EARLY_SEASON_STATE if week == 1 else "PREGAME_PRIOR_ONLY",
            "split_state": split_state,
            "features": features,
            "target": target,
        })
    return out


def aggregate_pbp_to_team_games(pbp_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate basic nflverse PBP rows into game/team research metrics.

    This intentionally uses only stable, interpretable primitives. It is tolerant of
    missing optional fields but requires game/team identity. Kneels/no-plays are
    excluded from rushing/scrimmage efficiency where flags are available.
    """
    plays_by_game_team: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in pbp_rows:
        r = dict(raw)
        game_id = r.get("game_id")
        posteam = r.get("posteam")
        if not game_id or not posteam:
            continue
        plays_by_game_team[(str(game_id), str(posteam).upper())].append(r)

    output: list[dict[str, Any]] = []
    for (game_id, team), plays in sorted(plays_by_game_team.items()):
        sample = next((p for p in plays if p.get("season") is not None and p.get("week") is not None), None)
        if sample is None:
            raise ValueError(f"PBP team-game {game_id}/{team} missing season/week")
        season, week = int(sample["season"]), int(sample["week"])

        def flag(p: dict[str, Any], key: str) -> bool:
            return _num(p.get(key)) == 1.0

        def valid_play(p: dict[str, Any]) -> bool:
            return not flag(p, "no_play") and not flag(p, "qb_kneel")

        scrimmage = [p for p in plays if valid_play(p) and (flag(p, "qb_dropback") or flag(p, "rush"))]
        dropbacks = [p for p in scrimmage if flag(p, "qb_dropback")]
        rushes = [p for p in scrimmage if flag(p, "rush") and not flag(p, "qb_kneel")]

        def mean_field(rows: list[dict[str, Any]], field: str) -> float | None:
            vals = [_num(p.get(field)) for p in rows]
            good = [x for x in vals if x is not None]
            return fmean(good) if good else None

        def rate(rows: list[dict[str, Any]], predicate) -> float | None:
            return (sum(1 for p in rows if predicate(p)) / len(rows)) if rows else None

        def_epa_rows = [p for p in plays if valid_play(p) and p.get("defteam")]
        # Defensive metrics are finalized by pairing with the opponent's offensive
        # row below; this keeps a single definition for every play-based metric.
        row = {
            "game_id": game_id,
            "season": season,
            "week": week,
            "team": team,
            "opponent": next((str(p.get("defteam")).upper() for p in def_epa_rows if p.get("defteam")), None),
            "off_dropback_epa": mean_field(dropbacks, "epa"),
            "off_rush_epa": mean_field(rushes, "epa"),
            "off_success_rate": mean_field(scrimmage, "success"),
            "off_cpoe": mean_field(dropbacks, "cpoe"),
            "off_sack_rate": rate(dropbacks, lambda p: flag(p, "sack")),
            "off_explosive_pass_rate": rate(dropbacks, lambda p: (_num(p.get("yards_gained")) or 0) >= 20),
            "off_explosive_rush_rate": rate(rushes, lambda p: (_num(p.get("yards_gained")) or 0) >= 10),
            "off_turnover_rate": rate(scrimmage, lambda p: flag(p, "interception") or flag(p, "fumble_lost")),
        }
        output.append(row)

    by_key = {(r["game_id"], r["team"]): r for r in output}
    for r in output:
        opp = r.get("opponent")
        other = by_key.get((r["game_id"], opp)) if opp else None
        r["def_dropback_epa_allowed"] = other.get("off_dropback_epa") if other else None
        r["def_rush_epa_allowed"] = other.get("off_rush_epa") if other else None
        r["def_success_rate_allowed"] = other.get("off_success_rate") if other else None
        r["def_sack_rate_generated"] = other.get("off_sack_rate") if other else None
        r["def_explosive_pass_rate_allowed"] = other.get("off_explosive_pass_rate") if other else None
        r["def_explosive_rush_rate_allowed"] = other.get("off_explosive_rush_rate") if other else None
        r["def_takeaway_rate"] = other.get("off_turnover_rate") if other else None
    return output


if __name__ == "__main__":
    print(f"NFL historical feature core {VERSION} · {LINEAGE} · {CALIBRATION_STATUS}")

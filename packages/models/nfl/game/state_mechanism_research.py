"""NFL State Intelligence 0.1.1 — early-down mechanism research.

Coefficient-free historical diagnostics for the DEN@KC M04/M05/M19/M30 chain:
first-down result -> later down/distance -> structural pressure exposure ->
conversion/continuation environment.

This module does not fit a betting model, does not consume market data, and must
not be used to mutate the frozen Week 2 OMEGA forecast artifact.
"""
from __future__ import annotations

from collections import defaultdict
import random
from typing import Any, Iterable

VERSION = "0.1.1"
LINEAGE = "nfl-state-mechanism-m04-m05-m19-m30-v0.1.1-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

SCRIMMAGE_INTENTS = {
    "DESIGNED_PASS", "DESIGNED_RUN", "DROPBACK_SCRAMBLE", "DROPBACK_SACK"
}

METRIC_SPECS = {
    "second_long_plus_rate": ("second_long_plus", "second_observed"),
    "reach_third_rate": ("reached_third", "series"),
    "third_elevated_plus_rate": ("third_elevated_plus", "third_observed"),
    "third_high_rate": ("third_high", "third_observed"),
    "third_dropback_rate": ("third_dropback", "third_observed"),
    "third_dropback_sack_rate": ("third_sack", "third_dropback"),
    "third_conversion_rate": ("third_conversion", "third_observed"),
    "series_first_down_rate": ("series_first_down", "series"),
}


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


def _down(row: dict[str, Any]) -> int | None:
    x = _num(row.get("down"))
    return None if x is None else int(x)


def _play_id(row: dict[str, Any]) -> float:
    x = _num(row.get("play_id"))
    return x if x is not None else 1e18


def _eligible(row: dict[str, Any]) -> bool:
    feat = _feat(row)
    return bool(
        feat.get("football_tendency_eligible")
        and feat.get("competitive_state") == "COMPETITIVE"
        and feat.get("play_intent") in SCRIMMAGE_INTENTS
    )


def _make_series_record(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not series or _down(series[0]) != 1:
        return None
    start = series[0]
    success = _num(start.get("success"))
    if success is None:
        return None

    second = next((r for r in series[1:] if _down(r) == 2), None)
    third = next((r for r in series[1:] if _down(r) == 3), None)
    third_feat = _feat(third) if third else {}
    second_bucket = _feat(second).get("down_distance_bucket") if second else None
    third_pressure = third_feat.get("pressure_opportunity_bucket") if third else None
    third_intent = third_feat.get("play_intent") if third else None

    return {
        "game_id": str(start.get("game_id") or ""),
        "season": int(_num(start.get("season")) or 0),
        "posteam": str(start.get("posteam") or "").upper(),
        "drive": str(start.get("drive") or ""),
        "first_down_success": 1 if success >= 0.5 else 0,
        "first_down_intent": _feat(start).get("play_intent"),
        "second_observed": 1 if second else 0,
        "second_long_plus": 1 if second_bucket in {"D2_LONG", "D2_VERY_LONG"} else 0,
        "reached_third": 1 if third else 0,
        "third_observed": 1 if third else 0,
        "third_elevated_plus": 1 if third_pressure in {"ELEVATED_STRUCTURAL_EXPOSURE", "HIGH_STRUCTURAL_EXPOSURE"} else 0,
        "third_high": 1 if third_pressure == "HIGH_STRUCTURAL_EXPOSURE" else 0,
        "third_dropback": 1 if third_intent in {"DESIGNED_PASS", "DROPBACK_SCRAMBLE", "DROPBACK_SACK"} else 0,
        "third_sack": 1 if third_intent == "DROPBACK_SACK" else 0,
        "third_conversion": 1 if third and _flag(third, "first_down") else 0,
        "series_first_down": 1 if any(_flag(r, "first_down") for r in series) else 0,
    }


def build_series_records(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build first-down series records from annotated State Intelligence snaps.

    Series are reconstructed within game/team/drive. Nullified, terminal,
    victory-formation, special-teams, and extreme closeout/comeback states are
    excluded by the State Intelligence eligibility contract.
    """
    drives: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        if not _eligible(row):
            continue
        game_id = str(row.get("game_id") or "")
        team = str(row.get("posteam") or "").upper()
        drive = str(row.get("drive") or "")
        if not game_id or not team or not drive:
            continue
        drives[(game_id, team, drive)].append(row)

    out: list[dict[str, Any]] = []
    for key in sorted(drives):
        snaps = sorted(drives[key], key=_play_id)
        current: list[dict[str, Any]] = []
        for row in snaps:
            d = _down(row)
            if not current:
                if d != 1:
                    continue
                current = [row]
            else:
                # A repeated first down without a prior conversion usually reflects
                # an accepted offensive penalty/replay of the down; keep it in the
                # current series rather than inventing a new set of downs.
                current.append(row)

            if _flag(row, "first_down"):
                rec = _make_series_record(current)
                if rec:
                    out.append(rec)
                current = []
                continue

            # A fourth-down snap without a first down terminates the series.
            if d == 4:
                rec = _make_series_record(current)
                if rec:
                    out.append(rec)
                current = []

        if current:
            rec = _make_series_record(current)
            if rec:
                out.append(rec)
    return out


def _counter_template() -> dict[str, int]:
    return {
        "series": 0,
        "second_observed": 0,
        "second_long_plus": 0,
        "reached_third": 0,
        "third_observed": 0,
        "third_elevated_plus": 0,
        "third_high": 0,
        "third_dropback": 0,
        "third_sack": 0,
        "third_conversion": 0,
        "series_first_down": 0,
    }


def _accumulate(counter: dict[str, int], row: dict[str, Any]) -> None:
    counter["series"] += 1
    for key in counter:
        if key != "series":
            counter[key] += int(row.get(key) or 0)


def _rates(counter: dict[str, int]) -> dict[str, Any]:
    out: dict[str, Any] = dict(counter)
    for name, (num, den) in METRIC_SPECS.items():
        out[name] = (counter[num] / counter[den]) if counter[den] else None
    return out


def summarize_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    groups = {0: _counter_template(), 1: _counter_template()}
    intent_groups: dict[str, dict[int, dict[str, int]]] = defaultdict(
        lambda: {0: _counter_template(), 1: _counter_template()}
    )
    seasons: dict[int, dict[int, dict[str, int]]] = defaultdict(
        lambda: {0: _counter_template(), 1: _counter_template()}
    )

    for row in records:
        group = int(row["first_down_success"])
        _accumulate(groups[group], row)
        intent = str(row.get("first_down_intent") or "UNKNOWN")
        _accumulate(intent_groups[intent][group], row)
        _accumulate(seasons[int(row.get("season") or 0)][group], row)

    def render(pair: dict[int, dict[str, int]]) -> dict[str, Any]:
        return {"failure": _rates(pair[0]), "success": _rates(pair[1])}

    return {
        "overall": render(groups),
        "by_first_down_intent": {k: render(v) for k, v in sorted(intent_groups.items())},
        "by_season": {str(k): render(v) for k, v in sorted(seasons.items())},
    }


def observed_differences(records: Iterable[dict[str, Any]]) -> dict[str, float | None]:
    summary = summarize_records(records)["overall"]
    fail = summary["failure"]
    succ = summary["success"]
    out: dict[str, float | None] = {}
    for metric in METRIC_SPECS:
        a, b = fail.get(metric), succ.get(metric)
        out[metric] = None if a is None or b is None else a - b
    return out


def cluster_bootstrap_differences(
    records: Iterable[dict[str, Any]], *, reps: int = 1000, seed: int = 20260916
) -> dict[str, Any]:
    """Game-cluster bootstrap CIs for failure-minus-success rate differences."""
    records = list(records)
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        game_id = str(row.get("game_id") or "")
        if game_id:
            by_game[game_id].append(row)
    game_ids = sorted(by_game)
    if len(game_ids) < 2:
        raise ValueError("cluster bootstrap requires at least two games")
    if reps < 100:
        raise ValueError("bootstrap reps must be >= 100")

    observed = observed_differences(records)
    draws: dict[str, list[float]] = {k: [] for k in METRIC_SPECS}
    rng = random.Random(seed)

    # Pre-aggregate each game to avoid repeatedly traversing every series.
    game_counts: dict[str, dict[int, dict[str, int]]] = {}
    for game_id, rows in by_game.items():
        pair = {0: _counter_template(), 1: _counter_template()}
        for row in rows:
            _accumulate(pair[int(row["first_down_success"])], row)
        game_counts[game_id] = pair

    for _ in range(reps):
        totals = {0: _counter_template(), 1: _counter_template()}
        for _j in range(len(game_ids)):
            chosen = game_counts[rng.choice(game_ids)]
            for group in (0, 1):
                for key, value in chosen[group].items():
                    totals[group][key] += value
        fail, succ = _rates(totals[0]), _rates(totals[1])
        for metric in METRIC_SPECS:
            a, b = fail.get(metric), succ.get(metric)
            if a is not None and b is not None:
                draws[metric].append(a - b)

    def percentile(values: list[float], q: float) -> float | None:
        if not values:
            return None
        xs = sorted(values)
        pos = (len(xs) - 1) * q
        lo = int(pos)
        hi = min(lo + 1, len(xs) - 1)
        frac = pos - lo
        return xs[lo] * (1 - frac) + xs[hi] * frac

    return {
        "cluster": "game_id",
        "reps": reps,
        "seed": seed,
        "failure_minus_success": {
            metric: {
                "observed": observed.get(metric),
                "ci95_low": percentile(values, 0.025),
                "ci95_high": percentile(values, 0.975),
            }
            for metric, values in draws.items()
        },
    }


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    seasons = tuple(sorted({int(s) for s in seasons}))
    if not seasons:
        raise ValueError("at least one development season is required")
    forbidden = [s for s in seasons if s >= SEALED_HOLDOUT_SEASON]
    if forbidden:
        raise ValueError(
            "mechanism discovery is development-only; sealed 2025 holdout and 2026 prospective data are forbidden: "
            + ",".join(map(str, forbidden))
        )
    return seasons

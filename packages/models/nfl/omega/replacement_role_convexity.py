"""OMEGA 0.6 — H003 replacement-role convexity challenger.

Pre-registered mechanism H003 from OMEGA 0.1:
    a defender whose role expands materially may not scale tackle production linearly
    with defensive snap share because alignment, responsibility, and proximity to the
    ball can change with the role itself.

The frozen OMEGA 0.4 H008 topology model already scales linearly with H012 predicted
snap share. H003 tests one additional, strictly-lagged convexity term only when the
predicted role is at least 10 percentage points above a pre-change baseline.

No market data, sportsbook settlement convention, postseason, or OMEGA 2025 data is
used here.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Sequence

VERSION = "0.6.0"
LINEAGE = "omega-tackle-v0.6.0-h003-replacement-role-convexity-2026-09-11"
HOLDOUT_SEASON = 2025
BASELINE_WINDOW = 4
ACTIVATION_JUMP = 0.10
CONFIDENCE_GAMES = 2
MAX_FACTOR = 1.50
BETA_GRID = (0.0, 0.25, 0.50, 0.75, 1.00, 1.50)


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


def build_role_transition_rows(
    exposure_rows: Sequence[dict[str, Any]],
    team_snap_totals: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    """Build strictly-lagged pre-change role baselines.

    The baseline intentionally excludes the player's most recent appearance when
    possible. That lets a newly elevated role be detected rather than immediately
    absorbing the first high-snap game into the baseline. With only one prior game,
    the fallback is the strictly-prior position average.
    """
    by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in exposure_rows:
        if not truthy(r.get("eligible_standard_rate_fit")):
            continue
        season = as_int(r.get("season")); week = as_int(r.get("week"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 exposure row entered H003 role-transition history")
        if 2016 <= season <= 2024:
            by_week[(season, week)].append(r)

    hist: dict[str, list[float]] = defaultdict(list)
    pos_sum: dict[str, float] = defaultdict(float)
    pos_n: dict[str, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []

    for season, week in sorted(by_week):
        batch = by_week[(season, week)]
        if season >= 2017:
            for r in batch:
                pid = str(r.get("player_id") or "")
                game = str(r.get("game_id") or "")
                team = str(r.get("team") or "")
                if not pid or not game or not team:
                    continue
                actual = _snap_share(r, team_snap_totals)
                if actual is None:
                    continue
                pg = canonical_position_group(r)
                pos_prior = pos_sum[pg] / pos_n[pg] if pos_n[pg] else 0.35
                h = hist[pid]
                recent = h[-1] if h else pos_prior
                if len(h) >= 2:
                    pre = h[max(0, len(h)-1-BASELINE_WINDOW):len(h)-1]
                    prechange = fmean(pre) if pre else pos_prior
                else:
                    prechange = pos_prior
                rows.append({
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
                    "actual_snap_share": float(actual),
                    "prior_games": len(h),
                    "position_prior_snap_share": float(pos_prior),
                    "last1_snap_share": float(recent),
                    "prechange_baseline_snap_share": float(prechange),
                })
        # Strict same-week boundary.
        for r in batch:
            pid = str(r.get("player_id") or "")
            if not pid:
                continue
            share = _snap_share(r, team_snap_totals)
            if share is None:
                continue
            pg = canonical_position_group(r)
            hist[pid].append(float(share))
            pos_sum[pg] += float(share)
            pos_n[pg] += 1
    return rows


def score_rows(
    h008_rows: Sequence[dict[str, Any]],
    transition_features: dict[tuple[str, str, str], dict[str, Any]],
    *,
    beta: float,
    out_key: str = "role_convexity_xtc",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in h008_rows:
        key = (str(r.get("game_id") or ""), str(r.get("team") or ""), str(r.get("player_id") or ""))
        fr = transition_features.get(key)
        if fr is None:
            continue
        pred_share = max(0.0, min(1.0, float(num(r.get("predicted_snap_share"), 0.0) or 0.0)))
        baseline = max(0.0, min(1.0, float(num(fr.get("prechange_baseline_snap_share"), 0.0) or 0.0)))
        prior_games = max(0, as_int(fr.get("prior_games")))
        jump = pred_share - baseline
        activated = prior_games >= 1 and jump >= ACTIVATION_JUMP
        confidence = min(1.0, prior_games / float(CONFIDENCE_GAMES)) if prior_games > 0 else 0.0
        factor = 1.0
        if activated and beta > 0:
            factor = min(MAX_FACTOR, 1.0 + float(beta) * jump * confidence)
        base = max(0.0, float(num(r.get("topology_xtc"), 0.0) or 0.0))
        z = dict(r)
        for k, v in fr.items():
            if k not in z:
                z[k] = v
        z["h003_beta"] = float(beta)
        z["h003_role_jump"] = float(jump)
        z["h003_activated"] = 1 if activated else 0
        z["h003_history_confidence"] = float(confidence)
        z["h003_convexity_factor"] = float(factor)
        z[out_key] = base * factor
        out.append(z)
    return out


def mae(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> float:
    if not rows:
        return 0.0
    return fmean(abs(float(num(r.get(actual), 0.0) or 0.0) - float(num(r.get(pred), 0.0) or 0.0)) for r in rows)


def rmse(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> float:
    if not rows:
        return 0.0
    return (fmean((float(num(r.get(actual), 0.0) or 0.0) - float(num(r.get(pred), 0.0) or 0.0)) ** 2 for r in rows)) ** 0.5

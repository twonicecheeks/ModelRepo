"""OMEGA 0.7 — H004 assist-vs-primary credit decomposition challenger.

H004 tests whether combined tackle credit is better predicted when the two official
credit pathways are modeled separately:

- PRIMARY credit = SOLO + PRIMARY_WITH_ASSIST
- ASSIST credit = ASSIST

The H012 exposure forecast and H008 opportunity-footprint forecast remain frozen.
H003 remains rejected. No market data, postseason, or OMEGA 2025 data is used.
"""
from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.7.0"
LINEAGE = "omega-tackle-v0.7.0-h004-assist-primary-decomposition-2026-09-11"
HOLDOUT_SEASON = 2025
RATE_WINDOW = 8
PRIMARY_ALPHA_GRID = (5.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0)
ASSIST_ALPHA_GRID = (5.0, 10.0, 25.0, 50.0, 100.0, 200.0, 400.0)


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


def aggregate_player_family_credit_classes(
    event_rows: Iterable[dict[str, Any]],
    families: Sequence[str],
) -> dict[tuple[str, str], dict[str, dict[str, float]]]:
    """Aggregate standard defensive primary and assist credits by family.

    PRIMARY means the player was the primary credited tackler, either SOLO or
    PRIMARY_WITH_ASSIST. ASSIST means the player received an assist credit.
    """
    famset = set(families)
    out: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    for e in event_rows:
        season = as_int(e.get("season"))
        if season == HOLDOUT_SEASON:
            raise ValueError("2025 event row entered H004 credit-class aggregation")
        if not truthy(e.get("is_standard_def_scrimmage_credit")):
            continue
        fam = str(e.get("play_family") or "")
        if fam not in famset:
            continue
        game = str(e.get("game_id") or "")
        pid = str(e.get("player_id") or "")
        if not game or not pid:
            continue
        role = str(e.get("credit_role") or "").strip().upper()
        g = out.setdefault((game, pid), {f: {"primary": 0.0, "assist": 0.0} for f in families})
        unit = float(num(e.get("combined_credit_unit"), 1.0) or 1.0)
        if role in {"SOLO", "PRIMARY_WITH_ASSIST"}:
            g[fam]["primary"] += unit
        elif role == "ASSIST":
            g[fam]["assist"] += unit
        else:
            raise ValueError(f"Unknown standard defensive credit role in H004: {role!r}")
    return out


def build_player_credit_class_rows(
    exposure_rows: Sequence[dict[str, Any]],
    family_outcomes: Sequence[dict[str, Any]],
    player_credit_classes: dict[tuple[str, str], dict[str, dict[str, float]]],
    team_snap_totals: dict[tuple[str, str], float],
    families: Sequence[str],
) -> list[dict[str, Any]]:
    """Build strictly lagged player family x credit-class rate histories.

    Exposure denominator matches H008: realized team opportunity plays in family ×
    realized player defensive snap share. Same-week outcomes are admitted only after
    all target rows for the week are emitted.
    """
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
            raise ValueError("2025 exposure row entered H004 player histories")
        if 2016 <= season <= 2024:
            by_week[(season, week)].append(r)

    hist: dict[str, dict[str, dict[str, list[dict[str, float]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    pos_credits: dict[tuple[str, str, str], float] = defaultdict(float)
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
                actual = player_credit_classes.get(
                    (game, pid), {f: {"primary": 0.0, "assist": 0.0} for f in families}
                )
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
                    "prior_games": max(
                        (len(hist[pid][f]["primary"]) for f in families), default=0
                    ),
                }
                total_primary = total_assist = 0.0
                for f in families:
                    exposure_hist = hist[pid][f]["primary"][-RATE_WINDOW:]
                    # Primary and assist have identical exposure history by construction.
                    prior_e = sum(x["exposure"] for x in exposure_hist)
                    prior_p = sum(x["credits"] for x in exposure_hist)
                    prior_a = sum(x["credits"] for x in hist[pid][f]["assist"][-RATE_WINDOW:])
                    pprior = (
                        pos_credits[(pg, f, "primary")] / pos_exp[(pg, f)]
                        if pos_exp[(pg, f)] > 0 else 0.10
                    )
                    aprior = (
                        pos_credits[(pg, f, "assist")] / pos_exp[(pg, f)]
                        if pos_exp[(pg, f)] > 0 else 0.05
                    )
                    ap = float(actual.get(f, {}).get("primary", 0.0))
                    aa = float(actual.get(f, {}).get("assist", 0.0))
                    total_primary += ap; total_assist += aa
                    row[f"prior_last8_exposure_{f}"] = prior_e
                    row[f"prior_last8_primary_{f}"] = prior_p
                    row[f"prior_last8_assist_{f}"] = prior_a
                    row[f"position_prior_primary_rate_{f}"] = pprior
                    row[f"position_prior_assist_rate_{f}"] = aprior
                    row[f"actual_primary_{f}"] = ap
                    row[f"actual_assist_{f}"] = aa
                row["actual_primary_total"] = total_primary
                row["actual_assist_total"] = total_assist
                row["actual_credit_class_sum"] = total_primary + total_assist
                out.append(row)

        # Update histories only after the whole week is emitted.
        for r in batch:
            game = str(r.get("game_id") or "")
            team = str(r.get("team") or "")
            pid = str(r.get("player_id") or "")
            fg = fam_map.get((game, team))
            share = _snap_share(r, team_snap_totals)
            if not game or not team or not pid or fg is None or share is None:
                continue
            pg = canonical_position_group(r)
            actual = player_credit_classes.get(
                (game, pid), {f: {"primary": 0.0, "assist": 0.0} for f in families}
            )
            for f in families:
                exp = float(fg.get(f"opp_{f}") or 0.0) * float(share)
                p = float(actual.get(f, {}).get("primary", 0.0))
                a = float(actual.get(f, {}).get("assist", 0.0))
                hist[pid][f]["primary"].append({"credits": p, "exposure": exp})
                hist[pid][f]["assist"].append({"credits": a, "exposure": exp})
                pos_credits[(pg, f, "primary")] += p
                pos_credits[(pg, f, "assist")] += a
                pos_exp[(pg, f)] += exp
    return out


def score_rows(
    rows: Sequence[dict[str, Any]],
    *,
    primary_alpha: float,
    assist_alpha: float,
    xto_predictions: dict[tuple[str, str], float],
    exposure_predictions: dict[tuple[str, str, str], float],
    family_share_predictions: dict[tuple[str, str], dict[str, float]],
    families: Sequence[str],
    out_key: str = "h004_xtc",
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
        pred_primary = pred_assist = 0.0
        z = dict(r)
        z["predicted_xto"] = float(x_to)
        z["predicted_snap_share"] = ss
        for f in families:
            sh = max(0.0, float(shares.get(f, 0.0)))
            pred_opp = max(0.0, float(x_to) * sh)
            prior_e = float(r[f"prior_last8_exposure_{f}"])
            prior_p = float(r[f"prior_last8_primary_{f}"])
            prior_a = float(r[f"prior_last8_assist_{f}"])
            pprior = float(r[f"position_prior_primary_rate_{f}"])
            aprior = float(r[f"position_prior_assist_rate_{f}"])
            pden = prior_e + float(primary_alpha)
            aden = prior_e + float(assist_alpha)
            prate = (prior_p + float(primary_alpha)*pprior)/pden if pden > 0 else pprior
            arate = (prior_a + float(assist_alpha)*aprior)/aden if aden > 0 else aprior
            pcon = pred_opp * ss * prate
            acon = pred_opp * ss * arate
            z[f"pred_share_{f}"] = sh
            z[f"pred_opp_{f}"] = pred_opp
            z[f"shrunk_primary_rate_{f}"] = prate
            z[f"shrunk_assist_rate_{f}"] = arate
            z[f"pred_primary_{f}"] = pcon
            z[f"pred_assist_{f}"] = acon
            pred_primary += pcon; pred_assist += acon
        z["h004_primary_alpha"] = float(primary_alpha)
        z["h004_assist_alpha"] = float(assist_alpha)
        z["pred_primary_total"] = max(0.0, pred_primary)
        z["pred_assist_total"] = max(0.0, pred_assist)
        z["pred_assist_share"] = (
            pred_assist / (pred_primary + pred_assist)
            if (pred_primary + pred_assist) > 0 else 0.0
        )
        z[out_key] = max(0.0, pred_primary + pred_assist)
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

"""NFL State Intelligence 0.1.4 — leakage-safe game challenger utilities.

This module converts the validated DEN@KC state components into a deliberately
small set of pregame-only matchup features, then provides paired bootstrap tools
for incremental model comparison. It does not read sportsbook data, open the 2025
holdout, or mutate frozen OMEGA forecasts.

Feature signs are defined from the home-team perspective:
- offense_exposure_advantage = away offense exposure propensity - home offense exposure propensity
  (positive means the away offense has historically put itself in more structurally exposed 3rd downs)
- defense_exposed_sack_advantage = home defense exposed-state sack conversion - away defense equivalent
  (positive means the home defense has historically converted exposed dropbacks into sacks more often)
"""
from __future__ import annotations

from collections import defaultdict
from math import log
import random
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.1.4"
LINEAGE = "nfl-state-feature-challenger-v0.1.4-den-kc-m04-m05-m06-m19-2026-09-16"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026

VARIANTS = ("OFFENSE_EXPOSURE", "DEFENSE_EXPOSED_SACK", "COMBINED")
STATE_FEATURE_NAMES = {
    "OFFENSE_EXPOSURE": (
        "state_offense_exposure_advantage",
        "missing__state_offense_exposure_advantage",
    ),
    "DEFENSE_EXPOSED_SACK": (
        "state_defense_exposed_sack_advantage",
        "missing__state_defense_exposed_sack_advantage",
    ),
    "COMBINED": (
        "state_offense_exposure_advantage",
        "missing__state_offense_exposure_advantage",
        "state_defense_exposed_sack_advantage",
        "missing__state_defense_exposed_sack_advantage",
    ),
}


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    seasons = tuple(sorted({int(s) for s in seasons}))
    if not seasons:
        raise ValueError("at least one development season is required")
    forbidden = [s for s in seasons if s >= SEALED_HOLDOUT_SEASON]
    if forbidden:
        raise ValueError(
            "state challenger discovery is development-only; sealed 2025 holdout and 2026 prospective data are forbidden: "
            + ",".join(map(str, forbidden))
        )
    return seasons


def build_game_state_features(
    persistence_records: dict[str, list[dict[str, Any]]],
    games: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Join strictly lagged component records into one home-perspective game row."""
    offense: dict[tuple[str, str], dict[str, Any]] = {}
    defense: dict[tuple[str, str], dict[str, Any]] = {}
    for r in persistence_records.get("offense", []):
        key = (str(r.get("game_id") or ""), str(r.get("team") or "").upper())
        if key[0] and key[1]:
            offense[key] = r
    for r in persistence_records.get("defense", []):
        key = (str(r.get("game_id") or ""), str(r.get("team") or "").upper())
        if key[0] and key[1]:
            defense[key] = r

    out: dict[str, dict[str, Any]] = {}
    for g in games:
        gid = str(g.get("game_id") or "")
        home = str(g.get("home_team") or "").upper()
        away = str(g.get("away_team") or "").upper()
        if not gid or not home or not away:
            continue

        ho = offense.get((gid, home))
        ao = offense.get((gid, away))
        hd = defense.get((gid, home))
        ad = defense.get((gid, away))
        ho_rate = _num(ho.get("pregame_exposure_rate")) if ho else None
        ao_rate = _num(ao.get("pregame_exposure_rate")) if ao else None
        hd_rate = _num(hd.get("pregame_exposed_sack_rate")) if hd else None
        ad_rate = _num(ad.get("pregame_exposed_sack_rate")) if ad else None

        off_adv = None if ho_rate is None or ao_rate is None else ao_rate - ho_rate
        def_adv = None if hd_rate is None or ad_rate is None else hd_rate - ad_rate
        out[gid] = {
            "game_id": gid,
            "home_team": home,
            "away_team": away,
            "home_offense_exposure_rate": ho_rate,
            "away_offense_exposure_rate": ao_rate,
            "home_defense_exposed_sack_rate": hd_rate,
            "away_defense_exposed_sack_rate": ad_rate,
            "home_offense_prior_third_downs": int(_num(ho.get("prior_third_downs")) or 0) if ho else 0,
            "away_offense_prior_third_downs": int(_num(ao.get("prior_third_downs")) or 0) if ao else 0,
            "home_defense_prior_exposed_dropbacks": int(_num(hd.get("prior_exposed_dropbacks")) or 0) if hd else 0,
            "away_defense_prior_exposed_dropbacks": int(_num(ad.get("prior_exposed_dropbacks")) or 0) if ad else 0,
            "state_offense_exposure_advantage": off_adv,
            "state_defense_exposed_sack_advantage": def_adv,
            "offense_feature_available": off_adv is not None,
            "defense_feature_available": def_adv is not None,
            "combined_feature_available": off_adv is not None and def_adv is not None,
        }
    return out


def state_feature_names(variant: str) -> tuple[str, ...]:
    variant = str(variant).upper()
    if variant not in STATE_FEATURE_NAMES:
        raise ValueError(f"unknown state challenger variant: {variant}")
    return STATE_FEATURE_NAMES[variant]


def vectorize_state_features(game_state: dict[str, Any] | None, variant: str) -> tuple[float | None, ...]:
    """Return state values plus explicit missingness indicators."""
    variant = str(variant).upper()
    names = state_feature_names(variant)
    state = game_state or {}
    values: list[float | None] = []
    for name in names:
        if name.startswith("missing__"):
            base = name[len("missing__"):]
            values.append(1.0 if _num(state.get(base)) is None else 0.0)
        else:
            values.append(_num(state.get(name)))
    return tuple(values)


def augment_vector(
    base_x: Sequence[float | None], game_state: dict[str, Any] | None, variant: str
) -> tuple[float | None, ...]:
    return tuple(base_x) + vectorize_state_features(game_state, variant)


def availability(game_state: dict[str, Any] | None, variant: str) -> bool:
    state = game_state or {}
    variant = str(variant).upper()
    if variant == "OFFENSE_EXPOSURE":
        return bool(state.get("offense_feature_available"))
    if variant == "DEFENSE_EXPOSED_SACK":
        return bool(state.get("defense_feature_available"))
    if variant == "COMBINED":
        return bool(state.get("combined_feature_available"))
    raise ValueError(f"unknown state challenger variant: {variant}")


def _clip(p: float) -> float:
    return min(1.0 - 1e-12, max(1e-12, float(p)))


def _metric_delta(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        raise ValueError("paired metric delta requires rows")
    base_brier = fmean((float(r["baseline_p"]) - int(r["y"])) ** 2 for r in rows)
    cand_brier = fmean((float(r["candidate_p"]) - int(r["y"])) ** 2 for r in rows)
    base_ll = -fmean(
        int(r["y"]) * log(_clip(float(r["baseline_p"])))
        + (1 - int(r["y"])) * log(_clip(1.0 - float(r["baseline_p"])))
        for r in rows
    )
    cand_ll = -fmean(
        int(r["y"]) * log(_clip(float(r["candidate_p"])))
        + (1 - int(r["y"])) * log(_clip(1.0 - float(r["candidate_p"])))
        for r in rows
    )
    base_acc = fmean(1.0 if (float(r["baseline_p"]) >= 0.5) == bool(int(r["y"])) else 0.0 for r in rows)
    cand_acc = fmean(1.0 if (float(r["candidate_p"]) >= 0.5) == bool(int(r["y"])) else 0.0 for r in rows)
    return {
        "log_loss_delta": cand_ll - base_ll,
        "brier_delta": cand_brier - base_brier,
        "accuracy_delta": cand_acc - base_acc,
    }


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def paired_week_cluster_bootstrap(
    rows: Iterable[dict[str, Any]], *, reps: int = 1000, seed: int = 20260916
) -> dict[str, Any]:
    """Bootstrap paired challenger-minus-baseline metric deltas by season-week cluster."""
    rows = [dict(r) for r in rows]
    if reps < 100:
        raise ValueError("bootstrap reps must be >= 100")
    by_cluster: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = (int(r.get("season") or 0), int(r.get("week") or 0))
        if key[0] > 0 and key[1] > 0:
            by_cluster[key].append(r)
    clusters = sorted(by_cluster)
    if len(clusters) < 2:
        raise ValueError("paired bootstrap requires at least two season-week clusters")

    observed = _metric_delta(rows)
    draws: dict[str, list[float]] = {k: [] for k in observed}
    rng = random.Random(seed)
    for _ in range(reps):
        sampled: list[dict[str, Any]] = []
        for _j in range(len(clusters)):
            sampled.extend(by_cluster[rng.choice(clusters)])
        got = _metric_delta(sampled)
        for key, value in got.items():
            draws[key].append(value)

    return {
        "cluster": "season_week",
        "reps": reps,
        "seed": seed,
        "metrics": {
            key: {
                "observed": observed[key],
                "ci95_low": _percentile(values, 0.025),
                "ci95_high": _percentile(values, 0.975),
            }
            for key, values in draws.items()
        },
    }


def promotion_signal(
    paired_bootstrap: dict[str, Any], *, seasons_improved_log_loss: int, seasons_total: int
) -> dict[str, Any]:
    """Conservative gate for further challenger research, never production promotion."""
    m = paired_bootstrap.get("metrics", {})
    ll = m.get("log_loss_delta", {})
    br = m.get("brier_delta", {})
    ll_obs = _num(ll.get("observed"))
    ll_hi = _num(ll.get("ci95_high"))
    br_obs = _num(br.get("observed"))
    qualifies = bool(
        ll_obs is not None and br_obs is not None and ll_hi is not None
        and ll_obs < 0 and br_obs < 0 and ll_hi < 0
        and seasons_total > 0 and seasons_improved_log_loss >= max(1, seasons_total - 1)
    )
    return {
        "status": "NEXT_STAGE_CHALLENGER_SIGNAL" if qualifies else "RESEARCH_ONLY_NO_PROMOTION_SIGNAL",
        "requiresProductionValidation": True,
        "criteria": {
            "pooledLogLossImproves": bool(ll_obs is not None and ll_obs < 0),
            "pooledBrierImproves": bool(br_obs is not None and br_obs < 0),
            "logLossBootstrapCiEntirelyBelowZero": bool(ll_hi is not None and ll_hi < 0),
            "seasonLogLossDirectionGate": bool(seasons_total > 0 and seasons_improved_log_loss >= max(1, seasons_total - 1)),
        },
    }


if __name__ == "__main__":
    print(f"NFL State Intelligence {VERSION} · {LINEAGE}")

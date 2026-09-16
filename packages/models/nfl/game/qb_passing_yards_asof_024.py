"""NFL QB Model 0.2.4 — 2026 as-of passing-yards shadow scorer helpers.

This layer scores the already-frozen 0.2.1 MODEL_A_DIRECT prospectively. It does
not fit or tune coefficients. 2025 is allowed only as lagged feature history, and
2026 rows are allowed only from weeks strictly earlier than the target game week.
The target QB identity must be supplied from an explicitly verified external source;
this module never guesses a starter.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean
from typing import Any, Iterable

VERSION = "0.2.4"
LINEAGE = "nfl-qb-passing-yards-2026-asof-shadow-v0.2.4-2026-09-16"
PROSPECTIVE_SEASON = 2026
SOURCE_PROMOTION_VERSION = "0.2.3"
FROZEN_CANDIDATE = "MODEL_A_DIRECT"
ALLOWED_IDENTITY_SOURCES = frozenset({
    "DIRECT_SPORTSBOOK_MARKET",
    "OFFICIAL_STARTER_ANNOUNCEMENT",
    "USER_VERIFIED_EXTERNAL",
})


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


@dataclass(frozen=True)
class TargetContext:
    season: int
    week: int
    game_id: str
    team: str
    opponent: str
    home: int
    qb_gsis_id: str
    qb_name: str
    identity_source: str


@dataclass(frozen=True)
class AsOfFeatureRow:
    target: TargetContext
    x: tuple[float | None, ...]
    baseline_last4: float
    league_prior_mean: float
    qb_prior_games: int
    team_prior_games: int
    defense_prior_games: int
    prior_2026_history_rows: int
    max_2026_history_week: int | None


def assert_promoted_spec(spec: dict[str, Any]) -> None:
    if str(spec.get("version")) != SOURCE_PROMOTION_VERSION:
        raise ValueError("QB 0.2.4 promotion version drift")
    if spec.get("status") != "PROSPECTIVE_SHADOW_READY_FROZEN_0.2.1":
        raise ValueError("QB 0.2.4 promotion status drift")
    if spec.get("frozenCandidate") != FROZEN_CANDIDATE:
        raise ValueError("QB 0.2.4 frozen candidate drift")
    if int(spec.get("prospectiveSeason") or 0) != PROSPECTIVE_SEASON:
        raise ValueError("QB 0.2.4 prospective season drift")
    if spec.get("prospectiveOutcomeRead") is not False:
        raise ValueError("QB 0.2.4 refuses promotion source that already read 2026 outcomes")
    if spec.get("marketDependency") is not False or bool(spec.get("marketFieldsAllowed")):
        raise ValueError("QB 0.2.4 promotion market contamination")
    if int(spec.get("oddsPapiRequests") or 0) != 0:
        raise ValueError("QB 0.2.4 OddsPapi drift")
    if spec.get("postHoldoutRefitPerformed") is not False or spec.get("postHoldoutReselectionPerformed") is not False:
        raise ValueError("QB 0.2.4 promotion mutation drift")
    if spec.get("requiresVerifiedTargetQbIdentity") is not True or spec.get("requiresAsOfPregameFeatureSnapshot") is not True:
        raise ValueError("QB 0.2.4 verified-identity/as-of contract drift")
    if spec.get("nextGate") != "BUILD_2026_ASOF_QB_PASSING_YARDS_SCORER_WITH_VERIFIED_IDENTITY":
        raise ValueError("QB 0.2.4 promotion next-gate drift")


def validate_identity_source(value: str) -> str:
    src = clean(value).upper()
    if src not in ALLOWED_IDENTITY_SOURCES:
        raise ValueError(
            "verified identity source must be one of: " + ", ".join(sorted(ALLOWED_IDENTITY_SOURCES))
        )
    return src


def build_target_context(
    *,
    game_id: str,
    team: str,
    qb_gsis_id: str,
    qb_name: str,
    identity_source: str,
    contract: Any,
) -> TargetContext:
    parsed = contract.parse_game_id(clean(game_id))
    if int(parsed["season"]) != PROSPECTIVE_SEASON:
        raise ValueError(f"QB 0.2.4 requires season {PROSPECTIVE_SEASON} target")
    t = contract.normalize_team_abbr(clean(team).upper())
    away = contract.normalize_team_abbr(parsed["away_team"])
    home = contract.normalize_team_abbr(parsed["home_team"])
    if t == away:
        opp, is_home = home, 0
    elif t == home:
        opp, is_home = away, 1
    else:
        raise ValueError(f"target team {t} not in game_id {game_id}")
    qid = clean(qb_gsis_id)
    if not qid:
        raise ValueError("verified target QB GSIS ID is required")
    return TargetContext(
        season=PROSPECTIVE_SEASON,
        week=int(parsed["week"]),
        game_id=clean(game_id),
        team=t,
        opponent=opp,
        home=is_home,
        qb_gsis_id=qid,
        qb_name=clean(qb_name),
        identity_source=validate_identity_source(identity_source),
    )


def add_game_context(rows: Iterable[dict[str, Any]], contract: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in rows:
        row = dict(raw)
        gid = clean(row.get("game_id"))
        team = contract.normalize_team_abbr(clean(row.get("team")).upper())
        parsed = contract.parse_game_id(gid)
        away = contract.normalize_team_abbr(parsed["away_team"])
        home = contract.normalize_team_abbr(parsed["home_team"])
        if team == away:
            row["_opponent"] = home; row["_home"] = 0
        elif team == home:
            row["_opponent"] = away; row["_home"] = 1
        else:
            raise ValueError(f"history team/game identity mismatch: {gid} team={team}")
        row["team"] = team
        key = (gid, team)
        if key in seen:
            raise ValueError(f"duplicate canonical QB history team-game: {gid} {team}")
        seen.add(key)
        out.append(row)
    out.sort(key=lambda r: (int(r.get("season") or 0), int(r.get("week") or 0), clean(r.get("game_id")), clean(r.get("team"))))
    return out


def assert_history_cutoff(rows: Iterable[dict[str, Any]], target_week: int) -> dict[str, Any]:
    tw = int(target_week)
    if not (1 <= tw <= 30):
        raise ValueError("target week out of range")
    total = prior_2026 = 0
    weeks: list[int] = []
    for r in rows:
        season = int(r.get("season") or 0)
        week = int(r.get("week") or 0)
        if season > PROSPECTIVE_SEASON:
            raise ValueError("history contains future season")
        if season == PROSPECTIVE_SEASON:
            if week >= tw:
                raise ValueError(f"target/current-or-later 2026 history forbidden: week {week} >= target week {tw}")
            prior_2026 += 1; weeks.append(week)
        total += 1
    return {
        "historyRows": total,
        "prior2026Rows": prior_2026,
        "max2026HistoryWeek": max(weeks) if weeks else None,
        "targetWeek": tw,
    }


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    vals = [num(r.get(field)) for r in rows]
    good = [float(v) for v in vals if v is not None]
    return None if not good else fmean(good)


def build_asof_feature_row(history_rows: Iterable[dict[str, Any]], target: TargetContext, q20: Any) -> AsOfFeatureRow:
    rows = [dict(r) for r in history_rows]
    cutoff = assert_history_cutoff(rows, target.week)
    if tuple(q20.FEATURE_NAMES) != tuple(q20.feature_names()):
        raise ValueError("QB 0.2.4 frozen 0.2.0 feature-name contract drift")

    qb_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    team_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    def_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    league_hist: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: (int(r.get("season") or 0), int(r.get("week") or 0), clean(r.get("game_id")), clean(r.get("team")))):
        qid = clean(row.get("observed_start_qb_gsis_id"))
        team = clean(row.get("team")).upper()
        opp = clean(row.get("_opponent")).upper()
        if not qid or not team or not opp:
            raise ValueError(f"history row missing QB/team/opponent identity: {row.get('game_id')} {team} {qid}")
        qb_hist[qid].append(row)
        team_hist[team].append(row)
        def_hist[opp].append(row)
        league_hist.append(row)

    qh = qb_hist[target.qb_gsis_id]
    th = team_hist[target.team]
    dh = def_hist[target.opponent]
    fmap: dict[str, float | None] = {
        "home": float(target.home),
        "week": float(target.week),
        "qb_prior_games": float(len(qh)),
        "qb_same_team_last_game": 1.0 if qh and clean(qh[-1].get("team")).upper() == target.team else 0.0,
        "team_prior_games": float(len(th)),
        "def_prior_games": float(len(dh)),
    }
    league_prior = _mean(league_hist, "official_passing_yards")
    q20._put_with_missing(fmap, "league_prior_mean_passing_yards", league_prior)

    qb_windows = {
        "last4": q20._window(qh, n=4),
        "last8": q20._window(qh, n=8),
        "prior_season": q20._window(qh, season=PROSPECTIVE_SEASON - 1),
    }
    for horizon, hrows in qb_windows.items():
        sm = q20.qb_summary(hrows)
        for metric in q20.QB_METRICS:
            q20._put_with_missing(fmap, f"qb_{horizon}_{metric}", sm[metric])
    for horizon, n in (("last4", 4), ("last8", 8)):
        sm = q20.team_summary(q20._window(th, n=n))
        for metric in q20.TEAM_METRICS:
            q20._put_with_missing(fmap, f"team_{horizon}_{metric}", sm[metric])
        ds = q20.defense_summary(q20._window(dh, n=n))
        for metric in q20.DEF_METRICS:
            q20._put_with_missing(fmap, f"def_{horizon}_{metric}", ds[metric])

    if set(fmap) != set(q20.FEATURE_NAMES):
        missing = sorted(set(q20.FEATURE_NAMES) - set(fmap)); extra = sorted(set(fmap) - set(q20.FEATURE_NAMES))
        raise ValueError(f"QB 0.2.4 feature contract drift missing={missing} extra={extra}")
    last4 = q20.qb_summary(q20._window(qh, n=4))["passing_yards"]
    baseline = last4 if last4 is not None else league_prior
    if baseline is None or league_prior is None:
        raise ValueError("prospective feature history insufficient for baseline/league prior")

    return AsOfFeatureRow(
        target=target,
        x=tuple(fmap[name] for name in q20.FEATURE_NAMES),
        baseline_last4=float(baseline),
        league_prior_mean=float(league_prior),
        qb_prior_games=len(qh),
        team_prior_games=len(th),
        defense_prior_games=len(dh),
        prior_2026_history_rows=int(cutoff["prior2026Rows"]),
        max_2026_history_week=cutoff["max2026HistoryWeek"],
    )


def predictive_distribution(point_prediction: float, residual_calibration: dict[str, Any]) -> dict[str, Any]:
    q = residual_calibration.get("quantiles") or {}
    required = ("p05", "p10", "p25", "p50", "p75", "p90", "p95")
    if any(k not in q for k in required):
        raise ValueError("frozen residual calibration quantiles incomplete")
    point = float(point_prediction)
    absolute = {k: point + float(q[k]) for k in required}
    return {
        "source": residual_calibration.get("source"),
        "calibrationN": int(residual_calibration.get("n") or 0),
        "residualMeanActualMinusPrediction": float(residual_calibration.get("meanResidualActualMinusPrediction") or 0.0),
        "residualSigma": float(residual_calibration.get("sigma") or 0.0),
        "predictiveQuantiles": absolute,
        "central80": [absolute["p10"], absolute["p90"]],
        "central90": [absolute["p05"], absolute["p95"]],
    }


if __name__ == "__main__":
    print(f"NFL QB passing-yards as-of scorer helpers {VERSION} · {LINEAGE}")

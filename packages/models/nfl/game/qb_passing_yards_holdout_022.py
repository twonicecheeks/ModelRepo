"""NFL QB Model 0.2.2 — single-use 2025 confirmatory holdout helpers.

No model selection or refit is allowed here. The frozen 0.2.1 MODEL_A_DIRECT is
scored once against the preregistered last-four benchmark. Feature construction
mirrors 0.2.0 exactly, including the rule that all games in a week are featurized
before any result from that week is admitted to history.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean
from typing import Any, Iterable

VERSION = "0.2.2"
LINEAGE = "nfl-qb-passing-yards-single-2025-holdout-v0.2.2-2026-09-16"
HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
FROZEN_SOURCE_VERSION = "0.2.1"
FROZEN_CANDIDATE = "MODEL_A_DIRECT"


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def assert_holdout_rows(rows: Iterable[dict[str, Any]]) -> None:
    vals = {int(r.get("season") or 0) for r in rows}
    if vals != {HOLDOUT_SEASON}:
        raise ValueError(f"0.2.2 requires exactly holdout season {HOLDOUT_SEASON}; got {sorted(vals)}")


def assert_freeze_ready(freeze_spec: dict[str, Any], manifest: dict[str, Any]) -> None:
    if freeze_spec.get("version") != FROZEN_SOURCE_VERSION:
        raise ValueError("0.2.2 freeze version drift")
    if freeze_spec.get("status") != "DEVELOPMENT_FROZEN_AWAITING_SINGLE_2025_HOLDOUT":
        raise ValueError("0.2.2 freeze status drift")
    if freeze_spec.get("frozenCandidate") != FROZEN_CANDIDATE:
        raise ValueError("0.2.2 frozen candidate drift")
    if int(freeze_spec.get("sealedHoldoutSeason") or 0) != HOLDOUT_SEASON:
        raise ValueError("0.2.2 holdout season drift")
    if freeze_spec.get("holdoutOpened") is not False or int(freeze_spec.get("holdoutLabelsAdmitted") or 0) != 0:
        raise ValueError("0.2.2 refuses already-open freeze spec")
    if freeze_spec.get("prospectiveRead") is not False:
        raise ValueError("0.2.2 prospective boundary drift")
    if freeze_spec.get("marketDependency") is not False or bool(freeze_spec.get("marketFieldsAllowed")):
        raise ValueError("0.2.2 market contamination")
    if int(freeze_spec.get("oddsPapiRequests") or 0) != 0:
        raise ValueError("0.2.2 OddsPapi drift")
    if bool(freeze_spec.get("selectionAfterHoldoutAllowed")) or bool(freeze_spec.get("refitAfterHoldoutAllowed")):
        raise ValueError("0.2.2 post-holdout mutation policy drift")
    if manifest.get("nextGate") != "RUN_SINGLE_2025_CONFIRMATORY_HOLDOUT_WITH_FROZEN_0.2.1_ONLY":
        raise ValueError("0.2.2 next-gate drift")
    if manifest.get("holdoutOpened") is not False or int(manifest.get("holdoutLabelsAdmitted") or 0) != 0:
        raise ValueError("0.2.2 freeze manifest already opened")


@dataclass(frozen=True)
class HoldoutExample:
    season: int
    week: int
    game_id: str
    team: str
    opponent: str
    qb_gsis_id: str
    x: tuple[float | None, ...]
    actual_passing_yards: float
    baseline_last4: float


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    vals = [float(r[field]) for r in rows if r.get(field) is not None]
    return None if not vals else fmean(vals)


def build_holdout_examples(
    dev_rows: Iterable[dict[str, Any]],
    holdout_rows: Iterable[dict[str, Any]],
    q20: Any,
) -> list[HoldoutExample]:
    """Build 2025 features from frozen 2016-2024 history plus earlier 2025 weeks only."""
    dev = [dict(r) for r in dev_rows]
    hold = [dict(r) for r in holdout_rows]
    if not dev or not hold:
        raise ValueError("development and holdout rows are required")
    if any(int(r.get("season") or 0) >= HOLDOUT_SEASON for r in dev):
        raise ValueError("development history contains 2025+")
    assert_holdout_rows(hold)
    if tuple(q20.FEATURE_NAMES) != tuple(q20.feature_names()):
        raise ValueError("frozen 0.2.0 feature-name contract drift")

    dev.sort(key=lambda r: (int(r.get("season") or 0), int(r.get("week") or 0), clean(r.get("game_id")), clean(r.get("team"))))
    hold.sort(key=lambda r: (int(r.get("week") or 0), clean(r.get("game_id")), clean(r.get("team"))))

    qb_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    team_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    def_hist: dict[str, list[dict[str, Any]]] = defaultdict(list)
    league_hist: list[dict[str, Any]] = []

    for row in dev:
        team = clean(row.get("team")).upper()
        opp = clean(row.get("_opponent")).upper()
        qid = clean(row.get("observed_start_qb_gsis_id"))
        if not team or not opp or not qid:
            raise ValueError("development history row missing identity/context")
        record = dict(row)
        qb_hist[qid].append(record)
        team_hist[team].append(record)
        def_hist[opp].append(record)
        league_hist.append(record)

    batches: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in hold:
        batches[int(row.get("week") or 0)].append(row)

    out: list[HoldoutExample] = []
    for week in sorted(batches):
        batch = sorted(batches[week], key=lambda r: (clean(r.get("game_id")), clean(r.get("team"))))
        for row in batch:
            gid = clean(row.get("game_id")); team = clean(row.get("team")).upper()
            opp = clean(row.get("_opponent")).upper(); qid = clean(row.get("observed_start_qb_gsis_id"))
            if not gid or not team or not opp or not qid:
                raise ValueError(f"holdout row missing identity/context: {gid} {team} {qid}")
            home = int(row.get("_home") or 0)
            qh = qb_hist[qid]; th = team_hist[team]; dh = def_hist[opp]
            fmap: dict[str, float | None] = {
                "home": float(home),
                "week": float(week),
                "qb_prior_games": float(len(qh)),
                "qb_same_team_last_game": 1.0 if qh and clean(qh[-1].get("team")).upper() == team else 0.0,
                "team_prior_games": float(len(th)),
                "def_prior_games": float(len(dh)),
            }
            league_prior = _mean(league_hist, "official_passing_yards")
            q20._put_with_missing(fmap, "league_prior_mean_passing_yards", league_prior)

            qb_windows = {
                "last4": q20._window(qh, n=4),
                "last8": q20._window(qh, n=8),
                "prior_season": q20._window(qh, season=HOLDOUT_SEASON - 1),
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
                raise ValueError(f"holdout feature contract drift missing={missing} extra={extra}")
            last4 = q20.qb_summary(q20._window(qh, n=4))["passing_yards"]
            baseline = last4 if last4 is not None else league_prior
            if baseline is None:
                raise ValueError("holdout baseline unavailable despite development history")
            actual = row.get("official_passing_yards")
            if actual is None:
                raise ValueError(f"holdout target missing official_passing_yards: {gid} {team}")
            out.append(HoldoutExample(
                season=HOLDOUT_SEASON,
                week=week,
                game_id=gid,
                team=team,
                opponent=opp,
                qb_gsis_id=qid,
                x=tuple(fmap[n] for n in q20.FEATURE_NAMES),
                actual_passing_yards=float(actual),
                baseline_last4=float(baseline),
            ))

        # Admit the completed holdout week only after every row in it was featurized.
        for row in batch:
            team = clean(row.get("team")).upper(); opp = clean(row.get("_opponent")).upper()
            qid = clean(row.get("observed_start_qb_gsis_id"))
            record = dict(row)
            qb_hist[qid].append(record)
            team_hist[team].append(record)
            def_hist[opp].append(record)
            league_hist.append(record)
    return out


def interval_coverage(prediction_rows: Iterable[dict[str, Any]], residual_calibration: dict[str, Any]) -> dict[str, Any]:
    rows = list(prediction_rows)
    if not rows:
        raise ValueError("no holdout predictions for interval coverage")
    q = residual_calibration.get("quantiles") or {}
    resid = [float(r["actual_passing_yards"]) - float(r[FROZEN_CANDIDATE]) for r in rows]
    out: dict[str, Any] = {"n": len(resid), "source": residual_calibration.get("source")}
    for label, lo_key, hi_key, nominal in (("central80", "p10", "p90", 0.80), ("central90", "p05", "p95", 0.90)):
        lo = float(q[lo_key]); hi = float(q[hi_key])
        hit = sum(lo <= x <= hi for x in resid)
        out[label] = {"nominal": nominal, "covered": hit, "coveragePct": 100.0 * hit / len(resid), "residualBounds": [lo, hi]}
    return out


if __name__ == "__main__":
    print(f"NFL QB passing-yards 2025 holdout helpers {VERSION} · {LINEAGE}")

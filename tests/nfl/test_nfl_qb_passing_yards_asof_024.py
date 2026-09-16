#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
sys.path.insert(0, str(ROOT / "packages/providers/nflverse/src"))

import contract
import qb_passing_yards_bakeoff_020 as q20
import qb_passing_yards_asof_024 as q24


def row(*, season, week, game_id, team, qid, yards, attempts=30, comps=20):
    return {
        "season": season, "week": week, "game_id": game_id, "team": team,
        "observed_start_qb_gsis_id": qid,
        "official_passing_yards": float(yards), "official_attempts": float(attempts),
        "official_completions": float(comps), "official_sacks_suffered": 2.0,
        "starter_structural_dropbacks": 34.0, "structural_scrambles": 2.0,
        "team_structural_plays": 64.0, "team_structural_dropbacks": 36.0,
        "team_designed_runs": 28.0, "mean_qb_epa": 0.05, "mean_cpoe": 1.0,
    }


def main() -> int:
    promotion = {
        "version": "0.2.3",
        "status": "PROSPECTIVE_SHADOW_READY_FROZEN_0.2.1",
        "frozenCandidate": "MODEL_A_DIRECT",
        "prospectiveSeason": 2026,
        "prospectiveOutcomeRead": False,
        "marketDependency": False,
        "marketFieldsAllowed": False,
        "oddsPapiRequests": 0,
        "postHoldoutRefitPerformed": False,
        "postHoldoutReselectionPerformed": False,
        "requiresVerifiedTargetQbIdentity": True,
        "requiresAsOfPregameFeatureSnapshot": True,
        "nextGate": "BUILD_2026_ASOF_QB_PASSING_YARDS_SCORER_WITH_VERIFIED_IDENTITY",
    }
    q24.assert_promoted_spec(promotion)
    assert q24.validate_identity_source("user_verified_external") == "USER_VERIFIED_EXTERNAL"
    try:
        q24.validate_identity_source("ROSTER_GUESS")
        raise AssertionError("unverified identity source should fail")
    except ValueError:
        pass

    target = q24.build_target_context(
        game_id="2026_02_A_B", team="A", qb_gsis_id="Q1", qb_name="Quarter Back",
        identity_source="USER_VERIFIED_EXTERNAL", contract=contract,
    )
    assert target.week == 2 and target.team == "A" and target.opponent == "B" and target.home == 0

    history = q24.add_game_context([
        row(season=2025, week=17, game_id="2025_17_A_B", team="A", qid="Q1", yards=200),
        row(season=2025, week=17, game_id="2025_17_C_D", team="C", qid="Q3", yards=250),
        row(season=2026, week=1, game_id="2026_01_A_C", team="A", qid="Q1", yards=300),
        row(season=2026, week=1, game_id="2026_01_D_B", team="D", qid="Q4", yards=180),
    ], contract)
    cutoff = q24.assert_history_cutoff(history, 2)
    assert cutoff["prior2026Rows"] == 2
    assert cutoff["max2026HistoryWeek"] == 1

    ex = q24.build_asof_feature_row(history, target, q20)
    idx = {n: i for i, n in enumerate(q20.FEATURE_NAMES)}
    assert abs(float(ex.x[idx["qb_last4_passing_yards"]]) - 250.0) < 1e-9
    assert abs(float(ex.x[idx["qb_prior_season_passing_yards"]]) - 200.0) < 1e-9
    assert abs(ex.baseline_last4 - 250.0) < 1e-9
    assert ex.qb_prior_games == 2
    assert ex.max_2026_history_week == 1

    bad = list(history) + q24.add_game_context([
        row(season=2026, week=2, game_id="2026_02_C_D", team="C", qid="Q3", yards=999),
    ], contract)
    try:
        q24.assert_history_cutoff(bad, 2)
        raise AssertionError("target-week history should fail")
    except ValueError:
        pass

    dist = q24.predictive_distribution(250.0, {
        "source": "chronological OOF",
        "n": 100,
        "meanResidualActualMinusPrediction": 1.0,
        "sigma": 75.0,
        "quantiles": {"p05": -100.0, "p10": -50.0, "p25": -20.0, "p50": 1.0, "p75": 25.0, "p90": 60.0, "p95": 110.0},
    })
    assert dist["central80"] == [200.0, 310.0]
    assert dist["central90"] == [150.0, 360.0]

    print("PASS NFL QB Model 0.2.4 as-of scorer contracts · verified identity required · target-week leakage blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))

import qb_passing_yards_bakeoff_020 as q20
import qb_passing_yards_holdout_022 as q22


def row(*, season, week, game_id, team, opp, qid, yards, attempts=30, comps=20, home=0):
    return {
        "season": season, "week": week, "game_id": game_id, "team": team,
        "_opponent": opp, "_home": home, "observed_start_qb_gsis_id": qid,
        "official_passing_yards": float(yards), "official_attempts": float(attempts),
        "official_completions": float(comps), "official_sacks_suffered": 2.0,
        "starter_structural_dropbacks": 34.0, "structural_scrambles": 2.0,
        "team_structural_plays": 64.0, "team_structural_dropbacks": 36.0,
        "team_designed_runs": 28.0, "mean_qb_epa": 0.05, "mean_cpoe": 1.0,
    }


def main() -> int:
    freeze = {
        "version": "0.2.1",
        "status": "DEVELOPMENT_FROZEN_AWAITING_SINGLE_2025_HOLDOUT",
        "frozenCandidate": "MODEL_A_DIRECT",
        "sealedHoldoutSeason": 2025,
        "holdoutOpened": False,
        "holdoutLabelsAdmitted": 0,
        "prospectiveRead": False,
        "marketDependency": False,
        "marketFieldsAllowed": False,
        "oddsPapiRequests": 0,
        "selectionAfterHoldoutAllowed": False,
        "refitAfterHoldoutAllowed": False,
    }
    manifest = {
        "nextGate": "RUN_SINGLE_2025_CONFIRMATORY_HOLDOUT_WITH_FROZEN_0.2.1_ONLY",
        "holdoutOpened": False,
        "holdoutLabelsAdmitted": 0,
    }
    q22.assert_freeze_ready(freeze, manifest)

    dev = [
        row(season=2024, week=16, game_id="2024_16_A_B", team="A", opp="B", qid="Q1", yards=200),
        row(season=2024, week=16, game_id="2024_16_C_D", team="C", opp="D", qid="Q2", yards=300),
    ]
    hold = [
        row(season=2025, week=1, game_id="2025_01_A_B", team="A", opp="B", qid="Q1", yards=100),
        row(season=2025, week=1, game_id="2025_01_C_D", team="C", opp="D", qid="Q2", yards=500),
        row(season=2025, week=2, game_id="2025_02_A_B", team="A", opp="B", qid="Q1", yards=250),
    ]
    ex = q22.build_holdout_examples(dev, hold, q20)
    assert len(ex) == 3
    idx = {n: i for i, n in enumerate(q20.FEATURE_NAMES)}
    w1 = [e for e in ex if e.week == 1]
    assert len(w1) == 2
    # Both Week 1 rows must see only the same pre-2025 league history.
    lp0 = w1[0].x[idx["league_prior_mean_passing_yards"]]
    lp1 = w1[1].x[idx["league_prior_mean_passing_yards"]]
    assert lp0 == lp1 == 250.0
    # Week 2 may admit both completed Week 1 rows: mean=(200+300+100+500)/4=275.
    w2 = next(e for e in ex if e.week == 2)
    assert w2.x[idx["league_prior_mean_passing_yards"]] == 275.0
    assert w1[0].baseline_last4 == 200.0
    assert w2.baseline_last4 == 150.0

    cal = {"source": "x", "quantiles": {"p05": -100, "p10": -50, "p90": 50, "p95": 100}}
    cov = q22.interval_coverage([
        {"actual_passing_yards": 210.0, "MODEL_A_DIRECT": 200.0},
        {"actual_passing_yards": 400.0, "MODEL_A_DIRECT": 200.0},
    ], cal)
    assert cov["central80"]["covered"] == 1
    assert cov["central90"]["covered"] == 1

    try:
        q22.assert_holdout_rows([{"season": 2024}])
        raise AssertionError("2024 should be rejected")
    except ValueError:
        pass

    print("PASS NFL QB Model 0.2.2 holdout contracts · same-week leakage blocked · frozen-candidate only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

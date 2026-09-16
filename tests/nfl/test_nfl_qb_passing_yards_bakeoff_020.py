#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
import qb_passing_yards_bakeoff_020 as q


def row(game_id, season, week, team, opp, home, qb, yards, attempts, completions):
    return {
        "game_id": game_id, "season": season, "week": week, "team": team,
        "_opponent": opp, "_home": home, "observed_start_qb_gsis_id": qb,
        "official_passing_yards": float(yards), "official_attempts": float(attempts),
        "official_completions": float(completions), "official_sacks_suffered": 2.0,
        "structural_scrambles": 2.0, "starter_structural_dropbacks": float(attempts + 4),
        "team_structural_plays": 60.0, "team_structural_dropbacks": 38.0,
        "team_designed_runs": 22.0, "mean_qb_epa": 0.1, "mean_cpoe": 1.5,
    }


def main() -> int:
    assert q.assert_exact_development_window(range(2016, 2025)) == tuple(range(2016, 2025))
    try:
        q.assert_development_only([2025])
    except ValueError:
        pass
    else:
        raise AssertionError("sealed 2025 must be rejected")

    rows = [
        row("2016_01_A_B", 2016, 1, "A", "B", 0, "Q1", 100, 20, 12),
        row("2016_01_A_B", 2016, 1, "B", "A", 1, "Q2", 200, 30, 20),
        row("2016_02_B_A", 2016, 2, "A", "B", 1, "Q1", 140, 24, 15),
        row("2016_02_B_A", 2016, 2, "B", "A", 0, "Q2", 180, 28, 18),
    ]
    ex = q.build_examples(rows)
    assert len(ex) == 4
    idx = {name: i for i, name in enumerate(q.FEATURE_NAMES)}

    # Same-week results are never admitted into one another's pregame feature state.
    assert ex[0].x[idx["league_prior_mean_passing_yards"]] is None
    assert ex[1].x[idx["league_prior_mean_passing_yards"]] is None
    assert ex[0].x[idx["qb_last4_passing_yards"]] is None
    assert ex[1].x[idx["qb_last4_passing_yards"]] is None

    # Week 2 sees Week 1 only.
    week2_q1 = next(e for e in ex if e.week == 2 and e.qb_gsis_id == "Q1")
    week2_q2 = next(e for e in ex if e.week == 2 and e.qb_gsis_id == "Q2")
    assert abs(float(week2_q1.x[idx["qb_last4_passing_yards"]]) - 100.0) < 1e-9
    assert abs(float(week2_q2.x[idx["qb_last4_passing_yards"]]) - 200.0) < 1e-9
    assert abs(float(week2_q1.x[idx["league_prior_mean_passing_yards"]]) - 150.0) < 1e-9
    assert week2_q1.baseline_last4_yards == 100.0

    # Closed-form fixed-L2 ridge is deterministic and handles explicit missing values.
    m = q.fit_ridge(
        [(0.0, None), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)],
        [10.0, 20.0, 30.0, 40.0],
        names=("a", "b"), l2=q.FIXED_L2,
    )
    p = m.predict((1.5, 2.5))
    assert isinstance(p, float)

    met = q.metric_summary([100.0, 200.0], [110.0, 180.0])
    assert met["n"] == 2
    assert abs(float(met["mae"]) - 15.0) < 1e-9
    assert abs(float(met["bias"]) + 5.0) < 1e-9

    assert q.CANDIDATES == (
        "MODEL_A_DIRECT", "MODEL_B_VOLUME_X_YPA", "MODEL_C_VOLUME_X_CR_X_YPC"
    )
    print("PASS NFL QB Model 0.2.0 passing-yards bakeoff contracts · same-week leakage blocked · 2025 sealed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

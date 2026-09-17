#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))

import qb_passing_yards_market_025 as q25


def main() -> int:
    score = {
        "version": "0.2.4",
        "status": "PROSPECTIVE_SHADOW_SCORE_FROZEN_0.2.1",
        "frozenCandidate": "MODEL_A_DIRECT",
        "coefficientRefitPerformed": False,
        "candidateReselectionPerformed": False,
        "targetOrLater2026OutcomeRowsAdmitted": 0,
        "marketPriceFieldsAdmitted": 0,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "nextGate": "WIRE_VERIFIED_IDENTITY_BRIDGE_AND_MARKET_LINE_PROBABILITY_WITHOUT_REFIT",
        "target": {
            "game_id": "2026_02_CIN_HOU",
            "qb_gsis_id": "00-0036442",
            "identitySource": "DIRECT_SPORTSBOOK_MARKET",
        },
    }
    q25.assert_score_ready(score)
    bad = dict(score); bad["targetOrLater2026OutcomeRowsAdmitted"] = 1
    try:
        q25.assert_score_ready(bad)
        raise AssertionError("prospective leakage should fail")
    except ValueError:
        pass

    assert q25.assert_half_yard_line(250.5) == 250.5
    for bad_line in (250.0, 250.25):
        try:
            q25.assert_half_yard_line(bad_line)
            raise AssertionError("non-half-yard line should fail")
        except ValueError:
            pass

    assert abs(q25.american_to_decimal(-110) - 1.9090909090909092) < 1e-12
    assert abs(q25.american_to_decimal(+120) - 2.2) < 1e-12
    assert abs(q25.implied_probability(-110) - (110/210)) < 1e-12
    assert q25.fair_american(0.5) == -100
    assert q25.fair_american(0.4) == 150

    nv = q25.no_vig_two_way(-110, -110)
    assert abs(nv["overNoVig"] - 0.5) < 1e-12
    assert abs(nv["underNoVig"] - 0.5) < 1e-12
    assert nv["hold"] > 0

    oof = [
        {"season": 2020, "game_id": "G1", "actual_passing_yards": 220, "MODEL_A_DIRECT": 200},
        {"season": 2020, "game_id": "G1", "actual_passing_yards": 180, "MODEL_A_DIRECT": 200},
        {"season": 2021, "game_id": "G2", "actual_passing_yards": 210, "MODEL_A_DIRECT": 200},
        {"season": 2021, "game_id": "G2", "actual_passing_yards": 190, "MODEL_A_DIRECT": 200},
    ]
    residuals = q25.residual_rows(oof)
    p = q25.empirical_market_probability(residuals, 200.0, 200.5)
    # Residuals +20,-20,+10,-10: two of four clear 200.5.
    assert abs(p["overProbability"] - 0.5) < 1e-12
    assert p["pushProbability"] == 0.0
    boot = q25.cluster_bootstrap_probability(residuals, 200.0, 200.5, reps=100, seed=7)
    assert abs(boot["overProbability"] - 0.5) < 1e-12
    assert 0 <= boot["overCi95"][0] <= boot["overCi95"][1] <= 1

    side = q25.market_side_summary(0.60, -110, 0.50)
    assert side["expectedRoiPct"] > 0
    assert abs(side["edgeVsNoVigProbabilityPoints"] - 10.0) < 1e-9

    print("PASS NFL QB Model 0.2.5 market contracts · frozen OOF probability · half-yard settlement only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

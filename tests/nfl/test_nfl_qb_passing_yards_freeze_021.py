#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))

import qb_passing_yards_freeze_021 as q


class Dummy:
    names = ("a", "b")
    means = [1.0, 2.0]
    scales = [2.0, 4.0]
    intercept = 10.0
    coefficients = [3.0, -2.0]
    l2 = 0.1
    def predict(self, x):
        z0 = ((self.means[0] if x[0] is None else float(x[0])) - self.means[0]) / self.scales[0]
        z1 = ((self.means[1] if x[1] is None else float(x[1])) - self.means[1]) / self.scales[1]
        return self.intercept + self.coefficients[0] * z0 + self.coefficients[1] * z1


def main() -> int:
    payload = q.serialize_ridge(Dummy())
    for x in ((1.0, 2.0), (3.0, 6.0), (None, 10.0)):
        a = Dummy().predict(x)
        b = q.predict_serialized_ridge(payload, x)
        assert abs(a - b) < 1e-12

    assert q.holdout_disposition(-2.0, (-4.0, -0.2)) == "CONFIRMATORY_HOLDOUT_PASS"
    assert q.holdout_disposition(-2.0, (-4.0, 0.5)) == "DIRECTIONAL_HOLDOUT_PASS"
    assert q.holdout_disposition(0.0, (-1.0, 1.0)) == "HOLDOUT_FAIL"
    assert q.holdout_disposition(1.0, (-1.0, 3.0)) == "HOLDOUT_FAIL"

    good_report = {
        "version": "0.2.0", "holdoutOpened": False, "holdoutLabelsAdmitted": 0,
        "prospectiveRead": False, "marketDependency": False, "marketFieldsAdmitted": 0,
        "oddsPapiRequests": 0, "frozenOmegaMutation": False,
        "selection": {"selectionStatus": "DEVELOPMENT_LEADER_SUPPORTED", "developmentLeader": "MODEL_A_DIRECT"},
        "nextGate": "FREEZE_DEVELOPMENT_LEADER_BEFORE_SINGLE_2025_HOLDOUT",
    }
    good_spec = {
        "status": "DEVELOPMENT_CHALLENGER_NOT_FROZEN", "target": "official_passing_yards",
        "identityMode": "CONDITIONAL_ON_KNOWN_QB_GSIS_ID", "marketFieldsAllowed": False,
        "oddsPapiRequests": 0, "sealedHoldoutSeason": 2025,
    }
    q.assert_freeze_authorized(good_report, good_spec)

    bad = dict(good_report); bad["holdoutOpened"] = True
    try:
        q.assert_freeze_authorized(bad, good_spec)
        raise AssertionError("opened holdout must fail closed")
    except ValueError:
        pass

    bad = dict(good_report); bad["selection"] = {"selectionStatus": "DEVELOPMENT_LEADER_SUPPORTED", "developmentLeader": "MODEL_B_VOLUME_X_YPA"}
    try:
        q.assert_freeze_authorized(bad, good_spec)
        raise AssertionError("leader drift must fail closed")
    except ValueError:
        pass

    rows = [
        {"actual_passing_yards": 100.0, "MODEL_A_DIRECT": 90.0},
        {"actual_passing_yards": 120.0, "MODEL_A_DIRECT": 130.0},
        {"actual_passing_yards": 110.0, "MODEL_A_DIRECT": 110.0},
    ]
    cal = q.residual_calibration(rows)
    assert cal["n"] == 3
    assert abs(cal["meanResidualActualMinusPrediction"]) < 1e-12

    print("PASS NFL QB Model 0.2.1 freeze contracts · leader locked · holdout policy preregistered · 2025 seal enforced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))

import qb_passing_yards_promotion_023 as q23


def good_holdout():
    return {
        "version":"0.2.2.1","holdoutDisposition":"CONFIRMATORY_HOLDOUT_PASS",
        "holdoutLabelsAdmitted":544,"officialJoinCoveragePct":100.0,
        "modelRefitPerformed":False,"candidateReselectionPerformed":False,
        "prospectiveRead":False,"marketDependency":False,"marketFieldsAdmitted":0,
        "oddsPapiRequests":0,"frozenOmegaMutation":False,
        "nextGate":"REVIEW_HOLDOUT_DISPOSITION_BEFORE_ANY_POST_HOLDOUT_REFIT_OR_PROSPECTIVE_PROMOTION",
    }


def good_freeze():
    return {
        "version":"0.2.1","frozenCandidate":"MODEL_A_DIRECT",
        "marketDependency":False,"marketFieldsAllowed":False,"oddsPapiRequests":0,
        "prospectiveRead":False,
    }


def main() -> int:
    q23.assert_promotable(good_holdout(),good_freeze(),"HOLDOUT_NEVER_FIT")
    for mutate in (
        lambda h: h.update(holdoutDisposition="DIRECTIONAL_HOLDOUT_PASS"),
        lambda h: h.update(modelRefitPerformed=True),
        lambda h: h.update(prospectiveRead=True),
    ):
        h=good_holdout(); mutate(h)
        try:
            q23.assert_promotable(h,good_freeze(),"HOLDOUT_NEVER_FIT")
            raise AssertionError("invalid promotion source should fail")
        except ValueError:
            pass
    try:
        q23.assert_promotable(good_holdout(),good_freeze(),"DEVELOPMENT_CANDIDATE")
        raise AssertionError("holdout role drift should fail")
    except ValueError:
        pass
    s=q23.promotion_status()
    assert s["coefficientRefitAfterHoldout"] is False
    assert s["holdoutSeasonUsedForCoefficientFit"] is False
    assert s["holdoutSeasonMayBeLaggedFeatureHistoryFor2026"] is True
    assert s["marketExecutionEligible"] is False
    print("PASS NFL QB Model 0.2.3 promotion contracts · confirmatory pass required · 2025 remains no-fit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

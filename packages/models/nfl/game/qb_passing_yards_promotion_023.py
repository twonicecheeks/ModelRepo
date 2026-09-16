"""NFL QB Model 0.2.3 — confirmatory-pass prospective shadow promotion.

This layer promotes the already-frozen 0.2.1 MODEL_A_DIRECT to 2026 prospective
shadow use after the preregistered 2025 confirmatory holdout passed. It does NOT
refit on 2025, does NOT change features/L2/residual calibration, and does NOT read
2026 outcomes or markets.

The repository-wide nflverse contract still classifies 2025 as HOLDOUT_NEVER_FIT.
0.2.3 preserves that contract deliberately: 2025 may be used later as lagged feature
history for 2026 scoring, but not as a coefficient-fit season on this frozen track.
"""
from __future__ import annotations

from typing import Any

VERSION = "0.2.3"
LINEAGE = "nfl-qb-passing-yards-confirmatory-promotion-v0.2.3-2026-09-16"
SOURCE_HOLDOUT_VERSION = "0.2.2.1"
SOURCE_FREEZE_VERSION = "0.2.1"
FROZEN_CANDIDATE = "MODEL_A_DIRECT"
PROSPECTIVE_SEASON = 2026
EXPECTED_HOLDOUT_ROLE = "HOLDOUT_NEVER_FIT"


def assert_promotable(holdout: dict[str, Any], freeze: dict[str, Any], holdout_role: str) -> None:
    if str(holdout.get("version")) != SOURCE_HOLDOUT_VERSION:
        raise ValueError("QB 0.2.3 holdout version drift")
    if holdout.get("holdoutDisposition") != "CONFIRMATORY_HOLDOUT_PASS":
        raise ValueError("QB 0.2.3 requires CONFIRMATORY_HOLDOUT_PASS")
    if int(holdout.get("holdoutLabelsAdmitted") or 0) <= 0 or float(holdout.get("officialJoinCoveragePct") or 0.0) != 100.0:
        raise ValueError("QB 0.2.3 requires complete scored holdout")
    if holdout.get("modelRefitPerformed") is not False or holdout.get("candidateReselectionPerformed") is not False:
        raise ValueError("QB 0.2.3 refuses mutated holdout evaluation")
    if holdout.get("prospectiveRead") is not False:
        raise ValueError("QB 0.2.3 refuses source that already read 2026 outcomes")
    if holdout.get("marketDependency") is not False or int(holdout.get("marketFieldsAdmitted") or 0) != 0:
        raise ValueError("QB 0.2.3 refuses market-contaminated holdout")
    if int(holdout.get("oddsPapiRequests") or 0) != 0 or holdout.get("frozenOmegaMutation") is not False:
        raise ValueError("QB 0.2.3 market/OMEGA integrity drift")
    if holdout.get("nextGate") != "REVIEW_HOLDOUT_DISPOSITION_BEFORE_ANY_POST_HOLDOUT_REFIT_OR_PROSPECTIVE_PROMOTION":
        raise ValueError("QB 0.2.3 holdout next-gate drift")

    if str(freeze.get("version")) != SOURCE_FREEZE_VERSION:
        raise ValueError("QB 0.2.3 frozen source version drift")
    if freeze.get("frozenCandidate") != FROZEN_CANDIDATE:
        raise ValueError("QB 0.2.3 frozen candidate drift")
    if freeze.get("marketDependency") is not False or bool(freeze.get("marketFieldsAllowed")):
        raise ValueError("QB 0.2.3 frozen source market drift")
    if int(freeze.get("oddsPapiRequests") or 0) != 0:
        raise ValueError("QB 0.2.3 frozen source OddsPapi drift")
    if freeze.get("prospectiveRead") is not False:
        raise ValueError("QB 0.2.3 frozen source prospective boundary drift")

    if str(holdout_role) != EXPECTED_HOLDOUT_ROLE:
        raise ValueError(f"QB 0.2.3 requires repository holdout role {EXPECTED_HOLDOUT_ROLE}; got {holdout_role}")


def promotion_status() -> dict[str, Any]:
    return {
        "status": "PROSPECTIVE_SHADOW_READY_FROZEN_0.2.1",
        "frozenCandidate": FROZEN_CANDIDATE,
        "coefficientRefitAfterHoldout": False,
        "candidateReselectionAfterHoldout": False,
        "featureContractChanged": False,
        "l2Changed": False,
        "residualCalibrationChanged": False,
        "holdoutSeasonUsedForCoefficientFit": False,
        "holdoutSeasonMayBeLaggedFeatureHistoryFor2026": True,
        "prospectiveSeason": PROSPECTIVE_SEASON,
        "prospectiveOutcomeRead": False,
        "marketExecutionEligible": False,
        "requiresVerifiedTargetQbIdentity": True,
        "requiresAsOfPregameFeatureSnapshot": True,
    }


if __name__ == "__main__":
    print(f"NFL QB passing-yards promotion {VERSION} · {LINEAGE}")

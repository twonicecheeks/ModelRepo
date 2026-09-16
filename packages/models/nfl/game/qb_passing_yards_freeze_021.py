"""NFL QB Model 0.2.1 — immutable development freeze helpers.

This layer freezes the 0.2.0 development winner before any 2025 holdout is opened.
It does not read holdout/prospective rows and does not touch markets or OMEGA.

The frozen candidate is MODEL_A_DIRECT only. Candidate selection is over after this
freeze. The single 2025 holdout is reserved for confirmatory evaluation of this one
candidate versus the predeclared last-four benchmark.
"""
from __future__ import annotations

from dataclasses import asdict
from math import sqrt
from statistics import fmean
from typing import Any, Iterable, Sequence

VERSION = "0.2.1"
LINEAGE = "nfl-qb-passing-yards-development-freeze-v0.2.1-2026-09-16"
SOURCE_MODEL_VERSION = "0.2.0"
FROZEN_CANDIDATE = "MODEL_A_DIRECT"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
HOLDOUT_BOOTSTRAP_REPS = 2000
HOLDOUT_BOOTSTRAP_SEED = 20260917

HOLDOUT_EVALUATION_POLICY = {
    "candidate": FROZEN_CANDIDATE,
    "primaryMetric": "MAE",
    "benchmark": "QB last-4 official passing-yards mean; fallback strictly prior league mean",
    "cluster": "game_id",
    "bootstrapReps": HOLDOUT_BOOTSTRAP_REPS,
    "bootstrapSeed": HOLDOUT_BOOTSTRAP_SEED,
    "confirmatoryPass": "candidate MAE < benchmark MAE AND game-cluster bootstrap 95% CI for candidate-minus-benchmark MAE is entirely below 0",
    "directionalPass": "candidate MAE < benchmark MAE but bootstrap 95% CI includes 0",
    "holdoutFail": "candidate MAE >= benchmark MAE",
    "secondaryMetrics": ["RMSE", "bias", "medianAbsoluteError", "frozen OOF residual interval coverage"],
    "selectionAfterHoldoutAllowed": False,
    "refitAfterHoldoutAllowed": False,
}


def assert_freeze_authorized(report: dict[str, Any], spec: dict[str, Any]) -> None:
    if str(report.get("version")) != SOURCE_MODEL_VERSION:
        raise ValueError("QB 0.2.1 source report version drift")
    if report.get("holdoutOpened") is not False or int(report.get("holdoutLabelsAdmitted") or 0) != 0:
        raise ValueError("QB 0.2.1 refuses source with opened 2025 holdout")
    if report.get("prospectiveRead") is not False:
        raise ValueError("QB 0.2.1 refuses source with prospective outcomes read")
    if report.get("marketDependency") is not False or int(report.get("marketFieldsAdmitted") or 0) != 0:
        raise ValueError("QB 0.2.1 refuses market-contaminated source")
    if int(report.get("oddsPapiRequests") or 0) != 0 or report.get("frozenOmegaMutation") is not False:
        raise ValueError("QB 0.2.1 market/OMEGA integrity drift")
    sel = report.get("selection") or {}
    if sel.get("selectionStatus") != "DEVELOPMENT_LEADER_SUPPORTED":
        raise ValueError("QB 0.2.0 development leader was not supported")
    if sel.get("developmentLeader") != FROZEN_CANDIDATE:
        raise ValueError("QB 0.2.1 frozen candidate does not match development leader")
    if report.get("nextGate") != "FREEZE_DEVELOPMENT_LEADER_BEFORE_SINGLE_2025_HOLDOUT":
        raise ValueError("QB 0.2.0 next-gate contract drift")
    if spec.get("status") != "DEVELOPMENT_CHALLENGER_NOT_FROZEN":
        raise ValueError("QB 0.2.0 source spec status drift")
    if spec.get("target") != "official_passing_yards":
        raise ValueError("QB 0.2.0 target drift")
    if spec.get("identityMode") != "CONDITIONAL_ON_KNOWN_QB_GSIS_ID":
        raise ValueError("QB 0.2.0 identity mode drift")
    if bool(spec.get("marketFieldsAllowed")) or int(spec.get("oddsPapiRequests") or 0) != 0:
        raise ValueError("QB 0.2.0 source spec market drift")
    if int(spec.get("sealedHoldoutSeason") or 0) != SEALED_HOLDOUT_SEASON:
        raise ValueError("QB 0.2.0 holdout season drift")


def serialize_ridge(model: Any) -> dict[str, Any]:
    return {
        "type": "RIDGE_REGRESSOR",
        "featureNames": list(model.names),
        "means": [float(x) for x in model.means],
        "scales": [float(x) for x in model.scales],
        "intercept": float(model.intercept),
        "coefficients": [float(x) for x in model.coefficients],
        "l2": float(model.l2),
    }


def predict_serialized_ridge(payload: dict[str, Any], x: Sequence[float | None]) -> float:
    names = tuple(payload.get("featureNames") or ())
    means = [float(v) for v in payload.get("means") or ()]
    scales = [float(v) for v in payload.get("scales") or ()]
    coefs = [float(v) for v in payload.get("coefficients") or ()]
    if not names or len(x) != len(names) or len(means) != len(names) or len(scales) != len(names) or len(coefs) != len(names):
        raise ValueError("frozen ridge dimension mismatch")
    z = [((means[i] if v is None else float(v)) - means[i]) / scales[i] for i, v in enumerate(x)]
    return float(payload["intercept"]) + sum(a * b for a, b in zip(coefs, z))


def residual_calibration(rows: Iterable[dict[str, Any]], prediction_field: str = FROZEN_CANDIDATE) -> dict[str, Any]:
    vals = sorted(float(r["actual_passing_yards"]) - float(r[prediction_field]) for r in rows)
    if not vals:
        raise ValueError("no OOF residuals for frozen calibration")
    mean = fmean(vals)
    sigma = sqrt(fmean((x - mean) ** 2 for x in vals)) if len(vals) > 1 else 0.0
    def q(p: float) -> float:
        idx = int(round((len(vals) - 1) * p))
        return vals[max(0, min(len(vals) - 1, idx))]
    return {
        "source": "chronological OOF 2020-2024 only",
        "n": len(vals),
        "meanResidualActualMinusPrediction": mean,
        "sigma": sigma,
        "quantiles": {k: q(p) for k, p in (("p05", .05), ("p10", .10), ("p25", .25), ("p50", .50), ("p75", .75), ("p90", .90), ("p95", .95))},
    }


def holdout_disposition(delta_mae: float, ci95: Sequence[float]) -> str:
    if len(ci95) != 2:
        raise ValueError("holdout CI must have two endpoints")
    d = float(delta_mae); hi = float(ci95[1])
    if d < 0.0 and hi < 0.0:
        return "CONFIRMATORY_HOLDOUT_PASS"
    if d < 0.0:
        return "DIRECTIONAL_HOLDOUT_PASS"
    return "HOLDOUT_FAIL"


if __name__ == "__main__":
    print(f"NFL QB passing-yards freeze {VERSION} · {LINEAGE}")

"""NFL QB Model 0.2.7 — direct-market shadow ledger helpers.

This layer is downstream of the frozen 0.2.4 score and 0.2.5 probability bridge.
It records direct sportsbook observations immutably, classifies quote freshness,
computes shadow-only EV diagnostics, and links repeated observations for later CLV.
It never refits/reselects the QB model and never authorizes execution.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

VERSION = "0.2.7"
LINEAGE = "nfl-qb-passing-yards-direct-market-shadow-ledger-v0.2.7-2026-09-16"
SOURCE_SCORE_VERSION = "0.2.4"
FROZEN_CANDIDATE = "MODEL_A_DIRECT"
FRESH_SECONDS = 15 * 60
AGING_SECONDS = 60 * 60
FUTURE_TOLERANCE_SECONDS = 5 * 60
ALLOWED_VERIFICATION_METHODS = frozenset({
    "DIRECT_BOOK_APP",
    "DIRECT_BOOK_WEB",
    "DIRECT_BOOK_API",
    "USER_ATTESTED_DIRECT_BOOK",
})
ALLOWED_AVAILABILITY = frozenset({
    "EXECUTABLE_TO_USER",
    "DISPLAYED_DIRECT",
    "UNKNOWN",
})


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_object(obj: Any) -> str:
    return sha256(canonical_bytes(obj)).hexdigest()


def parse_aware_timestamp(text: str) -> datetime:
    raw = clean(text)
    if not raw:
        raise ValueError("direct market capture requires an explicit captured-at timestamp")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 captured-at timestamp: {text}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("captured-at must include a timezone offset or Z")
    return dt


def classify_freshness(captured_at: str, observed_at: datetime | None = None) -> dict[str, Any]:
    captured = parse_aware_timestamp(captured_at)
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    age = (observed.astimezone(timezone.utc) - captured.astimezone(timezone.utc)).total_seconds()
    if age < -FUTURE_TOLERANCE_SECONDS:
        raise ValueError(f"captured-at is too far in the future: ageSeconds={age:.1f}")
    age_for_class = max(0.0, age)
    if age_for_class <= FRESH_SECONDS:
        status = "FRESH_DIRECT"
    elif age_for_class <= AGING_SECONDS:
        status = "AGING_DIRECT"
    else:
        status = "STALE_DIRECT"
    return {
        "capturedAt": captured.isoformat(),
        "observedAt": observed.astimezone(timezone.utc).isoformat(),
        "ageSeconds": age,
        "freshnessStatus": status,
        "freshThresholdSeconds": FRESH_SECONDS,
        "agingThresholdSeconds": AGING_SECONDS,
    }


def validate_direct_metadata(verification_method: str, availability_status: str) -> tuple[str, str]:
    verification = clean(verification_method).upper()
    availability = clean(availability_status).upper()
    if verification not in ALLOWED_VERIFICATION_METHODS:
        raise ValueError(f"unsupported direct verification method: {verification_method}")
    if availability not in ALLOWED_AVAILABILITY:
        raise ValueError(f"unsupported availability status: {availability_status}")
    return verification, availability


def capture_payload(
    *,
    target: dict[str, Any],
    book: str,
    line: float,
    over_price: int,
    under_price: int,
    captured_at: str,
    verification_method: str,
    availability_status: str,
    evidence_filename: str = "",
    evidence_sha256: str = "",
) -> dict[str, Any]:
    verification, availability = validate_direct_metadata(verification_method, availability_status)
    book_clean = clean(book)
    if not book_clean:
        raise ValueError("direct market capture requires book")
    game_id = clean(target.get("game_id"))
    qb_id = clean(target.get("qb_gsis_id"))
    if not game_id or not qb_id:
        raise ValueError("direct market capture requires complete target identity")
    captured = parse_aware_timestamp(captured_at)
    return {
        "schemaVersion": "NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_0.2.7",
        "source": "DIRECT_SPORTSBOOK_CAPTURE",
        "marketKind": "passing_yards",
        "target": {
            "game_id": game_id,
            "team": clean(target.get("team")),
            "opponent": clean(target.get("opponent")),
            "qb_gsis_id": qb_id,
            "qb_name": clean(target.get("qb_name")),
        },
        "book": book_clean,
        "line": float(line),
        "overAmerican": int(over_price),
        "underAmerican": int(under_price),
        "capturedAt": captured.isoformat(),
        "verificationMethod": verification,
        "availabilityStatus": availability,
        "evidence": {
            "filename": clean(evidence_filename),
            "sha256": clean(evidence_sha256),
        },
        "containsModelFields": False,
        "referenceOnly": False,
    }


def shadow_status(shadow_disposition: str, freshness_status: str, availability_status: str) -> str:
    disp = clean(shadow_disposition).upper()
    freshness = clean(freshness_status).upper()
    availability = clean(availability_status).upper()
    if freshness == "STALE_DIRECT":
        return "STALE_MARKET_REFERENCE"
    if availability == "UNKNOWN":
        return "DIRECT_AVAILABILITY_UNCONFIRMED"
    if disp == "ROBUST_POSITIVE_SHADOW":
        return "FRESH_ROBUST_POSITIVE_SHADOW" if freshness == "FRESH_DIRECT" else "AGING_ROBUST_POSITIVE_SHADOW"
    if disp == "POINT_POSITIVE_SHADOW":
        return "FRESH_POINT_POSITIVE_SHADOW" if freshness == "FRESH_DIRECT" else "AGING_POINT_POSITIVE_SHADOW"
    if disp == "NEGATIVE_EV_SHADOW":
        return "FRESH_NEGATIVE_EV_SHADOW" if freshness == "FRESH_DIRECT" else "AGING_NEGATIVE_EV_SHADOW"
    return "DIRECT_SHADOW_UNCLASSIFIED"


def movement_summary(current: dict[str, Any], previous: dict[str, Any] | None, q25: Any) -> dict[str, Any]:
    if previous is None:
        return {"hasPreviousSameBookCapture": False}
    cur_over = int(current["overAmerican"])
    cur_under = int(current["underAmerican"])
    prev_over = int(previous["overAmerican"])
    prev_under = int(previous["underAmerican"])
    return {
        "hasPreviousSameBookCapture": True,
        "previousCapturedAt": previous["capturedAt"],
        "previousLine": float(previous["line"]),
        "previousOverAmerican": prev_over,
        "previousUnderAmerican": prev_under,
        "lineDelta": float(current["line"]) - float(previous["line"]),
        "overRawImpliedProbabilityDelta": q25.implied_probability(cur_over) - q25.implied_probability(prev_over),
        "underRawImpliedProbabilityDelta": q25.implied_probability(cur_under) - q25.implied_probability(prev_under),
        "interpretation": "DESCRIPTIVE_MARKET_MOVEMENT_ONLY_NO_SHARP_MONEY_CLAIM",
    }


def clv_tracking_eligible(freshness_status: str, availability_status: str) -> bool:
    return clean(freshness_status).upper() in {"FRESH_DIRECT", "AGING_DIRECT"} and clean(availability_status).upper() in {
        "EXECUTABLE_TO_USER", "DISPLAYED_DIRECT"
    }


if __name__ == "__main__":
    print(f"NFL QB passing-yards direct shadow ledger {VERSION} · {LINEAGE}")

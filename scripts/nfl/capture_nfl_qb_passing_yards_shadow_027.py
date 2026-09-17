#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid


def load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def existing_captures(root: Path) -> list[dict]:
    base = root / "data/raw/nfl/qb_passing_yards_market_027"
    rows: list[dict] = []
    if not base.exists():
        return rows
    for path in sorted(base.glob("*/NFL_QB_PASSING_YARDS_DIRECT_MARKET_CAPTURE.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"cannot read prior QB direct capture {path}: {exc}") from exc
        row = dict(row)
        row["_path"] = str(path.relative_to(root))
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture one direct sportsbook QB passing-yards quote into the immutable 0.2.7 shadow ledger")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--game-id", required=True)
    ap.add_argument("--qb-gsis-id", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--line", required=True, type=float)
    ap.add_argument("--over-price", required=True, type=int)
    ap.add_argument("--under-price", required=True, type=int)
    ap.add_argument("--captured-at", required=True, help="ISO-8601 timestamp with timezone; required for freshness/CLV audit")
    ap.add_argument(
        "--verification-method", required=True,
        choices=["DIRECT_BOOK_APP", "DIRECT_BOOK_WEB", "DIRECT_BOOK_API", "USER_ATTESTED_DIRECT_BOOK"],
    )
    ap.add_argument(
        "--availability-status", required=True,
        choices=["EXECUTABLE_TO_USER", "DISPLAYED_DIRECT", "UNKNOWN"],
    )
    ap.add_argument("--evidence-file", default="", help="optional screenshot/export file; copied into immutable raw capture and SHA256 hashed")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    sys.path.insert(0, str(model_dir))
    import qb_passing_yards_market_025 as q25
    import qb_passing_yards_board_026 as q26
    import qb_passing_yards_shadow_ledger_027 as q27

    score_ptr = root / "data/prospective/nfl/CURRENT_QB_PASSING_YARDS_024"
    freeze_ptr = root / "data/models/nfl/CURRENT_QB_MODEL_021"
    if not score_ptr.exists() or not freeze_ptr.exists():
        raise FileNotFoundError("QB 0.2.7 prerequisite score/freeze pointer missing")

    score_dir = root / score_ptr.read_text(encoding="utf-8").strip()
    score_path = score_dir / "NFL_QB_PASSING_YARDS_ASOF_SCORE.json"
    if not score_path.exists():
        raise FileNotFoundError(f"QB 0.2.4 score missing: {score_path}")
    score = json.loads(score_path.read_text(encoding="utf-8"))
    q25.assert_score_ready(score)
    target = score.get("target") or {}
    if str(target.get("game_id") or "") != str(args.game_id).strip():
        raise ValueError("direct capture target game does not match current immutable 0.2.4 score")
    if str(target.get("qb_gsis_id") or "") != str(args.qb_gsis_id).strip():
        raise ValueError("direct capture target QB does not match current immutable 0.2.4 score")

    line = q25.assert_half_yard_line(args.line)
    over_price = q25.validate_american(args.over_price)
    under_price = q25.validate_american(args.under_price)
    verification, availability = q27.validate_direct_metadata(args.verification_method, args.availability_status)

    now = datetime.now(timezone.utc)
    freshness = q27.classify_freshness(args.captured_at, now)

    evidence_path: Path | None = None
    evidence_sha = ""
    evidence_filename = ""
    if str(args.evidence_file).strip():
        evidence_path = Path(args.evidence_file).expanduser().resolve()
        if not evidence_path.exists() or not evidence_path.is_file():
            raise FileNotFoundError(f"direct-market evidence file missing: {evidence_path}")
        evidence_sha = sha256_file(evidence_path)
        evidence_filename = evidence_path.name

    raw_capture = q27.capture_payload(
        target=target,
        book=args.book,
        line=line,
        over_price=over_price,
        under_price=under_price,
        captured_at=args.captured_at,
        verification_method=verification,
        availability_status=availability,
        evidence_filename=evidence_filename,
        evidence_sha256=evidence_sha,
    )
    capture_sha = q27.sha256_object(raw_capture)

    prior = existing_captures(root)
    for row in prior:
        comparable = {k: v for k, v in row.items() if k != "_path"}
        if q27.sha256_object(comparable) == capture_sha:
            raise ValueError(f"duplicate immutable direct capture already exists: {row['_path']}")

    freeze_dir = root / freeze_ptr.read_text(encoding="utf-8").strip()
    freeze_path = freeze_dir / "NFL_QB_PASSING_YARDS_FROZEN_SPEC.json"
    freeze_manifest_path = freeze_dir / "NFL_QB_PASSING_YARDS_FREEZE_MANIFEST.json"
    if not freeze_path.exists() or not freeze_manifest_path.exists():
        raise FileNotFoundError("QB 0.2.7 frozen source missing")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    frozen_sha = hashlib.sha256(q27.canonical_bytes(freeze)).hexdigest()
    if frozen_sha != score.get("frozenSpecSha256"):
        raise ValueError("QB 0.2.7 frozen-model lineage drift")

    source_model_dir = root / str(freeze.get("sourceModelRunDirectory") or "")
    oof_path = source_model_dir / "NFL_QB_PASSING_YARDS_OOF.jsonl"
    if not oof_path.exists():
        raise FileNotFoundError(f"frozen chronological OOF source missing: {oof_path}")
    expected_oof_sha = (freeze_manifest.get("sourceHashes") or {}).get("qb020OofJsonlSha256")
    actual_oof_sha = sha256_file(oof_path)
    if not expected_oof_sha or actual_oof_sha != expected_oof_sha:
        raise ValueError("QB 0.2.7 frozen OOF residual hash drift")
    residuals = q25.residual_rows(load_jsonl(oof_path))
    if len(residuals) != int((freeze.get("residualCalibration") or {}).get("n") or 0):
        raise ValueError("QB 0.2.7 frozen residual count drift")

    point = float(score["projectionPassingYards"])
    probs = q25.empirical_market_probability(residuals, point, line)
    boot = q25.cluster_bootstrap_probability(residuals, point, line)
    if abs(float(probs["overProbability"]) - float(boot["overProbability"])) > 1e-12:
        raise ValueError("QB 0.2.7 empirical/bootstrap probability mismatch")
    no_vig = q25.no_vig_two_way(over_price, under_price)
    over = q25.market_side_summary(probs["overProbability"], over_price, no_vig["overNoVig"])
    under = q25.market_side_summary(probs["underProbability"], under_price, no_vig["underNoVig"])
    over = q26.add_probability_ci(over, boot["overCi95"], over_price, q25)
    under = q26.add_probability_ci(under, boot["underCi95"], under_price, q25)
    over["shadowDisposition"] = q26.shadow_disposition(over)
    under["shadowDisposition"] = q26.shadow_disposition(under)
    one_row = {"book": raw_capture["book"], "line": line, "sides": {"OVER": over, "UNDER": under}}
    best = q26.best_priced_side([one_row])
    assert best is not None
    direct_status = q27.shadow_status(best["shadowDisposition"], freshness["freshnessStatus"], availability)

    current_capture_dt = q27.parse_aware_timestamp(raw_capture["capturedAt"])
    target_prior = [
        r for r in prior
        if str((r.get("target") or {}).get("game_id") or "") == str(target.get("game_id") or "")
        and str((r.get("target") or {}).get("qb_gsis_id") or "") == str(target.get("qb_gsis_id") or "")
    ]
    same_book_prior = [r for r in target_prior if str(r.get("book") or "").casefold() == str(raw_capture["book"]).casefold()]
    eligible_previous = [r for r in same_book_prior if q27.parse_aware_timestamp(str(r.get("capturedAt") or "")) < current_capture_dt]
    previous = max(eligible_previous, key=lambda r: q27.parse_aware_timestamp(str(r["capturedAt"]))) if eligible_previous else None
    movement = q27.movement_summary(raw_capture, previous, q25)

    history_compact: list[dict] = []
    for r in target_prior:
        history_compact.append({
            "capturePath": r["_path"],
            "capturedAt": r.get("capturedAt"),
            "book": r.get("book"),
            "line": r.get("line"),
            "overAmerican": r.get("overAmerican"),
            "underAmerican": r.get("underAmerican"),
            "availabilityStatus": r.get("availabilityStatus"),
            "verificationMethod": r.get("verificationMethod"),
        })

    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_" + capture_sha[:8] + "_" + uuid.uuid4().hex[:4]
    raw_dir = root / "data/raw/nfl/qb_passing_yards_market_027" / run_id
    ledger_dir = root / "data/prospective/nfl/qb_passing_yards_shadow_027" / run_id
    if raw_dir.exists() or ledger_dir.exists():
        raise FileExistsError(f"QB 0.2.7 immutable run directory collision: {run_id}")

    raw_rel = raw_dir.relative_to(root) / "NFL_QB_PASSING_YARDS_DIRECT_MARKET_CAPTURE.json"
    history_compact.append({
        "capturePath": str(raw_rel),
        "capturedAt": raw_capture["capturedAt"],
        "book": raw_capture["book"],
        "line": raw_capture["line"],
        "overAmerican": raw_capture["overAmerican"],
        "underAmerican": raw_capture["underAmerican"],
        "availabilityStatus": raw_capture["availabilityStatus"],
        "verificationMethod": raw_capture["verificationMethod"],
    })
    history_compact.sort(key=lambda r: (q27.parse_aware_timestamp(str(r["capturedAt"])), str(r["book"]).casefold()))

    clv_eligible = q27.clv_tracking_eligible(freshness["freshnessStatus"], availability)
    ledger = {
        "version": q27.VERSION,
        "lineage": q27.LINEAGE,
        "createdAt": now.isoformat(),
        "runId": run_id,
        "status": "PROSPECTIVE_DIRECT_MARKET_SHADOW_LEDGER",
        "target": target,
        "projectionPassingYards": point,
        "capture": {
            "path": str(raw_rel),
            "sha256": capture_sha,
            "book": raw_capture["book"],
            "line": line,
            "overAmerican": over_price,
            "underAmerican": under_price,
            "capturedAt": raw_capture["capturedAt"],
            "verificationMethod": verification,
            "availabilityStatus": availability,
            "evidencePresent": evidence_path is not None,
            "evidenceSha256": evidence_sha or None,
        },
        "freshness": freshness,
        "probabilityModel": probs,
        "probabilityBootstrap": boot,
        "twoWayNoVig": no_vig,
        "sides": {"OVER": over, "UNDER": under},
        "bestPointEvSide": best,
        "directShadowStatus": direct_status,
        "movementVsPreviousSameBook": movement,
        "targetObservationCount": len(target_prior) + 1,
        "sameBookObservationCount": len(same_book_prior) + 1,
        "captureHistory": history_compact,
        "clvTrackingEligible": clv_eligible,
        "executionQuoteEligible": availability == "EXECUTABLE_TO_USER" and freshness["freshnessStatus"] == "FRESH_DIRECT",
        "marketExecutionEligible": False,
        "marketExecutionReason": "SHADOW_ONLY_PENDING_PROSPECTIVE_CLV_AND_SETTLEMENT_VALIDATION",
        "sourceScorePath": str(score_path.relative_to(root)),
        "sourceScoreSha256": sha256_file(score_path),
        "frozenSpecSha256": frozen_sha,
        "frozenOofResidualSourceSha256": actual_oof_sha,
        "frozenOofResidualRows": len(residuals),
        "coefficientRefitPerformed": False,
        "candidateReselectionPerformed": False,
        "marketFieldsUsedAsModelFeatures": False,
        "targetOrLater2026OutcomeRowsAdmitted": 0,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "nextGate": "ACCUMULATE_DIRECT_SHADOW_SNAPSHOTS_AND_CAPTURE_PREGAME_CLOSE_FOR_CLV_028",
    }

    raw_dir.mkdir(parents=True, exist_ok=False)
    ledger_dir.mkdir(parents=True, exist_ok=False)
    raw_path = raw_dir / "NFL_QB_PASSING_YARDS_DIRECT_MARKET_CAPTURE.json"
    raw_path.write_bytes(q27.canonical_bytes(raw_capture))
    if evidence_path is not None:
        suffix = evidence_path.suffix.lower()
        shutil.copy2(evidence_path, raw_dir / ("EVIDENCE" + suffix))
    manifest = {
        "version": q27.VERSION,
        "runId": run_id,
        "createdAt": now.isoformat(),
        "captureSha256": capture_sha,
        "captureFileSha256": sha256_file(raw_path),
        "evidenceFileSha256": evidence_sha or None,
        "containsModelFields": False,
        "source": "DIRECT_SPORTSBOOK_CAPTURE",
        "immutable": True,
        "oddsPapiRequests": 0,
    }
    (raw_dir / "NFL_QB_PASSING_YARDS_DIRECT_MARKET_CAPTURE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    ledger_path = ledger_dir / "NFL_QB_PASSING_YARDS_SHADOW_LEDGER.json"
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    atomic_pointer(root / "data/raw/nfl/CURRENT_QB_PASSING_YARDS_MARKET_027", str(raw_dir.relative_to(root)))
    atomic_pointer(root / "data/prospective/nfl/CURRENT_QB_PASSING_YARDS_SHADOW_027", str(ledger_dir.relative_to(root)))

    print("\nNFL QB MODEL 0.2.7 — DIRECT MARKET SHADOW LEDGER")
    print(f"Target: {target.get('game_id')} · {target.get('team')} vs {target.get('opponent')} · {target.get('qb_name') or target.get('qb_gsis_id')}")
    print(f"Projection: {point:.1f} yd · {raw_capture['book']} {line:.1f} · OVER {over_price:+d} · UNDER {under_price:+d}")
    print(f"Direct verification: {verification} · availability {availability}")
    print(f"Captured: {raw_capture['capturedAt']} · age {freshness['ageSeconds']:.0f}s · {freshness['freshnessStatus']}")
    print(f"OVER model {100.0*probs['overProbability']:.2f}% · EV {over['expectedRoiPct']:+.2f}% · CI [{over['expectedRoiPctCi95'][0]:+.2f}%, {over['expectedRoiPctCi95'][1]:+.2f}%] · {over['shadowDisposition']}")
    print(f"UNDER model {100.0*probs['underProbability']:.2f}% · EV {under['expectedRoiPct']:+.2f}% · CI [{under['expectedRoiPctCi95'][0]:+.2f}%, {under['expectedRoiPctCi95'][1]:+.2f}%] · {under['shadowDisposition']}")
    print(f"Direct shadow status: {direct_status}")
    if movement.get("hasPreviousSameBookCapture"):
        print(f"Movement vs prior {raw_capture['book']}: line {movement['previousLine']:.1f} -> {line:.1f} · descriptive only / no sharp-money claim")
    else:
        print(f"Movement vs prior {raw_capture['book']}: FIRST DIRECT CAPTURE")
    print(f"Target ledger observations: {len(target_prior)+1} · same book {len(same_book_prior)+1}")
    print(f"CLV tracking eligible: {'YES' if clv_eligible else 'NO'}")
    print("Market execution eligible: NO · prospective CLV + settlement validation still required")
    print(f"Raw capture: {raw_path}")
    print(f"Shadow ledger: {ledger_path}")
    print("NEXT GATE: ACCUMULATE_DIRECT_SHADOW_SNAPSHOTS_AND_CAPTURE_PREGAME_CLOSE_FOR_CLV_028")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

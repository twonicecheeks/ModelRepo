#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
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


def canonical_bytes(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare frozen NFL QB passing-yards probability to a quoted half-yard market")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--game-id", required=True, help="must match the current immutable 0.2.4 score")
    ap.add_argument("--qb-gsis-id", required=True, help="must match the current immutable 0.2.4 score")
    ap.add_argument("--line", required=True, type=float, help="passing-yards line; 0.2.5 supports half-yard lines only")
    ap.add_argument("--book", required=True, help="sportsbook/reference book label")
    ap.add_argument(
        "--market-source", required=True,
        choices=["USER_ENTERED_DIRECT_SPORTSBOOK", "DIRECT_SPORTSBOOK_CAPTURE", "PROPSMADNESS_REFERENCE"],
    )
    ap.add_argument("--over-price", type=int, default=None, help="American odds for Over at the same line")
    ap.add_argument("--under-price", type=int, default=None, help="American odds for Under at the same line")
    ap.add_argument("--captured-at", default="", help="optional ISO-8601 quote time; defaults to evaluator run time")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    sys.path.insert(0, str(model_dir))
    import qb_passing_yards_market_025 as q25

    score_ptr = root / "data/prospective/nfl/CURRENT_QB_PASSING_YARDS_024"
    promotion_ptr = root / "data/models/nfl/CURRENT_QB_MODEL_023"
    freeze_ptr = root / "data/models/nfl/CURRENT_QB_MODEL_021"
    for p in (score_ptr, promotion_ptr, freeze_ptr):
        if not p.exists():
            raise FileNotFoundError(f"QB 0.2.5 prerequisite pointer missing: {p}")

    score_dir = root / score_ptr.read_text(encoding="utf-8").strip()
    score_path = score_dir / "NFL_QB_PASSING_YARDS_ASOF_SCORE.json"
    if not score_path.exists():
        raise FileNotFoundError(f"QB 0.2.4 score missing: {score_path}")
    score = json.loads(score_path.read_text(encoding="utf-8"))
    q25.assert_score_ready(score)

    target = score.get("target") or {}
    if str(target.get("game_id") or "") != str(args.game_id).strip():
        raise ValueError(f"market target game does not match current 0.2.4 score: {args.game_id} vs {target.get('game_id')}")
    if str(target.get("qb_gsis_id") or "") != str(args.qb_gsis_id).strip():
        raise ValueError("market target QB GSIS ID does not match current 0.2.4 score")
    line = q25.assert_half_yard_line(args.line)
    if str(args.market_source) not in q25.ALLOWED_MARKET_SOURCES:
        raise ValueError("unsupported market source")
    book = str(args.book or "").strip()
    if not book:
        raise ValueError("book label required")
    over_price = None if args.over_price is None else q25.validate_american(args.over_price)
    under_price = None if args.under_price is None else q25.validate_american(args.under_price)

    promotion_dir = root / promotion_ptr.read_text(encoding="utf-8").strip()
    promotion_path = promotion_dir / "NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.json"
    promotion_sha_path = promotion_dir / "NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.sha256"
    if not promotion_path.exists() or not promotion_sha_path.exists():
        raise FileNotFoundError("QB 0.2.3 promotion source missing")
    promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    promotion_sha = hashlib.sha256(canonical_bytes(promotion)).hexdigest()
    expected_promotion_sha = promotion_sha_path.read_text(encoding="utf-8").strip().split()[0]
    if promotion_sha != expected_promotion_sha or score.get("promotionSpecSha256") != promotion_sha:
        raise ValueError("QB 0.2.5 promotion lineage drift")

    freeze_dir = root / freeze_ptr.read_text(encoding="utf-8").strip()
    freeze_path = freeze_dir / "NFL_QB_PASSING_YARDS_FROZEN_SPEC.json"
    freeze_manifest_path = freeze_dir / "NFL_QB_PASSING_YARDS_FREEZE_MANIFEST.json"
    if not freeze_path.exists() or not freeze_manifest_path.exists():
        raise FileNotFoundError("QB 0.2.1 frozen source missing")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze_manifest = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    freeze_sha = hashlib.sha256(canonical_bytes(freeze)).hexdigest()
    if freeze_sha != score.get("frozenSpecSha256") or freeze_sha != promotion.get("frozenSpecSha256"):
        raise ValueError("QB 0.2.5 frozen-model lineage drift")

    source_model_dir = root / str(freeze.get("sourceModelRunDirectory") or "")
    oof_path = source_model_dir / "NFL_QB_PASSING_YARDS_OOF.jsonl"
    if not oof_path.exists():
        raise FileNotFoundError(f"frozen chronological OOF predictions missing: {oof_path}")
    expected_oof_sha = (freeze_manifest.get("sourceHashes") or {}).get("qb020OofJsonlSha256")
    actual_oof_sha = sha256_file(oof_path)
    if not expected_oof_sha or actual_oof_sha != expected_oof_sha:
        raise ValueError("QB 0.2.5 frozen OOF residual hash drift")
    oof = load_jsonl(oof_path)
    residuals = q25.residual_rows(oof)
    frozen_n = int((freeze.get("residualCalibration") or {}).get("n") or 0)
    if len(residuals) != frozen_n:
        raise ValueError(f"QB 0.2.5 frozen residual count drift: {len(residuals)} vs {frozen_n}")

    point = float(score["projectionPassingYards"])
    probs = q25.empirical_market_probability(residuals, point, line)
    boot = q25.cluster_bootstrap_probability(residuals, point, line)
    if abs(float(probs["overProbability"]) - float(boot["overProbability"])) > 1e-12:
        raise ValueError("QB 0.2.5 empirical/bootstrap point probability mismatch")

    no_vig = None
    if over_price is not None and under_price is not None:
        no_vig = q25.no_vig_two_way(over_price, under_price)

    over = q25.market_side_summary(
        probs["overProbability"], over_price,
        None if no_vig is None else no_vig["overNoVig"],
    )
    under = q25.market_side_summary(
        probs["underProbability"], under_price,
        None if no_vig is None else no_vig["underNoVig"],
    )
    over["modelProbabilityCi95"] = boot["overCi95"]
    under["modelProbabilityCi95"] = boot["underCi95"]
    if over_price is not None:
        ev_lo = q25.expected_roi(float(boot["overCi95"][0]), over_price)
        ev_hi = q25.expected_roi(float(boot["overCi95"][1]), over_price)
        over["expectedRoiCi95"] = [ev_lo, ev_hi]
        over["expectedRoiPctCi95"] = [100.0 * ev_lo, 100.0 * ev_hi]
        over["positiveEvAcrossProbabilityCi95"] = ev_lo > 0.0
    if under_price is not None:
        ev_lo = q25.expected_roi(float(boot["underCi95"][0]), under_price)
        ev_hi = q25.expected_roi(float(boot["underCi95"][1]), under_price)
        under["expectedRoiCi95"] = [ev_lo, ev_hi]
        under["expectedRoiPctCi95"] = [100.0 * ev_lo, 100.0 * ev_hi]
        under["positiveEvAcrossProbabilityCi95"] = ev_lo > 0.0

    if over_price is not None and under_price is not None:
        completeness = "TWO_SIDED"
    elif over_price is not None:
        completeness = "OVER_ONLY"
    elif under_price is not None:
        completeness = "UNDER_ONLY"
    else:
        completeness = "LINE_ONLY"

    now = datetime.now(timezone.utc)
    captured_at = str(args.captured_at).strip() or now.isoformat()
    quote_time_mode = "USER_PROVIDED" if str(args.captured_at).strip() else "RUN_TIME_ASSUMED_CAPTURE"
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/prospective/nfl/qb_passing_yards_market_025" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    report = {
        "version": q25.VERSION,
        "lineage": q25.LINEAGE,
        "createdAt": now.isoformat(),
        "runId": run_id,
        "status": "PROSPECTIVE_SHADOW_MARKET_EVALUATION",
        "target": target,
        "projectionPassingYards": point,
        "market": {
            "line": line,
            "book": book,
            "marketSource": str(args.market_source),
            "capturedAt": captured_at,
            "quoteTimeMode": quote_time_mode,
            "overAmerican": over_price,
            "underAmerican": under_price,
            "priceCompleteness": completeness,
            "referenceOnly": str(args.market_source) == "PROPSMADNESS_REFERENCE",
        },
        "probabilityModel": probs,
        "probabilityBootstrap": boot,
        "twoWayNoVig": no_vig,
        "sides": {"OVER": over, "UNDER": under},
        "frozenOofResidualRows": len(residuals),
        "frozenOofResidualSourceSha256": actual_oof_sha,
        "sourceScorePath": str(score_path.relative_to(root)),
        "sourceScoreSha256": sha256_file(score_path),
        "promotionSpecSha256": promotion_sha,
        "frozenSpecSha256": freeze_sha,
        "coefficientRefitPerformed": False,
        "candidateReselectionPerformed": False,
        "marketFieldsUsedAsModelFeatures": False,
        "targetOrLater2026OutcomeRowsAdmitted": 0,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "marketExecutionEligible": False,
        "nextGate": "VALIDATE_DIRECT_MARKET_CAPTURE_FRESHNESS_AND_PROSPECTIVE_CLV_BEFORE_EXECUTION_PROMOTION",
    }
    report_path = out_dir / "NFL_QB_PASSING_YARDS_MARKET_EVALUATION.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    atomic_pointer(root / "data/prospective/nfl/CURRENT_QB_PASSING_YARDS_MARKET_025", str(out_dir.relative_to(root)))

    print("\nNFL QB MODEL 0.2.5 — FROZEN OOF MARKET PROBABILITY")
    print(f"Target: {target.get('game_id')} · {target.get('team')} vs {target.get('opponent')} · {target.get('qb_name') or target.get('qb_gsis_id')}")
    print(f"Projection: {point:.1f} yd · market line {line:.1f} · {book} · {args.market_source}")
    print(f"Frozen residual source: chronological OOF 2020-2024 · n={len(residuals):,} · SHA verified")
    print("Probability method: empirical frozen OOF residual CDF · no refit · half-yard settlement only")
    print(f"  OVER {line:.1f}: {100.0*probs['overProbability']:.2f}% · 95% cluster CI [{100.0*boot['overCi95'][0]:.2f}%, {100.0*boot['overCi95'][1]:.2f}%] · fair {over['modelFairAmerican']:+d}")
    print(f"  UNDER {line:.1f}: {100.0*probs['underProbability']:.2f}% · 95% cluster CI [{100.0*boot['underCi95'][0]:.2f}%, {100.0*boot['underCi95'][1]:.2f}%] · fair {under['modelFairAmerican']:+d}")
    if no_vig is not None:
        print(f"Two-way no-vig market: OVER {100.0*no_vig['overNoVig']:.2f}% · UNDER {100.0*no_vig['underNoVig']:.2f}% · hold {100.0*no_vig['hold']:.2f}%")
    if over_price is not None:
        print(f"  OVER offered {over_price:+d} · model EV {over['expectedRoiPct']:+.2f}% · CI EV [{over['expectedRoiPctCi95'][0]:+.2f}%, {over['expectedRoiPctCi95'][1]:+.2f}%]")
    if under_price is not None:
        print(f"  UNDER offered {under_price:+d} · model EV {under['expectedRoiPct']:+.2f}% · CI EV [{under['expectedRoiPctCi95'][0]:+.2f}%, {under['expectedRoiPctCi95'][1]:+.2f}%]")
    print("Market fields used as model features: NO")
    print("Market execution eligible: NO · shadow market evaluation / CLV validation required")
    print(f"Evaluation: {report_path}")
    print("NEXT GATE: VALIDATE_DIRECT_MARKET_CAPTURE_FRESHNESS_AND_PROSPECTIVE_CLV_BEFORE_EXECUTION_PROMOTION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

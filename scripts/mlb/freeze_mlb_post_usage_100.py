#!/usr/bin/env python3
"""Freeze the selected 2026 postseason usage specification 1.0.0.

This creates an immutable local research freeze from the latest 0.9.0
historical-development bakeoff. It does NOT mutate production code.

Explicit confirmation is required because this action closes historical model
selection and establishes 2026 postseason as the prospective confirmation set.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import uuid

VERSION = "1.0.0"
LINEAGE = "mlb-post-usage-freeze-v1.0.0-2026-prospective-2026-09-19"
CONFIRM_TOKEN = "POST_USAGE_OUTS_2026_FREEZE"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def resolve_bakeoff(root: Path) -> Path:
    p = root / "data/models/mlb/CURRENT_POST_USAGE_BAKEOFF_090"
    if not p.exists():
        raise FileNotFoundError(p)
    out = root / p.read_text(encoding="utf-8").strip() / "POST_USAGE_MECHANISM_BAKEOFF_AUDIT.json"
    if not out.exists():
        raise FileNotFoundError(out)
    return out


def validate_candidate(audit: dict) -> dict:
    if audit.get("status") != "HISTORICAL_DEVELOPMENT_BAKEOFF_NOT_FRESH_VALIDATION":
        raise ValueError("bakeoff status is not historical development")
    sel = (audit.get("historical_development_selection") or {}).get("selected")
    if sel != "POST_USAGE_OUTS":
        raise ValueError(f"selected mechanism is {sel!r}, expected POST_USAGE_OUTS")
    cand = audit.get("freeze_candidate") or {}
    if cand.get("model_variant") != "POST_USAGE_OUTS":
        raise ValueError("freeze candidate model_variant mismatch")
    if cand.get("factor_field") != "outs_ratio":
        raise ValueError("freeze candidate factor_field must be outs_ratio")
    if int(cand.get("prospective_test_season") or 0) != 2026:
        raise ValueError("freeze candidate prospective season must be 2026")
    if cand.get("freeze_status") != "CANDIDATE_REQUIRES_EXPLICIT_FREEZE":
        raise ValueError("freeze candidate status is not eligible for explicit freeze")
    if bool(cand.get("k_outcomes_used_to_learn_factor")):
        raise ValueError("candidate claims K outcomes were used to learn factor")
    if audit.get("production_model_mutation") is not False:
        raise ValueError("bakeoff production mutation flag is not false")
    if audit.get("model_refit_performed") is not False:
        raise ValueError("bakeoff model refit flag is not false")
    value = float(cand["factor_value_for_2026_prospective"])
    if not (0.70 <= value <= 1.05):
        raise ValueError(f"candidate factor outside sanity range: {value}")
    return cand


def stable_spec(candidate: dict, core_sha: str, bakeoff_sha: str) -> dict:
    return {
        "model_variant": "POST_USAGE_OUTS",
        "mechanism": "EXPECTED_OUTS_RATIO_THEN_RECOMPUTE_BF",
        "factor_field": "outs_ratio",
        "factor_value": float(candidate["factor_value_for_2026_prospective"]),
        "training_seasons": [int(x) for x in candidate["training_seasons"]],
        "training_pitcher_seasons": int(candidate["training_pitcher_seasons"]),
        "prospective_test_season": 2026,
        "k_outcomes_used_to_learn_factor": False,
        "same_2026_postseason_usage_used": False,
        "production_k_core_sha256_at_freeze": core_sha,
        "selection_audit_sha256": bakeoff_sha,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Freeze MLB POST_USAGE_OUTS for 2026 prospective test")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--confirm", required=True)
    args = ap.parse_args()
    if args.confirm != CONFIRM_TOKEN:
        raise ValueError(f"explicit confirmation required: --confirm {CONFIRM_TOKEN}")

    root = Path(args.root).expanduser().resolve()
    bakeoff_path = resolve_bakeoff(root)
    bakeoff = json.loads(bakeoff_path.read_text(encoding="utf-8"))
    candidate = validate_candidate(bakeoff)

    core_path = root / "packages/models/mlb/k/structured_k_core.js"
    evaluator_path = root / "scripts/mlb/evaluate_mlb_post_usage_mechanisms_090.py"
    core_sha = sha256_file(core_path)
    bakeoff_sha = sha256_file(bakeoff_path)
    evaluator_sha = sha256_file(evaluator_path)
    spec = stable_spec(candidate, core_sha, bakeoff_sha)

    pointer = root / "data/models/mlb/CURRENT_POST_USAGE_FREEZE_100"
    if pointer.exists():
        prior_dir = root / pointer.read_text(encoding="utf-8").strip()
        prior_path = prior_dir / "POST_USAGE_2026_FREEZE.json"
        if not prior_path.exists():
            raise RuntimeError("freeze pointer exists but freeze manifest is missing")
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        prior_spec = prior.get("frozen_spec") or {}
        if prior_spec != spec:
            raise RuntimeError(
                "2026 POST_USAGE freeze already exists with a different specification; "
                "refusing replacement"
            )
        print()
        print(f"MLB POST_USAGE FREEZE {VERSION}")
        print("Status: ALREADY_FROZEN_IDENTICAL")
        print(f"Variant: {spec['model_variant']}")
        print(f"outs_ratio factor: {spec['factor_value']:.8f}")
        print(f"Freeze: {prior_path}")
        return 0

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/mlb/post_usage_freeze_100" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "version": VERSION,
        "lineage": LINEAGE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_PROSPECTIVE_2026",
        "explicit_confirmation_token": CONFIRM_TOKEN,
        "frozen_spec": spec,
        "historical_development_status": "CLOSED_FOR_2026_PROSPECTIVE_CONFIRMATION",
        "historical_development_audit": str(bakeoff_path),
        "historical_development_audit_sha256": bakeoff_sha,
        "mechanism_evaluator": str(evaluator_path),
        "mechanism_evaluator_sha256": evaluator_sha,
        "production_k_core": str(core_path),
        "production_k_core_sha256_at_freeze": core_sha,
        "prospective_rules": {
            "factor_refit_allowed_before_2026_postseason_result": False,
            "mechanism_reselection_allowed": False,
            "2026_postseason_usage_outcomes_allowed_to_mutate_factor": False,
            "2026_k_outcomes_allowed_to_mutate_factor": False,
            "production_promotion_requires_prospective_review": True,
        },
        "production_model_mutation": False,
        "production_model_promotion": False,
        "model_refit_performed": False,
        "historical_k_market": "NOT_ACQUIRED",
        "oddsPapi_requests": 0,
    }
    out = out_dir / "POST_USAGE_2026_FREEZE.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    atomic_write(pointer, str(out_dir.relative_to(root)) + "\n")

    print()
    print(f"MLB POST_USAGE FREEZE {VERSION}")
    print("Status: FROZEN_PROSPECTIVE_2026")
    print(f"Variant: {spec['model_variant']}")
    print(f"Mechanism: {spec['mechanism']}")
    print(f"outs_ratio factor: {spec['factor_value']:.8f}")
    print(f"Training seasons: {spec['training_seasons'][0]}-{spec['training_seasons'][-1]}")
    print(f"Training pitcher-seasons: {spec['training_pitcher_seasons']}")
    print("2026 K outcomes may mutate factor: NO")
    print("2026 usage outcomes may mutate factor: NO")
    print("Production promotion: NO")
    print(f"Freeze: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

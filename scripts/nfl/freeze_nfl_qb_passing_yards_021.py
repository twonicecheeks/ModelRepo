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
    ap = argparse.ArgumentParser(description="Freeze NFL QB Model 0.2.0 development leader before 2025 holdout")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()

    model_dir = root / "packages/models/nfl/game"
    provider_dir = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(model_dir)); sys.path.insert(0, str(provider_dir))
    import qb_passing_yards_bakeoff_020 as q20
    import qb_passing_yards_freeze_021 as q21
    import contract

    source_ptr = root / "data/models/nfl/CURRENT_QB_MODEL_020"
    target_ptr = root / "data/normalized/nfl/CURRENT_NFL_QB_OFFICIAL_TARGETS_019"
    raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    if not source_ptr.exists() or not target_ptr.exists() or not raw_ptr.exists():
        raise FileNotFoundError("required QB model/target/raw pointers missing")

    source_dir = root / source_ptr.read_text(encoding="utf-8").strip()
    target_dir = root / target_ptr.read_text(encoding="utf-8").strip()
    raw_sid = raw_ptr.read_text(encoding="utf-8").strip()
    report_path = source_dir / "NFL_QB_PASSING_YARDS_BAKEOFF.json"
    spec_path = source_dir / "QB_MODEL_SPEC.json"
    spec_sha_path = source_dir / "QB_MODEL_SPEC.sha256"
    oof_path = source_dir / "NFL_QB_PASSING_YARDS_OOF.jsonl"
    targets_path = target_dir / "NFL_QB_OFFICIAL_TARGETS.jsonl"
    target_audit_path = target_dir / "NFL_QB_OFFICIAL_TARGET_AUTHORITY_AUDIT.json"
    for p in (report_path, spec_path, spec_sha_path, oof_path, targets_path, target_audit_path):
        if not p.exists():
            raise FileNotFoundError(f"required freeze source missing: {p}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    q21.assert_freeze_authorized(report, spec)

    expected_spec_sha = spec_sha_path.read_text(encoding="utf-8").strip().split()[0]
    actual_spec_sha = hashlib.sha256(canonical_bytes(spec)).hexdigest()
    if expected_spec_sha != actual_spec_sha or report.get("candidateSpecSha256") != actual_spec_sha:
        raise ValueError("QB 0.2.0 source spec hash drift")
    if report.get("sourcePbpSnapshotId") != raw_sid:
        raise ValueError("QB 0.2.0/raw snapshot drift")

    target_audit = json.loads(target_audit_path.read_text(encoding="utf-8"))
    if target_audit.get("holdoutOpened") is not False or target_audit.get("prospectiveRead") is not False:
        raise ValueError("QB 0.1.9 target boundary drift")
    if target_audit.get("sourcePbpSnapshotId") != raw_sid:
        raise ValueError("QB 0.1.9/raw snapshot drift")
    if target_audit.get("disposition") != "OFFICIAL_TARGET_LAYER_READY_FOR_QB_MODELING":
        raise ValueError("QB 0.1.9 target authority no longer ready")

    rows = load_jsonl(targets_path)
    if not rows:
        raise ValueError("no canonical QB development targets")
    seasons = sorted({int(r.get("season") or 0) for r in rows})
    q20.assert_exact_development_window(seasons)
    if any(s >= 2025 for s in seasons):
        raise ValueError("freeze source unexpectedly contains 2025+")

    for row in rows:
        gid = str(row.get("game_id") or "")
        parsed = contract.parse_game_id(gid)
        away = contract.normalize_team_abbr(parsed["away_team"])
        home = contract.normalize_team_abbr(parsed["home_team"])
        team = str(row.get("team") or "").strip().upper()
        if team == away:
            row["_opponent"] = home; row["_home"] = 0
        elif team == home:
            row["_opponent"] = away; row["_home"] = 1
        else:
            raise ValueError(f"target team/game identity mismatch: {gid} team={team}")

    examples = q20.build_examples(rows)
    if len(examples) != int(report.get("developmentRows") or 0):
        raise ValueError("development example count drift")
    final_model = q20.fit_ridge(
        [e.x for e in examples],
        [e.y_passing_yards for e in examples],
        names=q20.FEATURE_NAMES,
        l2=q20.FIXED_L2,
    )
    model_payload = q21.serialize_ridge(final_model)
    if model_payload["featureNames"] != list(spec.get("featureNames") or ()):
        raise ValueError("frozen feature-name contract drift")
    if abs(float(model_payload["l2"]) - float(spec.get("fixedL2"))) > 1e-12:
        raise ValueError("frozen L2 drift")

    # Verify serialization is prediction-identical before freezing it.
    probes = examples[:3] + examples[-3:]
    for e in probes:
        a = final_model.predict(e.x)
        b = q21.predict_serialized_ridge(model_payload, e.x)
        if abs(a - b) > 1e-9:
            raise ValueError("serialized frozen model prediction mismatch")

    oof = load_jsonl(oof_path)
    if len(oof) != int(report.get("oofRows") or 0):
        raise ValueError("OOF row-count drift")
    residual_cal = q21.residual_calibration(oof)

    freeze_spec = {
        "version": q21.VERSION,
        "lineage": q21.LINEAGE,
        "status": "DEVELOPMENT_FROZEN_AWAITING_SINGLE_2025_HOLDOUT",
        "sourceModelVersion": q20.VERSION,
        "sourceModelRunDirectory": str(source_dir.relative_to(root)),
        "sourceModelSpecSha256": actual_spec_sha,
        "sourcePbpSnapshotId": raw_sid,
        "sourceOfficialTargetDirectory": str(target_dir.relative_to(root)),
        "frozenCandidate": q21.FROZEN_CANDIDATE,
        "target": "official_passing_yards",
        "identityMode": "CONDITIONAL_ON_KNOWN_QB_GSIS_ID",
        "trainingSeasons": list(q20.DEVELOPMENT_SEASONS),
        "trainingRows": len(examples),
        "featureTiming": spec["featureTiming"],
        "featureNames": list(q20.FEATURE_NAMES),
        "fixedL2": q20.FIXED_L2,
        "model": model_payload,
        "residualCalibration": residual_cal,
        "holdoutEvaluationPolicy": q21.HOLDOUT_EVALUATION_POLICY,
        "sealedHoldoutSeason": 2025,
        "holdoutOpened": False,
        "holdoutLabelsAdmitted": 0,
        "prospectiveSeason": 2026,
        "prospectiveRead": False,
        "marketDependency": False,
        "marketFieldsAllowed": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutationAllowed": False,
        "selectionAfterHoldoutAllowed": False,
        "refitAfterHoldoutAllowed": False,
    }
    freeze_sha = hashlib.sha256(canonical_bytes(freeze_spec)).hexdigest()

    source_hashes = {
        "qb020BakeoffJsonSha256": sha256_file(report_path),
        "qb020SpecJsonSha256": sha256_file(spec_path),
        "qb020OofJsonlSha256": sha256_file(oof_path),
        "qb019TargetsJsonlSha256": sha256_file(targets_path),
        "qb019TargetAuditJsonSha256": sha256_file(target_audit_path),
        "qb020CodeSha256": sha256_file(model_dir / "qb_passing_yards_bakeoff_020.py"),
        "qb021FreezeCodeSha256": sha256_file(model_dir / "qb_passing_yards_freeze_021.py"),
    }

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/qb_model_021" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    freeze_path = out_dir / "NFL_QB_PASSING_YARDS_FROZEN_SPEC.json"
    freeze_path.write_bytes(canonical_bytes(freeze_spec))
    (out_dir / "NFL_QB_PASSING_YARDS_FROZEN_SPEC.sha256").write_text(
        freeze_sha + "  NFL_QB_PASSING_YARDS_FROZEN_SPEC.json\n", encoding="utf-8"
    )
    manifest = {
        "version": q21.VERSION,
        "lineage": q21.LINEAGE,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "runId": run_id,
        "freezeSpecSha256": freeze_sha,
        "sourceHashes": source_hashes,
        "frozenCandidate": q21.FROZEN_CANDIDATE,
        "developmentSelectionStatus": report["selection"]["selectionStatus"],
        "developmentLeaderMae": report["pooledMetrics2020to2024"][q21.FROZEN_CANDIDATE]["mae"],
        "developmentBaselineMae": report["pooledMetrics2020to2024"]["baseline_last4"]["mae"],
        "developmentLeaderVsBaseline": report["selection"]["leaderVsLast4Baseline"],
        "holdoutEvaluationPolicy": q21.HOLDOUT_EVALUATION_POLICY,
        "holdoutOpened": False,
        "holdoutLabelsAdmitted": 0,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "nextGate": "RUN_SINGLE_2025_CONFIRMATORY_HOLDOUT_WITH_FROZEN_0.2.1_ONLY",
    }
    manifest_path = out_dir / "NFL_QB_PASSING_YARDS_FREEZE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    atomic_pointer(root / "data/models/nfl/CURRENT_QB_MODEL_021", str(out_dir.relative_to(root)))

    dev = report["selection"]["leaderVsLast4Baseline"]
    print("\nNFL QB MODEL 0.2.1 — DEVELOPMENT FREEZE")
    print(f"Source model: QB 0.2.0 · {source_dir.relative_to(root)}")
    print(f"Frozen candidate: {q21.FROZEN_CANDIDATE}")
    print(f"Training rows: {len(examples):,} · 2016-2024 only")
    print(f"Features: {len(q20.FEATURE_NAMES)} · fixed L2 {q20.FIXED_L2}")
    print(f"Development OOF MAE delta vs last4: {float(dev['deltaMae']):+.3f} yd · 95% CI [{float(dev['ci95'][0]):+.3f}, {float(dev['ci95'][1]):+.3f}]")
    print(f"OOF residual calibration: n={residual_cal['n']:,} · sigma {residual_cal['sigma']:.3f} yd")
    print("2025 holdout: STILL SEALED / 0 LABELS READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print("Post-holdout candidate reselection: FORBIDDEN")
    print("Post-holdout refit before disposition: FORBIDDEN")
    print("Holdout disposition is preregistered: CONFIRMATORY_PASS / DIRECTIONAL_PASS / FAIL")
    print(f"Freeze SHA256: {freeze_sha}")
    print(f"Frozen spec: {freeze_path}")
    print(f"Manifest: {manifest_path}")
    print("NEXT GATE: RUN_SINGLE_2025_CONFIRMATORY_HOLDOUT_WITH_FROZEN_0.2.1_ONLY")
    print("PASS QB Model 0.2.1 freeze · 2025 remains sealed · no model selection remains")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

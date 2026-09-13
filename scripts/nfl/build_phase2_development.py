#!/usr/bin/env python3
"""Build MODEL NFL 2.9.0 Phase 2A development-only historical model report."""
from __future__ import annotations

from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from statistics import fmean


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def load_current_snapshot(root: Path) -> tuple[str, Path]:
    ptr = root / "data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"
    if not ptr.exists():
        raise SystemExit("No normalized nflverse snapshot pointer. Run scripts/nfl/build_phase1_snapshot.command first.")
    sid = ptr.read_text(encoding="utf-8").strip()
    if not sid:
        raise SystemExit("CURRENT_PHASE1_SNAPSHOT is blank")
    path = root / "data/normalized/nfl/phase1" / sid
    required = ["pregame_features.csv", "game_targets.csv", "NFLVERSE_COVERAGE_AUDIT.json", "NORMALIZATION_MANIFEST.json"]
    missing = [n for n in required if not (path / n).exists()]
    if missing:
        raise SystemExit(f"normalized snapshot {sid} missing: {', '.join(missing)}")
    return sid, path


def development_targets(path: Path, development_game_ids: set[str]) -> dict[str, int]:
    """Read labels only for preselected development game IDs; 2025 IDs are never admitted."""
    out: dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            gid = str(row.get("game_id") or "")
            if gid not in development_game_ids:
                continue
            raw = row.get("home_win")
            if raw in ("0", "0.0"):
                out[gid] = 0
            elif raw in ("1", "1.0"):
                out[gid] = 1
    return out


def report_markdown(report: dict) -> str:
    m = report["selectedModel"]["walkForward"]
    selected = m["selectedL2"]
    chosen = next(x for x in m["candidates"] if x["l2"] == selected)
    home = report["baselines"]["constantHomeRate"]
    elo = report["baselines"]["eloOnline"]
    lines = [
        "# MODEL NFL 2.9.0 Phase 2A — Development Validation Report", "",
        f"Generated: {report['generatedAt']}", "",
        "**Status: HISTORICAL DEVELOPMENT ONLY. 2025 HOLDOUT NOT EVALUATED. NOT PRODUCTION.**", "",
        f"Source snapshot: `{report['sourceSnapshotId']}`", "",
        f"Development seasons: {report['developmentSeasons'][0]}–{report['developmentSeasons'][-1]} REG", "",
        f"Chronological validation seasons: {', '.join(map(str, report['validationSeasons']))}", "",
        "## Integrity", "",
        f"- nflverse market isolation: **{'PASS' if report['integrity']['marketIsolationPass'] else 'FAIL'}**",
        f"- 2025 holdout evaluated: **NO**",
        f"- 2025 labels admitted to model selection/fitting: **{report['integrity']['holdoutLabelsAdmitted']}**",
        f"- OddsPapi requests: **0**", "",
        "## Development benchmarks", "",
        "| Model | N | Brier | Log loss | Accuracy |",
        "|---|---:|---:|---:|---:|",
        f"| Constant home-rate | {home['n']} | {home['brier']:.5f} | {home['logLoss']:.5f} | {home['accuracy']:.3f} |",
        f"| Online Elo-style | {elo['n']} | {elo['brier']:.5f} | {elo['logLoss']:.5f} | {elo['accuracy']:.3f} |",
        f"| L2 logistic walk-forward (λ={selected:g}) | {chosen['pooled']['n']} | {chosen['pooled']['brier']:.5f} | {chosen['pooled']['logLoss']:.5f} | {chosen['pooled']['accuracy']:.3f} |",
        "", "## Walk-forward folds", "",
        "| Season | N | Brier | Log loss | Accuracy |", "|---:|---:|---:|---:|---:|",
    ]
    for fold in chosen["folds"]:
        lines.append(f"| {fold['season']} | {fold['n']} | {fold['brier']:.5f} | {fold['logLoss']:.5f} | {fold['accuracy']:.3f} |")
    lines += ["", "## Regularization search", "", "| λ | Brier | Log loss |", "|---:|---:|---:|"]
    for cand in m["candidates"]:
        lines.append(f"| {cand['l2']:g} | {cand['pooled']['brier']:.5f} | {cand['pooled']['logLoss']:.5f} |")
    lines += [
        "", "## Next gate", "",
        "Review this report before freezing the model specification. Do **not** evaluate the 2025 holdout or produce a 2026 betting probability from this Phase 2A candidate yet.", "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    sys.path.insert(0, str(root / "packages/models/nfl/game"))
    import research_model as rm

    sid, snap = load_current_snapshot(root)
    coverage = json.loads((snap / "NFLVERSE_COVERAGE_AUDIT.json").read_text(encoding="utf-8"))
    norm_manifest = json.loads((snap / "NORMALIZATION_MANIFEST.json").read_text(encoding="utf-8"))
    if not coverage.get("marketIsolation", {}).get("pass"):
        raise SystemExit("FAIL source coverage audit did not pass market isolation")
    if int(coverage.get("holdoutSeason")) != rm.HOLDOUT_SEASON:
        raise SystemExit("FAIL unexpected holdout season")
    if norm_manifest.get("trainingWindowFrozen") is not False:
        raise SystemExit("FAIL Phase 1 snapshot unexpectedly claims a frozen training window")

    feature_rows = read_csv(snap / "pregame_features.csv")
    dev_seasons = list(range(2016, 2025))
    dev_rows = [r for r in feature_rows if int(r["season"]) in dev_seasons and r.get("game_type") == "REG"]
    if not dev_rows:
        raise SystemExit("FAIL no 2016-2024 REG development feature rows")
    dev_ids = {r["game_id"] for r in dev_rows}
    # Critical holdout boundary: labels are loaded only for development IDs.
    targets = development_targets(snap / "game_targets.csv", dev_ids)
    examples = rm.examples_from_rows(dev_rows, targets, allowed_seasons=set(dev_seasons), game_type="REG")
    if len(examples) < 1000:
        raise SystemExit(f"FAIL development sample unexpectedly small: {len(examples)}")

    validation_seasons = [2022, 2023, 2024]
    walk = rm.walk_forward_l2(examples, validation_seasons=validation_seasons)
    selected_l2 = walk["selectedL2"]
    candidate = rm.fit_logistic(examples, l2=selected_l2)

    # Constant baseline is evaluated on the same chronological 2022-2024 window,
    # using only prior seasons for each fold.
    const_y, const_p = [], []
    for season in validation_seasons:
        train = [e for e in examples if e.season < season]
        test = [e for e in examples if e.season == season]
        const_y.extend(e.y for e in test)
        const_p.extend(rm.constant_home_rate(train, test))
    const_metrics = rm.metric_summary(const_y, const_p)

    # Elo is an online baseline over all development games; report a comparable
    # 2022-2024 slice after the rating has been warmed on prior development games.
    elo_all = rm.elo_online_predictions(examples)
    elo_y, elo_p = [], []
    for e, p in zip(examples, elo_all):
        if e.season in validation_seasons:
            elo_y.append(e.y); elo_p.append(p)
    elo_metrics = rm.metric_summary(elo_y, elo_p)

    chosen_walk = next(x for x in walk["candidates"] if x["l2"] == selected_l2)
    # Candidate calibration is derived only from pooled development validation.
    pooled_y, pooled_p = [], []
    for season in validation_seasons:
        train = [e for e in examples if e.season < season]
        test = [e for e in examples if e.season == season]
        model = rm.fit_logistic(train, l2=selected_l2)
        pooled_y.extend(e.y for e in test)
        pooled_p.extend(model.predict_proba(e.x) for e in test)

    spec = {
        "specVersion": "0.1.0-candidate",
        "status": "CANDIDATE_NOT_FROZEN",
        "productionEligible": False,
        "holdoutSeason": rm.HOLDOUT_SEASON,
        "holdoutEvaluated": False,
        "prospectiveSeason": rm.PROSPECTIVE_SEASON,
        "sourceSnapshotId": sid,
        "trainingSeasonsUsed": dev_seasons,
        "gameType": "REG",
        "validationSeasons": validation_seasons,
        "selectedL2": selected_l2,
        "selectionCriterion": "pooled chronological development log loss; Brier secondary",
        "marketFieldsAllowed": False,
        "oddsPapiRequests": 0,
        "model": candidate.to_dict(),
    }
    spec_bytes = canonical_json(spec)
    spec_sha = sha256_bytes(spec_bytes)

    report = {
        "reportVersion": "0.1.0",
        "generatedAt": utc_now(),
        "status": "DEVELOPMENT_ONLY_HOLDOUT_UNTOUCHED",
        "sourceSnapshotId": sid,
        "developmentSeasons": dev_seasons,
        "validationSeasons": validation_seasons,
        "developmentExamples": len(examples),
        "integrity": {
            "marketIsolationPass": True,
            "holdoutSeason": rm.HOLDOUT_SEASON,
            "holdoutEvaluated": False,
            "holdoutLabelsAdmitted": 0,
            "oddsPapiRequests": 0,
        },
        "baselines": {"constantHomeRate": const_metrics, "eloOnline": elo_metrics},
        "selectedModel": {
            "featureSetVersion": rm.FEATURE_SET_VERSION,
            "baseFeatureCount": len(rm.base_feature_names()),
            "expandedFeatureCount": len(rm.expanded_feature_names()),
            "walkForward": walk,
            "pooledCalibration": rm.calibration_bins(pooled_y, pooled_p),
            "candidateSpecSha256": spec_sha,
            "candidateFitIterations": candidate.iterations,
            "candidateFitFinalGradientNorm": candidate.final_gradient_norm,
        },
    }

    out_root = root / "data/models/nfl/phase2a" / sid
    if out_root.exists():
        raise SystemExit(f"Refusing to overwrite immutable Phase 2A output: {out_root}")
    staging = out_root.parent / ("." + sid + ".staging")
    if staging.exists():
        import shutil; shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        (staging / "MODEL_SPEC_CANDIDATE.json").write_bytes(spec_bytes)
        (staging / "MODEL_SPEC_CANDIDATE.sha256").write_text(spec_sha + "  MODEL_SPEC_CANDIDATE.json\n", encoding="utf-8")
        (staging / "DEVELOPMENT_VALIDATION_REPORT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (staging / "DEVELOPMENT_VALIDATION_REPORT.md").write_text(report_markdown(report), encoding="utf-8")
        manifest = {
            "phase": "NFL_2.9.0_PHASE2A",
            "createdAt": utc_now(),
            "sourceSnapshotId": sid,
            "candidateSpecSha256": spec_sha,
            "holdoutEvaluated": False,
            "productionEligible": False,
            "oddsPapiRequests": 0,
        }
        (staging / "PHASE2A_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, out_root)
        ptr_tmp = root / "data/models/nfl/.CURRENT_PHASE2A.tmp"
        ptr = root / "data/models/nfl/CURRENT_PHASE2A"
        ptr.parent.mkdir(parents=True, exist_ok=True)
        ptr_tmp.write_text(sid + "\n", encoding="utf-8")
        os.replace(ptr_tmp, ptr)
    except Exception:
        import shutil; shutil.rmtree(staging, ignore_errors=True)
        raise

    print("MODEL NFL 2.9.0 PHASE 2A — DEVELOPMENT MODEL BUILD")
    print(f"PASS source normalized snapshot: {sid}")
    print(f"PASS development REG examples: {len(examples)} · seasons 2016-2024")
    print("PASS 2025 holdout outcomes: NOT EVALUATED / NOT ADMITTED")
    print(f"PASS chronological validation: {','.join(map(str, validation_seasons))}")
    print(f"PASS selected L2: {selected_l2:g} by development log loss")
    print(f"PASS candidate spec SHA256: {spec_sha}")
    print("PASS OddsPapi requests: 0 · market fields: isolated")
    print(f"REPORT: {out_root / 'DEVELOPMENT_VALIDATION_REPORT.md'}")
    print("BUILD PASS — paste DEVELOPMENT_VALIDATION_REPORT.md into ChatGPT before freezing or evaluating 2025")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

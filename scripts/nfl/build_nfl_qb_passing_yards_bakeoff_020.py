#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse
import hashlib
import json
import os
import sys
import uuid


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def load_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def canonical_bytes(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def residual_summary(rows: list[dict], field: str) -> dict:
    vals = sorted(float(r["actual_passing_yards"]) - float(r[field]) for r in rows)
    if not vals:
        return {"n": 0}
    n = len(vals)
    mean = fmean(vals)
    var = fmean((x - mean) ** 2 for x in vals) if n > 1 else 0.0
    def q(p: float) -> float:
        idx = int(round((n - 1) * p))
        return vals[max(0, min(n - 1, idx))]
    return {
        "n": n, "mean": mean, "sigma": var ** 0.5,
        "p05": q(.05), "p10": q(.10), "p25": q(.25), "p50": q(.50),
        "p75": q(.75), "p90": q(.90), "p95": q(.95),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="NFL QB Model 0.2.0 chronological passing-yards challenger bakeoff")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    provider_dir = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(model_dir)); sys.path.insert(0, str(provider_dir))
    import qb_passing_yards_bakeoff_020 as q20
    import contract

    seasons = q20.assert_exact_development_window(parse_seasons(args.seasons))

    target_ptr = root / "data/normalized/nfl/CURRENT_NFL_QB_OFFICIAL_TARGETS_019"
    state_ptr = root / "data/models/nfl/CURRENT_QB_STATE_019"
    raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    if not target_ptr.exists() or not state_ptr.exists() or not raw_ptr.exists():
        raise FileNotFoundError("required QB 0.1.9 official-target/raw pointers missing")

    target_dir = root / target_ptr.read_text(encoding="utf-8").strip()
    state_dir = root / state_ptr.read_text(encoding="utf-8").strip()
    raw_sid = raw_ptr.read_text(encoding="utf-8").strip()
    target_audit = json.loads((target_dir / "NFL_QB_OFFICIAL_TARGET_AUTHORITY_AUDIT.json").read_text(encoding="utf-8"))
    state_audit = json.loads((state_dir / "NFL_QB_OFFICIAL_TARGET_AUTHORITY_AUDIT.json").read_text(encoding="utf-8"))

    for audit, label in ((target_audit, "target"), (state_audit, "state")):
        if audit.get("sourcePbpSnapshotId") != raw_sid:
            raise ValueError(f"QB 0.1.9 {label}/raw snapshot mismatch")
        if audit.get("holdoutOpened") is not False or audit.get("prospectiveRead") is not False:
            raise ValueError(f"QB 0.1.9 {label} holdout/prospective boundary drift")
        if audit.get("marketDependency") is not False or int(audit.get("oddsPapiRequests") or 0) != 0:
            raise ValueError(f"QB 0.1.9 {label} market-isolation drift")
        if audit.get("frozenOmegaMutation") is not False:
            raise ValueError(f"QB 0.1.9 {label} OMEGA mutation drift")
        if audit.get("modelFitAuthorizedForNextVersion") is not True:
            raise ValueError("QB 0.1.9 did not authorize development model fitting")
        if audit.get("disposition") != "OFFICIAL_TARGET_LAYER_READY_FOR_QB_MODELING":
            raise ValueError("QB 0.1.9 target authority is not ready")

    rows = [r for r in load_jsonl(target_dir / "NFL_QB_OFFICIAL_TARGETS.jsonl") if int(r.get("season") or 0) in seasons]
    if len(rows) != int(target_audit.get("targetRows") or 0):
        raise ValueError("QB 0.1.9 canonical target row-count drift")
    if not rows:
        raise ValueError("no canonical QB 0.1.9 targets")

    # Identity-only game context. No schedule result or market columns are read.
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
            raise ValueError(f"target team/game identity mismatch: {gid} team={team} away={away} home={home}")

    examples = q20.build_examples(rows)
    counts = {s: sum(1 for e in examples if e.season == s) for s in seasons}
    if sum(counts.values()) != len(rows):
        raise ValueError("QB 0.2.0 feature-row coverage drift")

    oof: list[dict] = []
    folds: list[dict] = []
    for season in q20.VALIDATION_SEASONS:
        train = [e for e in examples if e.season < season]
        test = [e for e in examples if e.season == season]
        if not train or not test:
            raise ValueError(f"empty chronological fold {season}")
        preds = q20.fit_predict_candidates(train, test, l2=q20.FIXED_L2)
        oof.extend(preds)
        ys = [float(r["actual_passing_yards"]) for r in preds]
        fm = {
            "baseline_last4": q20.metric_summary(ys, [float(r["baseline_last4"]) for r in preds]),
        }
        for name in q20.CANDIDATES:
            fm[name] = q20.metric_summary(ys, [float(r[name]) for r in preds])
        folds.append({
            "validationSeason": season,
            "trainSeasons": [s for s in seasons if s < season],
            "trainRows": len(train), "validationRows": len(test), "metrics": fm,
        })
        print(
            f"PASS chronological fold {season} · train {len(train):,} · test {len(test):,} · "
            + " · ".join(f"{name} MAE {fm[name]['mae']:.3f}" for name in q20.CANDIDATES)
        )

    selection = q20.development_selection(oof)
    ys_all = [float(r["actual_passing_yards"]) for r in oof]
    pooled = {
        "baseline_last4": q20.metric_summary(ys_all, [float(r["baseline_last4"]) for r in oof])
    }
    for name in q20.CANDIDATES:
        pooled[name] = q20.metric_summary(ys_all, [float(r[name]) for r in oof])

    bootstrap = {}
    for name in q20.CANDIDATES:
        bootstrap[f"{name}_vs_last4"] = q20.cluster_bootstrap_mae_delta(oof, name, "baseline_last4")
    for i, a in enumerate(q20.CANDIDATES):
        for b in q20.CANDIDATES[i + 1:]:
            bootstrap[f"{a}_vs_{b}"] = q20.cluster_bootstrap_mae_delta(oof, a, b)

    residuals = {name: residual_summary(oof, name) for name in q20.CANDIDATES}
    residuals["baseline_last4"] = residual_summary(oof, "baseline_last4")

    spec = {
        "version": q20.VERSION,
        "lineage": q20.LINEAGE,
        "status": "DEVELOPMENT_CHALLENGER_NOT_FROZEN",
        "target": "official_passing_yards",
        "identityMode": "CONDITIONAL_ON_KNOWN_QB_GSIS_ID",
        "identityPolicy": "historical observed-start GSIS is a target key and prior-history lookup key only; future caller must supply verified/market-listed QB identity; current-game performance never enters features",
        "featureTiming": "strictly prior week; all rows in target season/week are featurized before that week is admitted to history",
        "featureNames": list(q20.FEATURE_NAMES),
        "fixedL2": q20.FIXED_L2,
        "validationSeasons": list(q20.VALIDATION_SEASONS),
        "candidates": {
            "MODEL_A_DIRECT": "ridge: pregame features -> official passing yards",
            "MODEL_B_VOLUME_X_YPA": "ridge attempts x ridge yards/attempt",
            "MODEL_C_VOLUME_X_CR_X_YPC": "ridge attempts x bounded ridge completion rate x ridge yards/completion",
        },
        "baseline": "QB last-4 official passing-yards mean; fallback strictly prior league mean",
        "developmentSelectionRule": selection["selectionRule"],
        "componentPolicy": "official weekly attempts/completions/passing yards/sacks are historical target/stat authority; PBP supplies lagged structural mechanisms only",
        "airYacPolicy": "rare air/YAC semantic anomalies remain quarantined; current 0.2.0 candidates do not fit air+YAC component targets",
        "marketFieldsAllowed": False,
        "oddsPapiRequests": 0,
        "sealedHoldoutSeason": 2025,
        "prospectiveSeason": 2026,
        "frozenOmegaMutationAllowed": False,
    }
    spec_sha = hashlib.sha256(canonical_bytes(spec)).hexdigest()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/qb_model_020" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    pred_path = out_dir / "NFL_QB_PASSING_YARDS_OOF.jsonl"
    with pred_path.open("w", encoding="utf-8") as f:
        for row in sorted(oof, key=lambda r: (int(r["season"]), int(r["week"]), str(r["game_id"]), str(r["team"]))):
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    report = {
        "version": q20.VERSION,
        "lineage": q20.LINEAGE,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourcePbpSnapshotId": raw_sid,
        "sourceOfficialTargetDirectory": str(target_dir.relative_to(root)),
        "sourceOfficialTargetAuditDirectory": str(state_dir.relative_to(root)),
        "developmentSeasons": list(seasons),
        "validationSeasons": list(q20.VALIDATION_SEASONS),
        "sealedHoldoutSeason": 2025,
        "holdoutOpened": False,
        "holdoutLabelsAdmitted": 0,
        "prospectiveSeason": 2026,
        "prospectiveRead": False,
        "marketDependency": False,
        "marketFieldsAdmitted": 0,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "trainingOrRefitPerformed": True,
        "trainingScope": "development-only expanding-year coefficient fits; 2025 remains sealed",
        "conditionalIdentityResearch": True,
        "starterResolverInModelFit": False,
        "starterResolverReason": "QB prop/verified-starter research is conditional on the target QB identity; resolver accuracy remains an independent end-to-end operational layer and is not allowed to contaminate QB skill estimation",
        "featureTiming": spec["featureTiming"],
        "featureCount": len(q20.FEATURE_NAMES),
        "developmentRows": len(examples),
        "rowsBySeason": {str(k): v for k, v in counts.items()},
        "oofRows": len(oof),
        "fixedL2": q20.FIXED_L2,
        "hyperparameterSearchPerformed": False,
        "pooledMetrics2020to2024": pooled,
        "chronologicalFolds": folds,
        "clusterBootstrapMaeDeltas": bootstrap,
        "oofResidualDistributions": residuals,
        "selection": selection,
        "candidateSpecSha256": spec_sha,
        "nextGate": (
            "FREEZE_DEVELOPMENT_LEADER_BEFORE_SINGLE_2025_HOLDOUT"
            if selection["selectionStatus"] == "DEVELOPMENT_LEADER_SUPPORTED"
            else "DO_NOT_OPEN_2025_REVIEW_DEVELOPMENT_EVIDENCE"
        ),
        "productionEligible": False,
    }
    audit_path = out_dir / "NFL_QB_PASSING_YARDS_BAKEOFF.json"
    audit_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out_dir / "QB_MODEL_SPEC.json").write_bytes(canonical_bytes(spec))
    (out_dir / "QB_MODEL_SPEC.sha256").write_text(spec_sha + "  QB_MODEL_SPEC.json\n", encoding="utf-8")

    md = [
        "# NFL QB Model 0.2.0 — Passing-Yards Challenger Bake-off", "",
        "**2025 HOLDOUT REMAINS SEALED. DEVELOPMENT RESEARCH ONLY.**", "",
        f"Source PBP snapshot: `{raw_sid}`", "",
        f"Official target snapshot: `{target_audit.get('officialStatsSnapshotId')}`", "",
        "## Pooled chronological OOF performance, 2020-2024", "",
        "| Model | N | MAE | RMSE | Bias | Median AE |", "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("baseline_last4",) + q20.CANDIDATES:
        m = pooled[name]
        md.append(f"| {name} | {m['n']} | {m['mae']:.3f} | {m['rmse']:.3f} | {m['bias']:.3f} | {m['medianAbsoluteError']:.3f} |")
    md += ["", "## Chronological folds", "", "| Season | Train N | Test N | Baseline MAE | A MAE | B MAE | C MAE |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for fold in folds:
        m = fold["metrics"]
        md.append(
            f"| {fold['validationSeason']} | {fold['trainRows']} | {fold['validationRows']} | "
            f"{m['baseline_last4']['mae']:.3f} | {m['MODEL_A_DIRECT']['mae']:.3f} | "
            f"{m['MODEL_B_VOLUME_X_YPA']['mae']:.3f} | {m['MODEL_C_VOLUME_X_CR_X_YPC']['mae']:.3f} |"
        )
    l = selection["leaderVsLast4Baseline"]
    md += [
        "", "## Selection", "",
        f"Development leader: **{selection['developmentLeader']}**", "",
        f"Status: **{selection['selectionStatus']}**", "",
        f"Leader MAE delta vs last-4 baseline: **{l['deltaMae']:+.3f} yd** · 95% game-cluster bootstrap **[{l['ci95'][0]:+.3f}, {l['ci95'][1]:+.3f}]**", "",
        f"Fold wins: `{json.dumps(selection['foldWinsByMae'], sort_keys=True)}`", "",
        f"Next gate: **{report['nextGate']}**", "",
        "## Integrity", "",
        "- 2025 labels admitted: **0**",
        "- 2026 outcomes read: **NO**",
        "- sportsbook/market fields admitted: **0**",
        "- OddsPapi requests: **0**",
        "- OMEGA mutation: **NO**",
        "- hyperparameter search: **NO**; L2 was fixed before this bake-off",
        "- target authority: nflverse weekly player stats",
        "- PBP role: lagged football-mechanism features only",
        "- identity mode: conditional on a known QB GSIS ID; starter resolver is evaluated separately",
    ]
    md_path = out_dir / "NFL_QB_PASSING_YARDS_BAKEOFF.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    atomic_pointer(root / "data/models/nfl/CURRENT_QB_MODEL_020", str(out_dir.relative_to(root)))

    print("\nNFL QB MODEL 0.2.0 — PASSING-YARDS CHALLENGER BAKE-OFF")
    print(f"PBP source snapshot: {raw_sid}")
    print(f"Official target snapshot: {target_audit.get('officialStatsSnapshotId')}")
    print(f"Development rows: {len(examples):,} · 2016-2024")
    print(f"Chronological OOF: {len(oof):,} rows · 2020-2024")
    print("2025 holdout: SEALED / 0 LABELS READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print(f"Fixed L2: {q20.FIXED_L2} · hyperparameter search NO")
    print("Identity mode: CONDITIONAL ON KNOWN QB · resolver not used in coefficient fit")
    print("\nPOOLED OOF 2020-2024")
    for name in ("baseline_last4",) + q20.CANDIDATES:
        m = pooled[name]
        print(f"  {name}: MAE {m['mae']:.3f} · RMSE {m['rmse']:.3f} · bias {m['bias']:+.3f} · median AE {m['medianAbsoluteError']:.3f}")
    print("\nFOLD MAE")
    for fold in folds:
        m = fold["metrics"]
        print(
            f"  {fold['validationSeason']}: base {m['baseline_last4']['mae']:.3f} · "
            f"A {m['MODEL_A_DIRECT']['mae']:.3f} · B {m['MODEL_B_VOLUME_X_YPA']['mae']:.3f} · C {m['MODEL_C_VOLUME_X_CR_X_YPC']['mae']:.3f}"
        )
    l = selection["leaderVsLast4Baseline"]
    print("\nDEVELOPMENT SELECTION")
    print(f"  leader: {selection['developmentLeader']}")
    print(f"  fold wins: {selection['foldWinsByMae']}")
    print(f"  leader vs last4 MAE delta {l['deltaMae']:+.3f} yd · 95% CI [{l['ci95'][0]:+.3f}, {l['ci95'][1]:+.3f}]")
    print(f"  status: {selection['selectionStatus']}")
    print(f"  next gate: {report['nextGate']}")
    print(f"\nOOF predictions: {pred_path}")
    print(f"Audit: {audit_path}")
    print(f"Report: {md_path}")
    print("PASS QB Model 0.2.0 bakeoff · 2025 sealed · no market data · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

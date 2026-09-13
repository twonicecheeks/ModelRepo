#!/usr/bin/env python3
"""Chronological Phase 2C QB/roster challenger evaluation; 2025 remains unopened."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import json
import os
import shutil
import sys


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def readcsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def canon(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    sys.path.insert(0, str(root / "packages/models/nfl/game"))
    import research_model as rm
    import phase2c_model as pm

    ctx_ptr = root / "data/normalized/nfl/CURRENT_PHASE2C_CONTEXT"
    if not ctx_ptr.exists():
        raise SystemExit("FAIL no Phase2C context pointer; run scripts/nfl/build_phase2c_context.command first")
    sid = ctx_ptr.read_text(encoding="utf-8").strip()
    ctx = root / "data/normalized/nfl/phase2c_context" / sid
    rows = readcsv(ctx / "phase2c_features.csv")
    if any(int(r["season"]) >= 2025 for r in rows):
        raise SystemExit("FAIL 2025 row present in Phase2C development features")

    # Critical holdout boundary: 2025 target rows are skipped before labels are parsed.
    labels: dict[str, int] = {}
    with (root / "data/normalized/nfl/phase1" / sid / "game_targets.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = int(r["game_id"][:4])
            if s >= 2025:
                continue
            if r.get("home_win") in ("0", "0.0", "1", "1.0"):
                labels[r["game_id"]] = int(float(r["home_win"]))

    allowed = set(range(2016, 2025))
    base_ex = rm.examples_from_rows(rows, labels, allowed_seasons=allowed, game_type="REG")
    rowby = {r["game_id"]: r for r in rows}
    if len(base_ex) < 2000:
        raise SystemExit(f"FAIL development sample unexpectedly small: {len(base_ex)}")
    missing_context = [e.game_id for e in base_ex if e.game_id not in rowby]
    if missing_context:
        raise SystemExit(f"FAIL Phase2C context missing {len(missing_context)} development games")

    # Use the exact already-reviewed Phase2A baseline report rather than refitting it.
    phase2a_report_path = root / "data/models/nfl/phase2a" / sid / "DEVELOPMENT_VALIDATION_REPORT.json"
    if not phase2a_report_path.exists():
        raise SystemExit("FAIL exact Phase2A development report missing; run build_phase2_development.command first")
    phase2a = json.loads(phase2a_report_path.read_text(encoding="utf-8"))
    if phase2a.get("sourceSnapshotId") != sid:
        raise SystemExit("FAIL Phase2A report snapshot mismatch")
    integ = phase2a.get("integrity", {})
    if integ.get("holdoutEvaluated") is not False or int(integ.get("holdoutLabelsAdmitted", -1)) != 0:
        raise SystemExit("FAIL Phase2A baseline does not prove sealed 2025 holdout")
    walk = phase2a["selectedModel"]["walkForward"]
    base_l2 = float(walk["selectedL2"])
    chosen = next((x for x in walk["candidates"] if float(x["l2"]) == base_l2), None)
    if chosen is None:
        raise SystemExit("FAIL Phase2A selected L2 candidate missing from report")
    base_metrics = dict(chosen["pooled"])
    base_fold_metrics = {str(int(x["season"])): dict(x) for x in chosen["folds"]}

    base_names = rm.expanded_feature_names()
    selection_folds = (2020, 2021)
    eval_folds = (2022, 2023, 2024)
    context_l2_grid = (0.1, 0.3, 1.0, 3.0)
    configs = {
        "team_plus_qb": (True, False),
        "team_plus_roster": (False, True),
        "team_plus_qb_roster": (True, True),
    }

    def design(e, include_qb: bool, include_roster: bool):
        return pm.combined_vector(
            e.x,
            rowby[e.game_id],
            base_names,
            include_qb=include_qb,
            include_roster=include_roster,
        )

    # Each challenger gets its own shrinkage selected strictly on earlier 2020-2021 folds.
    reg_search: dict[str, dict] = {}
    selected_l2: dict[str, float] = {}
    for name, (iq, ir) in configs.items():
        names = pm.combined_names(base_names, include_qb=iq, include_roster=ir)
        candidates = []
        for lam in context_l2_grid:
            ys: list[int] = []
            ps: list[float] = []
            folds = []
            for season in selection_folds:
                train = [e for e in base_ex if e.season < season]
                test = [e for e in base_ex if e.season == season]
                model = pm.fit_fast_logit(
                    [design(e, iq, ir) for e in train],
                    [e.y for e in train],
                    names,
                    l2=lam,
                )
                pp = [model.predict(design(e, iq, ir)) for e in test]
                yy = [e.y for e in test]
                mm = rm.metric_summary(yy, pp)
                folds.append({"season": season, **mm})
                ys.extend(yy)
                ps.extend(pp)
            candidates.append({"l2": lam, "metrics": rm.metric_summary(ys, ps), "folds": folds})
        candidates.sort(key=lambda x: (x["metrics"]["logLoss"], x["metrics"]["brier"], -x["l2"]))
        reg_search[name] = {"selectionFolds": list(selection_folds), "candidates": candidates}
        selected_l2[name] = float(candidates[0]["l2"])

    # Evaluate only on later 2022-2024 development folds. No row deletion is allowed.
    oof_by: dict[str, list[dict]] = {}
    for name, (iq, ir) in configs.items():
        pred: list[dict] = []
        names = pm.combined_names(base_names, include_qb=iq, include_roster=ir)
        lam = selected_l2[name]
        for season in eval_folds:
            train = [e for e in base_ex if e.season < season]
            test = [e for e in base_ex if e.season == season]
            model = pm.fit_fast_logit(
                [design(e, iq, ir) for e in train],
                [e.y for e in train],
                names,
                l2=lam,
            )
            for e in test:
                pred.append({"season": season, "game_id": e.game_id, "y": e.y, "p": model.predict(design(e, iq, ir))})
        oof_by[name] = pred

    expected_n = int(base_metrics["n"])
    eval_examples = [e for e in base_ex if e.season in eval_folds]
    if len(eval_examples) != expected_n:
        raise SystemExit(f"FAIL Phase2C evaluation sample {len(eval_examples)} != exact Phase2A baseline N {expected_n}")
    expected_ids = {e.game_id for e in eval_examples}
    for name, pred in oof_by.items():
        ids = {r["game_id"] for r in pred}
        if len(pred) != expected_n or ids != expected_ids:
            raise SystemExit(f"FAIL {name} is not paired to exact Phase2A evaluation games")

    metrics: dict[str, dict] = {"base_team": base_metrics}
    fold_metrics: dict[str, dict] = {"base_team": base_fold_metrics}
    for name, pred in oof_by.items():
        metrics[name] = rm.metric_summary([r["y"] for r in pred], [r["p"] for r in pred])
        fold_metrics[name] = {}
        for season in eval_folds:
            rr = [r for r in pred if r["season"] == season]
            fold_metrics[name][str(season)] = rm.metric_summary([r["y"] for r in rr], [r["p"] for r in rr])
            base_fold_n = int(base_fold_metrics[str(season)]["n"])
            if len(rr) != base_fold_n:
                raise SystemExit(f"FAIL {name} season {season} N {len(rr)} != Phase2A N {base_fold_n}")

    improvements = {}
    for name in configs:
        m = metrics[name]
        improvements[name] = {
            "brier": float(base_metrics["brier"]) - float(m["brier"]),
            "logLoss": float(base_metrics["logLoss"]) - float(m["logLoss"]),
            "accuracy": float(m["accuracy"]) - float(base_metrics["accuracy"]),
        }
    ranked = sorted(
        configs,
        key=lambda n: (metrics[n]["logLoss"], metrics[n]["brier"], -metrics[n]["accuracy"], n),
    )
    best = ranked[0]
    best_imp = improvements[best]
    statistical_verdict = (
        "OUTPERFORMS_BASE_ON_BRIER_AND_LOGLOSS"
        if best_imp["brier"] > 0 and best_imp["logLoss"] > 0
        else "NO_CONTEXT_CHALLENGER_BEATS_BASE_ON_BOTH"
    )

    # Fit best context challenger on all 2016-2024 development examples only for coefficient diagnostics.
    biq, bir = configs[best]
    best_names = pm.combined_names(base_names, include_qb=biq, include_roster=bir)
    final = pm.fit_fast_logit(
        [design(e, biq, bir) for e in base_ex],
        [e.y for e in base_ex],
        best_names,
        l2=selected_l2[best],
    )
    coeff = sorted(
        ({"feature": n, "coefficient": c, "abs": abs(c)} for n, c in zip(best_names, final.coefficients)),
        key=lambda x: (-x["abs"], x["feature"]),
    )[:30]

    # Weekly-roster files identify week-level roster state, but do not expose an exact
    # pre-kickoff snapshot timestamp. Therefore roster/QB availability proxies remain
    # a research challenger even if they improve metrics; this source-timing gate must
    # be resolved before freezing a production specification.
    source_timing_gate = "WEEKLY_ROSTER_EXACT_PREGAME_TIMESTAMP_NOT_PROVEN"
    promotion_verdict = (
        "KEEP_RESEARCH_CHALLENGER_SOURCE_TIMING_GATE"
        if statistical_verdict.startswith("OUTPERFORMS")
        else "DO_NOT_PROMOTE_YET"
    )

    spec = {
        "phase": "NFL_2.9.0_PHASE2C",
        "status": "DEVELOPMENT_CHALLENGER_NOT_FROZEN",
        "holdoutSeason": 2025,
        "holdoutEvaluated": False,
        "holdoutLabelsAdmitted": 0,
        "marketFieldsAllowed": False,
        "oddsPapiRequests": 0,
        "sourceSnapshotId": sid,
        "featureLineage": pm.LINEAGE,
        "exactPhase2ABaseL2": base_l2,
        "contextL2Grid": list(context_l2_grid),
        "contextL2SelectionFolds": list(selection_folds),
        "selectedContextL2": selected_l2,
        "evaluationFolds": list(eval_folds),
        "bestContextChallenger": best,
        "statisticalVerdict": statistical_verdict,
        "promotionVerdict": promotion_verdict,
        "sourceTimingGate": source_timing_gate,
    }
    spec_sha = hashlib.sha256(canon(spec)).hexdigest()
    report = {
        "generatedAt": now(),
        "sourceSnapshotId": sid,
        "integrity": {
            "holdoutEvaluated": False,
            "holdoutLabelsAdmitted": 0,
            "marketFieldsAllowed": False,
            "oddsPapiRequests": 0,
            "exactPhase2ABaselineReused": True,
            "pairedEvaluationGames": expected_n,
        },
        "metrics": metrics,
        "foldMetrics": fold_metrics,
        "regularization": {
            "baseL2": base_l2,
            "baseSource": "PHASE2A_DEVELOPMENT_VALIDATION_REPORT",
            "contextSelectionFolds": list(selection_folds),
            "search": reg_search,
            "selectedByModel": selected_l2,
        },
        "extendedVsBase": improvements,
        "bestContextChallenger": best,
        "statisticalVerdict": statistical_verdict,
        "promotionVerdict": promotion_verdict,
        "sourceTimingGate": source_timing_gate,
        "topStandardizedCoefficients": coeff,
        "notes": [
            "The Phase2A baseline metrics are read from the exact previously reviewed report; they are not refit or approximated.",
            "Each context challenger selects L2 on 2020-2021 only; reported comparison is 2022-2024.",
            "Observed primary-QB history is strictly lagged; the target game's PBP never creates its own pregame QB features.",
            "Target-week weekly-roster status is a research availability proxy, not a timestamp-verified pre-kickoff starter source.",
            "No verified live starter-QB adapter exists yet; Phase2C cannot produce a 2026 production probability.",
        ],
    }

    out = root / "data/models/nfl/phase2c" / sid
    if out.exists():
        raise SystemExit(f"Refusing overwrite immutable Phase2C model output: {out}")
    staging = out.parent / ("." + sid + ".staging")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        (staging / "PHASE2C_SPEC.json").write_bytes(canon(spec))
        (staging / "PHASE2C_SPEC.sha256").write_text(spec_sha + "  PHASE2C_SPEC.json\n", encoding="utf-8")
        (staging / "PHASE2C_BAKEOFF.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        order = ["base_team", "team_plus_qb", "team_plus_roster", "team_plus_qb_roster"]
        md = [
            "# MODEL NFL 2.9.0 Phase 2C — QB / Roster Transition Bake-off",
            "",
            "**2025 HOLDOUT REMAINS SEALED. NOT PRODUCTION.**",
            "",
            f"Source snapshot: `{sid}`",
            "",
            "## Paired chronological performance (2022–2024)",
            "",
            "| Model | N | Brier | Log loss | Accuracy |",
            "|---|---:|---:|---:|---:|",
        ]
        for n in order:
            m = metrics[n]
            md.append(f"| {n} | {m['n']} | {m['brier']:.5f} | {m['logLoss']:.5f} | {m['accuracy']:.3f} |")
        md += [
            "",
            "## Year-by-year stability — best context challenger vs exact Phase 2A base",
            "",
            "| Season | Base Brier | Context Brier | Base LogLoss | Context LogLoss |",
            "|---:|---:|---:|---:|---:|",
        ]
        for season in eval_folds:
            b = fold_metrics["base_team"][str(season)]
            e = fold_metrics[best][str(season)]
            md.append(
                f"| {season} | {b['brier']:.5f} | {e['brier']:.5f} | {b['logLoss']:.5f} | {e['logLoss']:.5f} |"
            )
        md += ["", "## Context challengers vs exact Phase 2A base", ""]
        for name in configs:
            imp = improvements[name]
            md.append(
                f"- `{name}` — Brier improvement **{imp['brier']:+.5f}** · "
                f"log-loss improvement **{imp['logLoss']:+.5f}** · accuracy change **{imp['accuracy']:+.3f}** · "
                f"selected λ **{selected_l2[name]:g}**"
            )
        md += [
            "",
            f"Best context challenger: **{best}**",
            f"Statistical verdict: **{statistical_verdict}**",
            f"Promotion verdict: **{promotion_verdict}**",
            "",
            "## Source-timing gate",
            "",
            f"- **{source_timing_gate}**",
            "- nflverse weekly rosters are useful week-level roster state, but this Phase 2C release does not claim an exact archived pre-kickoff timestamp for each historical row.",
            "- Therefore any QB/roster improvement remains research evidence until that provenance is resolved or replaced with a timestamp-verifiable source.",
            "",
            "## Regularization discipline",
            "",
            f"- Exact Phase2A base: λ={base_l2:g} from the previously generated Phase2A report.",
            "- Each context model selects λ independently on **2020–2021 only**.",
            "- Model comparison is **2022–2024 only**, on exactly the Phase2A evaluation games.",
            "",
            f"## Top standardized coefficients — `{best}` development fit",
            "",
        ]
        for c in coeff[:18]:
            md.append(f"- `{c['feature']}`: {c['coefficient']:+.4f}")
        md += [
            "",
            "## Integrity",
            "",
            "- 2025 labels admitted: **0**",
            "- 2025 evaluated: **NO**",
            "- sportsbook/market fields: **DISALLOWED**",
            "- OddsPapi requests: **0**",
            "- live starter-QB verification: **NOT YET WIRED**",
            "",
            "## Rule",
            "",
            "Do **not** open 2025 from this report. First review whether QB/roster context improves both proper scoring rules, especially the weak 2023 fold, and resolve the historical roster timing gate before freezing the feature specification.",
            "",
        ]
        (staging / "PHASE2C_BAKEOFF.md").write_text("\n".join(md), encoding="utf-8")
        os.replace(staging, out)
        (root / "data/models/nfl/CURRENT_PHASE2C").write_text(sid + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print("MODEL NFL 2.9.0 PHASE 2C — QB / ROSTER TRANSITION CHALLENGER")
    print(f"PASS exact paired 2022-2024 games: {expected_n}")
    print(f"PASS exact Phase2A baseline reused: λ={base_l2:g}")
    print("PASS context λ selection: 2020-2021 only · per challenger")
    print(f"PASS best context challenger: {best} · λ={selected_l2[best]:g}")
    print(f"PASS statistical verdict: {statistical_verdict}")
    print(f"PASS promotion gate: {promotion_verdict}")
    print("PASS 2025 holdout: NOT EVALUATED / 0 labels admitted")
    print("PASS market fields disallowed · OddsPapi requests 0")
    print(f"REPORT: {out / 'PHASE2C_BAKEOFF.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

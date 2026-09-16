#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import json
import os
import sys
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def fmt(v, digits=5):
    return "NA" if v is None else f"{float(v):.{digits}f}"


def pp(v):
    return "NA" if v is None else f"{100.0 * float(v):+.3f} pp"


def main() -> int:
    ap = argparse.ArgumentParser(description="Development-only State Intelligence 0.1.4 paired game-model challenger bake-off")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    ap.add_argument("--evaluation-seasons", default="2021-2024")
    ap.add_argument("--min-prior-third-downs", type=int, default=20)
    ap.add_argument("--min-prior-exposed-dropbacks", type=int, default=20)
    ap.add_argument("--bootstrap-reps", type=int, default=1000)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    sys.path.insert(0, str(model_dir))
    import research_model as rm
    import challenger_models as cm
    import state_component_persistence_research as persistence
    import state_feature_challenger_014 as sc

    seasons = list(sc.assert_development_only(parse_seasons(args.seasons)))
    eval_seasons = parse_seasons(args.evaluation_seasons)
    if any(s not in seasons for s in eval_seasons):
        raise ValueError("evaluation seasons must be a subset of development seasons")
    if any(s >= 2025 for s in eval_seasons):
        raise ValueError("2025 holdout and 2026 prospective seasons are forbidden")

    # Phase 1 game features / labels.
    phase1_ptr = root / "data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"
    if not phase1_ptr.exists():
        raise FileNotFoundError("CURRENT_PHASE1_SNAPSHOT missing")
    sid = phase1_ptr.read_text(encoding="utf-8").strip()
    phase1 = root / "data/normalized/nfl/phase1" / sid
    feature_rows = read_csv(phase1 / "pregame_features.csv")
    targets: dict[str, int] = {}
    for row in read_csv(phase1 / "game_targets.csv"):
        value = row.get("home_win")
        if value in ("0", "0.0", "1", "1.0"):
            targets[str(row.get("game_id") or "")] = int(float(value))
    dev_rows = [
        r for r in feature_rows
        if int(r.get("season") or 0) in set(seasons) and str(r.get("game_type") or "") == "REG"
    ]
    examples = rm.examples_from_rows(dev_rows, targets, allowed_seasons=set(seasons))
    examples = sorted(examples, key=lambda e: (e.season, e.week, e.game_id))
    if len(examples) < 1000:
        raise ValueError(f"development game sample unexpectedly small: {len(examples)}")

    # Reuse the pre-existing Phase 2B team-L2 regularization choice. State features
    # get no feature-specific hyperparameter search in this audit.
    phase2b_ptr = root / "data/models/nfl/CURRENT_PHASE2B"
    if not phase2b_ptr.exists():
        raise FileNotFoundError("CURRENT_PHASE2B missing; State 0.1.4 requires the existing Phase 2B development baseline")
    phase2b_sid = phase2b_ptr.read_text(encoding="utf-8").strip()
    if phase2b_sid != sid:
        raise ValueError(f"Phase 2B / Phase 1 source snapshot mismatch: {phase2b_sid} != {sid}")
    phase2b_report = json.loads((root / "data/models/nfl/phase2b" / sid / "CHALLENGER_BAKEOFF.json").read_text(encoding="utf-8"))
    team_l2 = float(phase2b_report["selection"]["teamL2"])

    # State snapshot must originate from the exact same immutable nflverse source.
    state_ptr = root / "data/normalized/nfl/CURRENT_NFL_STATE_INTELLIGENCE"
    if not state_ptr.exists():
        raise FileNotFoundError("CURRENT_NFL_STATE_INTELLIGENCE missing")
    state_dir = root / state_ptr.read_text(encoding="utf-8").strip()
    state_audit = json.loads((state_dir / "NFL_STATE_INTELLIGENCE_AUDIT.json").read_text(encoding="utf-8"))
    if str(state_audit.get("sourceSnapshotId")) != sid:
        raise ValueError(f"State / Phase 1 source snapshot mismatch: {state_audit.get('sourceSnapshotId')} != {sid}")
    if state_audit.get("marketDependency") is not False or state_audit.get("frozenOmegaMutation") is not False:
        raise ValueError("State Intelligence boundary drift")

    state_rows: list[dict] = []
    for season in seasons:
        path = state_dir / f"NFL_STATE_INTELLIGENCE_SNAPS_{season}.jsonl"
        if not path.exists():
            raise FileNotFoundError(path)
        rows = load_jsonl(path)
        state_rows.extend(rows)
        print(f"PASS {season} · state snaps {len(rows):,}")

    records = persistence.build_persistence_records(
        state_rows,
        min_prior_third_downs=args.min_prior_third_downs,
        min_prior_exposed_dropbacks=args.min_prior_exposed_dropbacks,
    )
    games = [
        {"game_id": e.game_id, "home_team": e.home_team, "away_team": e.away_team}
        for e in examples
    ]
    game_state = sc.build_game_state_features(records, games)

    base_names = tuple(rm.expanded_feature_names())
    variants = list(sc.VARIANTS)
    paired_rows: dict[str, list[dict]] = {v: [] for v in variants}
    folds: list[dict] = []
    coeffs: dict[str, list[dict]] = {v: [] for v in variants}

    for season in eval_seasons:
        train = [e for e in examples if e.season < season]
        test = [e for e in examples if e.season == season]
        if not train or not test:
            continue

        base_model = cm.fit_generic_logit(
            [e.x for e in train], [e.y for e in train], base_names, l2=team_l2
        )
        base_ps = {e.game_id: base_model.predict(e.x) for e in test}
        fold = {
            "season": season,
            "trainGames": len(train),
            "testGames": len(test),
            "baseline": rm.metric_summary([e.y for e in test], [base_ps[e.game_id] for e in test]),
            "variants": {},
        }

        for variant in variants:
            state_names = sc.state_feature_names(variant)
            names = base_names + state_names
            train_x = [sc.augment_vector(e.x, game_state.get(e.game_id), variant) for e in train]
            test_x = [sc.augment_vector(e.x, game_state.get(e.game_id), variant) for e in test]
            mdl = cm.fit_generic_logit(train_x, [e.y for e in train], names, l2=team_l2)
            cand_ps = [mdl.predict(x) for x in test_x]
            ys = [e.y for e in test]
            available_n = sum(1 for e in test if sc.availability(game_state.get(e.game_id), variant))
            fold["variants"][variant] = {
                **rm.metric_summary(ys, cand_ps),
                "featureAvailableGames": available_n,
                "featureCoveragePct": 100.0 * available_n / len(test) if test else None,
            }
            cmap = dict(zip(mdl.names, mdl.coefficients))
            coeffs[variant].append({
                "season": season,
                **{n: cmap.get(n) for n in state_names if not n.startswith("missing__")},
            })
            for e, cp in zip(test, cand_ps):
                paired_rows[variant].append({
                    "game_id": e.game_id,
                    "season": e.season,
                    "week": e.week,
                    "y": e.y,
                    "baseline_p": base_ps[e.game_id],
                    "candidate_p": cp,
                    "feature_available": sc.availability(game_state.get(e.game_id), variant),
                })
        folds.append(fold)
        print(f"PASS fold {season} · train {len(train):,} · test {len(test):,}")

    if not folds:
        raise ValueError("no evaluation folds produced")

    base_all = paired_rows[variants[0]]
    baseline_metrics = rm.metric_summary(
        [r["y"] for r in base_all], [r["baseline_p"] for r in base_all]
    )
    candidate_results: dict[str, dict] = {}
    for i, variant in enumerate(variants):
        rows = paired_rows[variant]
        cand_metrics = rm.metric_summary([r["y"] for r in rows], [r["candidate_p"] for r in rows])
        boot = sc.paired_week_cluster_bootstrap(rows, reps=args.bootstrap_reps, seed=20260916 + i)
        season_details = []
        improved = 0
        for fold in folds:
            base_ll = float(fold["baseline"]["logLoss"])
            cand_ll = float(fold["variants"][variant]["logLoss"])
            better = cand_ll < base_ll
            improved += 1 if better else 0
            season_details.append({
                "season": fold["season"],
                "baselineLogLoss": base_ll,
                "candidateLogLoss": cand_ll,
                "logLossDelta": cand_ll - base_ll,
                "baselineBrier": float(fold["baseline"]["brier"]),
                "candidateBrier": float(fold["variants"][variant]["brier"]),
                "brierDelta": float(fold["variants"][variant]["brier"]) - float(fold["baseline"]["brier"]),
                "featureCoveragePct": fold["variants"][variant]["featureCoveragePct"],
            })
        available = [r for r in rows if r["feature_available"]]
        available_pair = None
        if available:
            available_pair = {
                "n": len(available),
                "baseline": rm.metric_summary([r["y"] for r in available], [r["baseline_p"] for r in available]),
                "candidate": rm.metric_summary([r["y"] for r in available], [r["candidate_p"] for r in available]),
            }
        gate = sc.promotion_signal(
            boot, seasons_improved_log_loss=improved, seasons_total=len(season_details)
        )
        candidate_results[variant] = {
            "metrics": cand_metrics,
            "pairedBootstrap": boot,
            "seasonFolds": season_details,
            "seasonsImprovedLogLoss": improved,
            "seasonsTotal": len(season_details),
            "featureAvailableGames": sum(1 for r in rows if r["feature_available"]),
            "featureCoveragePct": 100.0 * sum(1 for r in rows if r["feature_available"]) / len(rows) if rows else None,
            "availableOnlyDiagnostic": available_pair,
            "stateCoefficientsByFold": coeffs[variant],
            "promotionSignal": gate,
        }

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/state_intelligence_014" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    result = {
        "version": sc.VERSION,
        "lineage": sc.LINEAGE,
        "createdAt": utc_now(),
        "runId": run_id,
        "sourceSnapshotId": sid,
        "sourcePhase1": str(phase1.relative_to(root)),
        "sourceStateDirectory": str(state_dir.relative_to(root)),
        "developmentSeasons": seasons,
        "evaluationSeasons": eval_seasons,
        "sealedHoldoutSeason": 2025,
        "prospectiveSeason": 2026,
        "holdoutOpened": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "trainingOrRefitProductionPerformed": False,
        "baseline": {
            "model": "Phase2A team-feature L2 logistic re-fit chronologically per fold",
            "l2Source": "existing Phase2B development selection; no State-0.1.4-specific tuning",
            "l2": team_l2,
            "metrics": baseline_metrics,
        },
        "stateFeatureConstruction": {
            "minPriorOffenseThirdDowns": args.min_prior_third_downs,
            "minPriorDefenseExposedDropbacks": args.min_prior_exposed_dropbacks,
            "sameWeekHistoryAllowed": False,
            "offenseExposureAdvantage": "away offense lagged exposed-third-down share minus home offense share",
            "defenseExposedSackAdvantage": "home defense lagged exposed-state sack conversion minus away defense conversion",
            "missingness": "explicit indicators; no fabricated early-season priors",
        },
        "folds": folds,
        "candidates": candidate_results,
    }
    json_path = out_dir / "NFL_STATE_FEATURE_CHALLENGER_BAKEOFF.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        "NFL STATE INTELLIGENCE 0.1.4 — PREGAME GAME-MODEL CHALLENGER BAKE-OFF",
        "",
        f"Source snapshot: {sid}",
        f"Development seasons admitted: {seasons[0]}-{seasons[-1]}",
        f"Chronological evaluation seasons: {','.join(map(str, eval_seasons))}",
        "2025 holdout: SEALED / NOT READ",
        "2026 prospective: NOT READ",
        "Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO",
        f"Shared L2 from pre-existing Phase2B development selection: {team_l2}",
        "State-feature-specific hyperparameter search: NONE",
        "",
        "PAIRED ALL-GAME PERFORMANCE",
        f"  BASELINE: n={baseline_metrics['n']} · logloss {baseline_metrics['logLoss']:.5f} · brier {baseline_metrics['brier']:.5f} · accuracy {baseline_metrics['accuracy']:.3f}",
    ]
    for variant in variants:
        r = candidate_results[variant]
        m = r["metrics"]
        bm = r["pairedBootstrap"]["metrics"]
        lines += [
            "",
            f"  {variant}:",
            f"    n={m['n']} · logloss {m['logLoss']:.5f} · brier {m['brier']:.5f} · accuracy {m['accuracy']:.3f}",
            f"    feature coverage: {r['featureAvailableGames']}/{m['n']} ({r['featureCoveragePct']:.2f}%)",
            f"    logloss delta vs baseline: {bm['log_loss_delta']['observed']:+.6f} [{bm['log_loss_delta']['ci95_low']:+.6f}, {bm['log_loss_delta']['ci95_high']:+.6f}]",
            f"    brier delta vs baseline: {bm['brier_delta']['observed']:+.6f} [{bm['brier_delta']['ci95_low']:+.6f}, {bm['brier_delta']['ci95_high']:+.6f}]",
            f"    season logloss direction: improved {r['seasonsImprovedLogLoss']}/{r['seasonsTotal']}",
            f"    gate: {r['promotionSignal']['status']}",
        ]
        for sf in r["seasonFolds"]:
            lines.append(
                f"      {sf['season']}: LL delta {sf['logLossDelta']:+.6f} · Brier delta {sf['brierDelta']:+.6f} · coverage {sf['featureCoveragePct']:.1f}%"
            )
        coef_text = []
        for cf in r["stateCoefficientsByFold"]:
            vals = [f"{k}={v:+.4f}" for k, v in cf.items() if k != "season" and v is not None]
            coef_text.append(f"{cf['season']}: " + ", ".join(vals))
        if coef_text:
            lines.append("    standardized state coefficients by fold:")
            lines.extend(f"      {x}" for x in coef_text)

    lines += [
        "",
        "Interpretation guard:",
        "  This is an incremental development challenger against the existing team baseline, not a production model.",
        "  Candidate parameters are fit only on seasons earlier than each evaluation season; State-0.1.4 adds no hyperparameter tuning.",
        "  The conservative gate only authorizes further challenger work; it cannot promote a feature into production or open 2025.",
        "",
        f"JSON: {json_path}",
    ]
    txt_path = out_dir / "NFL_STATE_FEATURE_CHALLENGER_BAKEOFF.txt"
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    current = root / "data/models/nfl/CURRENT_STATE_INTELLIGENCE_014"
    current.parent.mkdir(parents=True, exist_ok=True)
    tmp = current.with_name("." + current.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
    os.replace(tmp, current)

    print()
    print(txt_path.read_text(encoding="utf-8"))
    print("PASS development-only State 0.1.4 challenger bake-off · 2025 holdout sealed · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

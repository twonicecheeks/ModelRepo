#!/usr/bin/env python3
"""OMEGA 0.15 — discrete T+A distribution research foundation.

Purpose:
  Convert the frozen H008+H012 independent mean count into honest line-specific
  probabilities.  This script fits/compares only pre-2025 count distributions.

Hard boundaries:
  - Frozen mean model is unchanged.
  - 2025 outcome rows are never read or scored.
  - Sportsbook prices/market fields are never read.
  - Candidate architecture is predeclared: Poisson, global NB2, role-tier NB2.
  - 2021-2023 chronological folds choose the architecture.
  - 2024 is confirmation only and does not choose the architecture.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

SCHEMA = "OMEGA_TACKLE_DISTRIBUTION_FOUNDATION_0.15"
SID_EXPECTED = "20260910T205221Z_58d8156a"
FROZEN_SPEC_SHA = "c2ca80b6a144c3aa86bc41bdb82f6f5618ffa279a38f4c6d358025ed7fbd69fb"
CANDIDATES = ("POISSON", "NB_GLOBAL", "NB_ROLE")
SELECTION_YEARS = (2021, 2022, 2023)
NLL_TIE_TOL = 0.001


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        x = float(v)
        return default if math.isnan(x) else x
    except (TypeError, ValueError):
        return default


def candidate_complexity(name: str) -> int:
    return {"POISSON": 0, "NB_GLOBAL": 1, "NB_ROLE": 2}[name]


def select_architecture(summary: list[dict[str, Any]]) -> str:
    best_nll = min(float(x["meanCountNLL"]) for x in summary)
    near = [x for x in summary if float(x["meanCountNLL"]) <= best_nll + NLL_TIE_TOL]
    near.sort(key=lambda x: (float(x["meanThresholdBrier"]), candidate_complexity(str(x["model"]))))
    return str(near[0]["model"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()

    sys.path.insert(0, str(root / "packages/models/nfl/omega"))
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import tackle_count_distribution as dist

    # ------------------------------------------------------------
    # Immutable lineage / post-holdout boundary checks.
    # ------------------------------------------------------------
    frozen_ptr = root / "data/models/nfl/CURRENT_OMEGA_TACKLE_FROZEN"
    seal_ptr = root / "data/models/nfl/CURRENT_OMEGA_TACKLE_POST_HOLDOUT_SEAL"
    consumed = root / "data/models/nfl/OMEGA_TACKLE_2025_CONSUMED.json"
    for p in (frozen_ptr, seal_ptr, consumed):
        if not p.exists():
            raise SystemExit(f"FAIL prerequisite missing: {p}")
    sid = frozen_ptr.read_text(encoding="utf-8").strip()
    if sid != SID_EXPECTED or seal_ptr.read_text(encoding="utf-8").strip() != sid:
        raise SystemExit("FAIL OMEGA source/frozen/post-holdout pointers disagree")
    frozen_spec_path = root / "data/models/nfl/omega_tackle_frozen" / sid / "OMEGA_TACKLE_FROZEN_SPEC.json"
    if not frozen_spec_path.exists() or sha256_file(frozen_spec_path) != FROZEN_SPEC_SHA:
        raise SystemExit("FAIL frozen OMEGA spec hash drift")
    frozen_spec = json.loads(frozen_spec_path.read_text(encoding="utf-8"))
    c = json.loads(consumed.read_text(encoding="utf-8"))
    if c.get("status") != "CONSUMED_FOREVER_FOR_OMEGA_TACKLE_TUNING":
        raise SystemExit("FAIL OMEGA 2025 is not permanently consumed")

    # ------------------------------------------------------------
    # Pre-2025 historical sources only.  No 2025 score/report read.
    # ------------------------------------------------------------
    ptrs = {
        "foundation": root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION",
        "exposure": root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE",
        "baseline": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE",
        "role": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER",
        "opp": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_OPPORTUNITY_CHALLENGER",
        "foot": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_FOOTPRINT_CHALLENGER",
    }
    for p in ptrs.values():
        if not p.exists():
            raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    if any(p.read_text(encoding="utf-8").strip() != sid for p in ptrs.values()):
        raise SystemExit("FAIL OMEGA prerequisite pointers disagree")

    foundation = root / "data/normalized/nfl/omega_tackle" / sid
    exposure = root / "data/normalized/nfl/omega_tackle_exposure" / sid
    base = root / "data/models/nfl/omega_tackle_02" / sid
    role = root / "data/models/nfl/omega_tackle_022_exposure" / sid
    opp = root / "data/models/nfl/omega_tackle_03_opportunity" / sid
    foot = root / "data/models/nfl/omega_tackle_04_footprint" / sid

    req = [
        foundation / "OMEGA_TACKLE_FOUNDATION_AUDIT.json",
        foundation / "omega_tackle_play_opportunities.csv",
        foundation / "omega_tackle_credit_events.csv",
        exposure / "OMEGA_TACKLE_EXPOSURE_AUDIT.json",
        exposure / "omega_tackle_exposure_player_games.csv",
        base / "OMEGA_0.2_AUDIT.json",
        role / "OMEGA_0.2.2_AUDIT.json",
        role / "omega_2024_exposure_challenger_validation.csv",
        opp / "OMEGA_0.3_AUDIT.json",
        foot / "OMEGA_0.4_AUDIT.json",
        foot / "omega_2024_footprint_validation.csv",
    ]
    for p in req:
        if not p.exists():
            raise SystemExit(f"FAIL required historical source missing: {p}")

    fa = json.loads(req[0].read_text(encoding="utf-8"))
    ea = json.loads(req[3].read_text(encoding="utf-8"))
    ba = json.loads(req[5].read_text(encoding="utf-8"))
    ra = json.loads(req[6].read_text(encoding="utf-8"))
    oa = json.loads(req[8].read_text(encoding="utf-8"))
    fpa = json.loads(req[9].read_text(encoding="utf-8"))
    if str(ra.get("verdict")) != "H012_EXPOSURE_CHALLENGER_PASS":
        raise SystemExit("FAIL H012 is not frozen PASS")
    if str(oa.get("verdict")) != "H011_FAIL":
        raise SystemExit("FAIL H011 expected rejected")
    if str(fpa.get("verdict")) != "H008_TACKLE_OPPORTUNITY_FOOTPRINT_PASS":
        raise SystemExit("FAIL H008 is not frozen PASS")
    if sha256_file(req[9]) != frozen_spec.get("auditHashes", {}).get("h008"):
        raise SystemExit("FAIL H008 audit hash drift from frozen spec")

    # Historical audit seals must still show no 2025 reads / market contamination.
    seal_values = [
        fa.get("omegaHoldoutPbpRowsRead", 0),
        ea.get("omegaHoldoutRowsRead", 0),
        ba.get("integrity", {}).get("omega2025RowsRead", 0),
        ra.get("integrity", {}).get("omega2025RowsRead", 0),
        oa.get("integrity", {}).get("omega2025RowsRead", 0),
        fpa.get("integrity", {}).get("omega2025RowsRead", 0),
    ]
    if any(int(x) != 0 for x in seal_values):
        raise SystemExit("FAIL inherited historical source shows 2025 row access")

    exposure_rows = read_csv(req[4])
    plays = read_csv(req[1])
    events = read_csv(req[2])
    if any(int(num(r.get("season"))) >= 2025 for r in exposure_rows + plays + events):
        raise SystemExit("FAIL OMEGA 0.15 attempted to read 2025+ historical rows")

    # ------------------------------------------------------------
    # Reconstruct the frozen H008 mean for 2018-2023, then use the
    # exact already-written 2024 H008 confirmation rows.
    # ------------------------------------------------------------
    team_outcomes = xb.aggregate_team_game_outcomes(plays, exposure_rows)
    team_rows = xb.build_team_pregame_rows(team_outcomes)
    team_snap_totals = xb.estimate_team_defensive_snaps(exposure_rows)
    role_rows = er.build_exposure_pregame_rows(exposure_rows, team_snap_totals)
    family_outcomes = tf.aggregate_team_family_opportunities(plays)
    family_share_rows = tf.build_team_family_share_pregame_rows(family_outcomes)
    family_share_by_season: dict[int, dict[tuple[str, str], dict[str, float]]] = defaultdict(dict)
    for r in family_share_rows:
        family_share_by_season[int(r["season"])][(r["game_id"], r["defense_team"])] = {
            f: float(r[f"pred_share_{f}"]) for f in tf.FAMILIES
        }
    player_family_credits = tf.aggregate_player_family_credits(events)
    topo_rows = tf.build_player_topology_rows(exposure_rows, family_outcomes, player_family_credits, team_snap_totals)
    mismatch = [r for r in topo_rows if abs(float(r["actual_family_credit_sum"]) - float(r["actual_xtc"])) > 1e-9]
    if mismatch:
        raise SystemExit(f"FAIL inherited H008 family-credit reconciliation drift: {len(mismatch)}")

    xto_l2 = float(ba["selection"]["xTOL2"])
    role_l2 = float(ra["selection"]["selectedL2"])
    h008_alpha = float(fpa["selection"]["familyOpportunityShrinkageAlpha"])
    if (xto_l2, role_l2, h008_alpha) != (0.3, 0.01, 50.0):
        raise SystemExit("FAIL frozen H008/H012 constants drift")

    hist: list[dict[str, Any]] = []
    for year in range(2018, 2024):
        ttrain = [r for r in team_rows if 2017 <= int(r["season"]) < year]
        tval = [r for r in team_rows if int(r["season"]) == year]
        rrtrain = [r for r in role_rows if 2017 <= int(r["season"]) < year]
        rrval = [r for r in role_rows if int(r["season"]) == year]
        pval = [r for r in topo_rows if int(r["season"]) == year]
        if not ttrain or not tval or not rrtrain or not rrval or not pval:
            continue
        xm = xb.fit_ridge(ttrain, target_key="actual_opportunity_plays", l2=xto_l2)
        em = er.fit_ridge(rrtrain, role_l2)
        xpred = {(r["game_id"], r["defense_team"]): xm.predict([float(r[n]) for n in xb.TEAM_FEATURE_NAMES]) for r in tval}
        epred = {(r["game_id"], r["team"], r["player_id"]): em.predict(r) for r in rrval}
        scored = tf.score_rows(pval, alpha=h008_alpha, xto_predictions=xpred, exposure_predictions=epred, family_share_predictions=family_share_by_season.get(year, {}))
        for r in scored:
            k = (r["game_id"], r["team"], r["player_id"])
            if k not in epred:
                continue
            z = dict(r)
            z["predicted_xtc"] = float(r["topology_xtc"])
            z["predicted_snap_share"] = min(1.0, max(0.0, float(epred[k])))
            z["role_tier"] = dist.role_tier(z["predicted_snap_share"])
            hist.append(z)
    if not hist:
        raise SystemExit("FAIL no reconstructed pre-2024 H008 predictions")

    role_2024 = read_csv(req[7])
    role_map_2024 = {(r.get("game_id"), r.get("team"), r.get("player_id")): r for r in role_2024}
    exact_2024 = []
    for r in read_csv(req[10]):
        k = (r.get("game_id"), r.get("team"), r.get("player_id"))
        rr = role_map_2024.get(k)
        if rr is None:
            continue
        z = dict(r)
        z["predicted_xtc"] = num(r.get("topology_xtc"))
        z["predicted_snap_share"] = min(1.0, max(0.0, num(rr.get("challenger_snap_share"))))
        z["role_tier"] = dist.role_tier(z["predicted_snap_share"])
        exact_2024.append(z)
    if not exact_2024:
        raise SystemExit("FAIL no exact frozen 2024 H008 confirmation rows")

    all_pre2025 = hist + exact_2024
    if any(int(num(r.get("season"))) >= 2025 for r in all_pre2025):
        raise SystemExit("FAIL reconstructed distribution data includes 2025")

    # ------------------------------------------------------------
    # Precommitted chronological architecture selection.
    # ------------------------------------------------------------
    fold_rows: list[dict[str, Any]] = []
    for year in SELECTION_YEARS:
        train = [r for r in hist if int(num(r.get("season"))) < year]
        val = [r for r in hist if int(num(r.get("season"))) == year]
        if not train or not val:
            raise SystemExit(f"FAIL missing chronological distribution fold {year}")
        for model in CANDIDATES:
            params = dist.fit_params(train, model)
            met = dist.evaluate_rows(val, model, params)
            fold_rows.append({
                "validationSeason": year,
                "model": model,
                "trainRows": len(train),
                "validationRows": len(val),
                "countNLL": met["countNLL"],
                "thresholdBrier": met["thresholdBrier"],
                "paramsJson": json.dumps(params, sort_keys=True, separators=(",", ":")),
            })

    summary = []
    for model in CANDIDATES:
        rr = [r for r in fold_rows if r["model"] == model]
        summary.append({
            "model": model,
            "folds": len(rr),
            "meanCountNLL": fmean(float(r["countNLL"]) for r in rr),
            "meanThresholdBrier": fmean(float(r["thresholdBrier"]) for r in rr),
            "complexityRank": candidate_complexity(model),
        })
    selected = select_architecture(summary)

    # Params fit through 2023 for untouched 2024 confirmation.
    train_through_2023 = [r for r in hist if int(num(r.get("season"))) <= 2023]
    confirm_params = dist.fit_params(train_through_2023, selected)
    confirm_all = []
    for model in CANDIDATES:
        params = dist.fit_params(train_through_2023, model)
        met = dist.evaluate_rows(exact_2024, model, params)
        confirm_all.append({"model": model, **met, "paramsJson": json.dumps(params, sort_keys=True, separators=(",", ":"))})
    selected_confirm = next(x for x in confirm_all if x["model"] == selected)
    poisson_confirm = next(x for x in confirm_all if x["model"] == "POISSON")

    # Production-research parameters can use all pre-2025 rows after architecture
    # has already been selected.  2026 remains the prospective validation regime.
    production_params = dist.fit_params(all_pre2025, selected)
    calibration_2024 = dist.threshold_calibration(exact_2024, selected, confirm_params)

    by_role = []
    for tier in dist.ROLE_TIERS:
        rr = [r for r in exact_2024 if r["role_tier"] == tier]
        if rr:
            m = dist.evaluate_rows(rr, selected, confirm_params)
            by_role.append({"roleTier": tier, **m})
    by_position = []
    positions = sorted({str(r.get("position_group") or "UNK") for r in exact_2024})
    for pg in positions:
        rr = [r for r in exact_2024 if str(r.get("position_group") or "UNK") == pg]
        if rr:
            m = dist.evaluate_rows(rr, selected, confirm_params)
            by_position.append({"positionGroup": pg, **m})

    # Confirmation is descriptive only.  The selected architecture is never
    # changed here.  This output remains RESEARCH_ONLY until 2026 prospective.
    nll_delta = float(poisson_confirm["countNLL"]) - float(selected_confirm["countNLL"])
    brier_delta = float(poisson_confirm["thresholdBrier"]) - float(selected_confirm["thresholdBrier"])
    confirmation_label = (
        "CONFIRMATION_BOTH_IMPROVE" if nll_delta > 0 and brier_delta > 0
        else "CONFIRMATION_MIXED_OR_WORSE"
    )

    outbase = root / "data/models/nfl/omega_tackle_015_distribution"
    out = outbase / sid
    if out.exists():
        spec = out / "OMEGA_0.15_DISTRIBUTION_SPEC.json"
        manifest = out / "OMEGA_OUTPUT_MANIFEST.json"
        if spec.exists() and manifest.exists():
            (root / "data/models/nfl/CURRENT_OMEGA_TACKLE_DISTRIBUTION").write_text(sid + "\n", encoding="utf-8")
            print(f"PASS existing immutable OMEGA 0.15 distribution output found: {out}")
            return 0
        raise SystemExit(f"FAIL corrupt/incomplete existing OMEGA 0.15 output: {out}")

    staging = outbase / ("." + sid + ".staging")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        write_csv(staging / "omega_0.15_chronological_selection.csv", fold_rows)
        write_csv(staging / "omega_0.15_selection_summary.csv", summary)
        write_csv(staging / "omega_2024_distribution_confirmation.csv", confirm_all)
        write_csv(staging / "omega_2024_threshold_calibration.csv", calibration_2024)
        write_csv(staging / "omega_2024_distribution_by_role.csv", by_role)
        write_csv(staging / "omega_2024_distribution_by_position.csv", by_position)

        spec_obj = {
            "schemaVersion": "OMEGA_TACKLE_DISTRIBUTION_SPEC_0.15",
            "createdAt": now(),
            "sourceSnapshotId": sid,
            "status": "RESEARCH_ONLY_PROSPECTIVE_2026_VALIDATION_REQUIRED",
            "independentMeanLineage": frozen_spec.get("lineage"),
            "frozenMeanSpecSha256": FROZEN_SPEC_SHA,
            "target": "combined_standard_def_scrimmage_integer_TA",
            "selectedArchitecture": selected,
            "candidateArchitectures": list(CANDIDATES),
            "selectionProtocol": {
                "chronologicalFolds": list(SELECTION_YEARS),
                "primaryMetric": "count negative log likelihood",
                "secondaryMetric": "mean Brier across integer thresholds 0.5..14.5",
                "nllTieTolerance": NLL_TIE_TOL,
                "tieBreak": "lower threshold Brier, then lower complexity",
                "confirmationSeason": 2024,
                "confirmationIsPristineHoldout": False,
                "holdout2025Used": False,
                "prospectiveValidationRequired": 2026,
            },
            "distribution": {
                "family": selected,
                "parameterization": "NB2 variance=mean+mean^2/size" if selected.startswith("NB") else "Poisson variance=mean",
                "productionResearchParamsFitThrough2024": production_params,
                "roleTierDefinition": {"LOW": "<0.35", "ROTATIONAL": "0.35-<0.65", "STARTER": "0.65-<0.85", "EVERY_DOWN": ">=0.85"},
                "roleTierInput": "H012 predicted snap share only; never target-game realized snaps",
            },
            "marketBoundary": {
                "marketFieldsReadDuringFit": 0,
                "oddsPapiRequests": 0,
                "networkRequests": 0,
                "sportsbookPricesEnterPredictionPath": False,
                "fairLinePricingAllowed": "research-only mechanical conversion after independent distribution",
                "postedPriceEVAllowed": "downstream only; does not alter OMEGA-I distribution",
                "deviggedMarketProbabilityUse": "sanity-check/comparison only",
            },
            "permanentRules": [
                "OMEGA 2025 remains consumed forever and may not tune this distribution.",
                "A mean xTC is not itself a bet; wagers require line-specific probabilities.",
                "T+A is an integer count and is priced with a discrete count distribution, not Normal/lognormal yardage assumptions.",
                "Alternative lines are priced from one coherent PMF, not separate ad-hoc projections.",
                "Sportsbook prices remain downstream of the independent OMEGA-I model.",
                "2026 prospective calibration/CLV is required before VERIFIED prop Trust.",
            ],
        }
        audit = {
            "schemaVersion": SCHEMA,
            "generatedAt": now(),
            "sourceSnapshotId": sid,
            "integrity": {
                "omega2025OutcomeRowsRead": 0,
                "marketFieldsRead": 0,
                "oddsPapiRequests": 0,
                "networkRequests": 0,
                "frozenMeanModelChanged": False,
                "h008Frozen": True,
                "h012Frozen": True,
                "targetSnapMagnitudeUsed": False,
            },
            "historicalRows": {"reconstructed2018to2023": len(hist), "exact2024Confirmation": len(exact_2024)},
            "candidateArchitectures": list(CANDIDATES),
            "chronologicalSelectionSummary": summary,
            "selectedArchitecture": selected,
            "confirmation2024": {
                "allCandidates": confirm_all,
                "selectedVsPoissonCountNLLImprovement": nll_delta,
                "selectedVsPoissonThresholdBrierImprovement": brier_delta,
                "label": confirmation_label,
                "thresholdCalibration": calibration_2024,
                "byRole": by_role,
                "byPosition": by_position,
            },
            "productionResearchParamsFitThrough2024": production_params,
            "verdict": "DISTRIBUTION_RESEARCH_CANDIDATE_ONLY_2026_PROSPECTIVE_REQUIRED",
        }
        (staging / "OMEGA_0.15_DISTRIBUTION_SPEC.json").write_text(json.dumps(spec_obj, indent=2) + "\n", encoding="utf-8")
        (staging / "OMEGA_0.15_DISTRIBUTION_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        md = f"""# OMEGA Tackle Model 0.15 — Distribution & Pricing Foundation Audit

Generated: {audit['generatedAt']}

**RESEARCH-ONLY DISTRIBUTION LAYER. FROZEN H008+H012 MEAN UNCHANGED. 2025 OUTCOMES NOT USED. NO MARKET DATA.**

## Why this exists

A mean projection is not a wager probability. OMEGA 0.15 converts the validated independent xTC mean into a discrete integer-count distribution so one coherent model can price every half-point tackle line.

## Hard integrity boundaries

- Frozen mean spec SHA256: `{FROZEN_SPEC_SHA}`
- Source snapshot: `{sid}`
- 2025 outcome rows used for distribution fitting: **0**
- Market fields read: **0**
- OddsPapi requests: **0**
- Network requests: **0**
- H008 / H012 changed: **NO**
- Target-game realized snap magnitude used: **NO**

## Predeclared candidates

1. `POISSON` — variance forced equal to mean.
2. `NB_GLOBAL` — one NB2 overdispersion size for all players.
3. `NB_ROLE` — NB2 size conditioned only on H012 **predicted** exposure role tier, with global fallback for sparse tiers.

This is intentionally narrow. No feature dump and no market-guided distribution choice.

## Selection protocol

- 2018-2020: initial strictly-lagged history.
- 2021, 2022, 2023: chronological validation folds.
- Primary score: count negative log likelihood.
- Secondary score: average Brier score across half-point thresholds 0.5 through 14.5.
- NLL tie tolerance: {NLL_TIE_TOL} per row; ties prefer lower threshold Brier, then simpler architecture.
- 2024: confirmation only; it cannot switch the selected architecture.
- 2025: **CONSUMED / FORBIDDEN FOR TUNING**.
- 2026: prospective probability calibration and market validation required.

## Selection

Selected architecture: **{selected}**

"""
        for x in summary:
            md += f"- {x['model']}: mean fold NLL **{x['meanCountNLL']:.6f}** · threshold Brier **{x['meanThresholdBrier']:.6f}**\n"
        md += f"""

## 2024 confirmation

- Selected NLL: **{float(selected_confirm['countNLL']):.6f}**
- Poisson NLL: **{float(poisson_confirm['countNLL']):.6f}**
- Selected improvement vs Poisson: **{nll_delta:+.6f}**
- Selected threshold Brier: **{float(selected_confirm['thresholdBrier']):.6f}**
- Poisson threshold Brier: **{float(poisson_confirm['thresholdBrier']):.6f}**
- Selected improvement vs Poisson: **{brier_delta:+.6f}**
- Confirmation label: **{confirmation_label}**

## Interpretation

This release does **not** claim a sportsbook edge. It establishes the probability layer needed to ask the correct question: `P(T+A > line)` rather than comparing xTC directly with a sportsbook line. The resulting PMF can price a full alternate-line ladder coherently.

Posted sportsbook break-even and EV calculations are downstream arithmetic only. De-vigged two-sided market probability is a sanity check against the independent distribution, never an input into OMEGA-I.

## Status

**DISTRIBUTION_RESEARCH_CANDIDATE_ONLY_2026_PROSPECTIVE_REQUIRED**
"""
        (staging / "OMEGA_0.15_DISTRIBUTION_AUDIT.md").write_text(md, encoding="utf-8")

        files = []
        for p in sorted(staging.iterdir()):
            if p.is_file():
                files.append({"filename": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size})
        (staging / "OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion": SCHEMA, "sourceSnapshotId": sid, "createdAt": now(), "files": files}, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, out)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    (root / "data/models/nfl/CURRENT_OMEGA_TACKLE_DISTRIBUTION").write_text(sid + "\n", encoding="utf-8")
    print("OMEGA 0.15 — DISTRIBUTION & PRICING FOUNDATION")
    print(f"PASS reconstructed H008 means: {len(hist)} pre-2024 rows + {len(exact_2024)} exact 2024 rows")
    for x in summary:
        print(f"  {x['model']}: CV NLL {x['meanCountNLL']:.6f} · threshold Brier {x['meanThresholdBrier']:.6f}")
    print(f"SELECTED: {selected}")
    print(f"2024 selected-vs-Poisson NLL improvement: {nll_delta:+.6f}")
    print(f"2024 selected-vs-Poisson threshold-Brier improvement: {brier_delta:+.6f}")
    print(f"CONFIRMATION: {confirmation_label}")
    print("PASS 2025 outcome rows 0 · market fields 0 · OddsPapi 0 · network 0")
    print("STATUS: RESEARCH_ONLY — 2026 prospective validation required")
    print(f"REPORT: {out/'OMEGA_0.15_DISTRIBUTION_AUDIT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

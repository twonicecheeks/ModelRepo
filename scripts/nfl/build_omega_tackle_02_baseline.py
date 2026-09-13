#!/usr/bin/env python3
"""Build OMEGA 0.2 xTO/xTC transparent research baseline.

Integrity:
* Uses OMEGA 0.1/0.1.1 only.
* 2016 is history seed; 2017-2023 are fit targets.
* 2024 is chronological validation only.
* 2025 OMEGA tackle holdout remains unopened.
* No market files and no OddsPapi calls.
* No over/under probabilities or betting recommendations are emitted.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse, csv, hashlib, json, os, shutil, sys
from statistics import fmean
from typing import Any

SCHEMA = "OMEGA_TACKLE_XTO_XTC_BASELINE_0.2"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
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


def pct_improve(base: float, model: float) -> float | None:
    return None if base == 0 else 100.0 * (base - model) / base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "packages/models/nfl/omega"))
    import xto_xtc_baseline as xb

    fptr = root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION"
    eptr = root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE"
    if not fptr.exists() or not eptr.exists():
        raise SystemExit("FAIL OMEGA 0.1/0.1.1 pointer missing")
    fsid = fptr.read_text(encoding="utf-8").strip()
    esid = eptr.read_text(encoding="utf-8").strip()
    if fsid != esid:
        raise SystemExit(f"FAIL OMEGA source snapshot mismatch foundation={fsid} exposure={esid}")
    sid = fsid
    foundation = root / "data/normalized/nfl/omega_tackle" / sid
    exposure = root / "data/normalized/nfl/omega_tackle_exposure" / sid
    fa = json.loads((foundation / "OMEGA_TACKLE_FOUNDATION_AUDIT.json").read_text(encoding="utf-8"))
    ea = json.loads((exposure / "OMEGA_TACKLE_EXPOSURE_AUDIT.json").read_text(encoding="utf-8"))
    if fa.get("omegaHoldoutPbpRowsRead") != 0 or fa.get("omegaHoldoutTackleOutcomesRead") != 0:
        raise SystemExit("FAIL OMEGA 0.1 holdout integrity")
    if ea.get("omegaHoldoutRowsRead") != 0:
        raise SystemExit("FAIL OMEGA 0.1.1 holdout integrity")
    if not ea.get("standardCreditReconciliation", {}).get("pass"):
        raise SystemExit("FAIL OMEGA 0.1.1 credit reconciliation")
    if not ea.get("integrity", {}).get("zeroOutcomeRowsIncluded"):
        raise SystemExit("FAIL exposure universe does not include explicit zero outcomes")
    if fa.get("marketFieldsRead") != 0 or ea.get("marketFieldsRead") != 0:
        raise SystemExit("FAIL market contamination")

    plays = read_csv(foundation / "omega_tackle_play_opportunities.csv")
    exposure_rows = read_csv(exposure / "omega_tackle_exposure_player_games.csv")
    if any(int(float(r.get("season") or 0)) == xb.HOLDOUT_SEASON for r in exposure_rows):
        raise SystemExit("FAIL 2025 exposure row unexpectedly present")
    if any(int(float(r.get("season") or 0)) == xb.HOLDOUT_SEASON for r in plays):
        raise SystemExit("FAIL 2025 play row unexpectedly present")

    outcomes = xb.aggregate_team_game_outcomes(plays, exposure_rows)
    team_rows = xb.build_team_pregame_rows(outcomes)
    player_rows = xb.build_player_pregame_rows(exposure_rows, team_rows)
    train_team = [r for r in team_rows if 2017 <= int(r["season"]) <= 2023]
    val_team = [r for r in team_rows if int(r["season"]) == 2024]
    if not train_team or not val_team:
        raise SystemExit("FAIL insufficient team train/validation rows")

    snap_l2, snap_search = xb.choose_ridge_lambda(team_rows, target_key="actual_defensive_snaps", pred_key="predicted_defensive_snaps")
    xto_l2, xto_search = xb.choose_ridge_lambda(team_rows, target_key="actual_opportunity_plays", pred_key="predicted_xto")
    snap_model = xb.fit_ridge(train_team, target_key="actual_defensive_snaps", l2=snap_l2)
    xto_model = xb.fit_ridge(train_team, target_key="actual_opportunity_plays", l2=xto_l2)

    team_val = []
    for r in val_team:
        z = dict(r)
        vec = [float(r[n]) for n in xb.TEAM_FEATURE_NAMES]
        z["predicted_defensive_snaps"] = snap_model.predict(vec)
        z["predicted_xto"] = xto_model.predict(vec)
        team_val.append(z)

    alpha, alpha_search = xb.choose_player_alpha(player_rows, team_rows, snap_l2=snap_l2)
    snap_predictions_2024 = {(r["game_id"], r["defense_team"]): float(r["predicted_defensive_snaps"]) for r in team_val}
    pval = [r for r in player_rows if int(r["season"]) == 2024]
    player_val = xb.score_player_rows(pval, alpha=alpha, snap_predictions=snap_predictions_2024)
    if not player_val:
        raise SystemExit("FAIL no 2024 player validation rows")

    team_snap_metrics = xb.count_metrics(team_val, actual_key="actual_defensive_snaps", pred_key="predicted_defensive_snaps")
    team_snap_bench = xb.count_metrics(team_val, actual_key="actual_defensive_snaps", pred_key="benchmark_defensive_snaps")
    team_xto_metrics = xb.count_metrics(team_val, actual_key="actual_opportunity_plays", pred_key="predicted_xto")
    team_xto_bench = xb.count_metrics(team_val, actual_key="actual_opportunity_plays", pred_key="benchmark_opportunity_plays")
    player_xtc_metrics = xb.count_metrics(player_val, actual_key="actual_xtc", pred_key="predicted_xtc")
    player_xtc_bench = xb.count_metrics(player_val, actual_key="actual_xtc", pred_key="benchmark_last4_xtc")

    by_pos = {}
    for pg in sorted({r["position_group"] for r in player_val}):
        rows = [r for r in player_val if r["position_group"] == pg]
        if rows:
            by_pos[pg] = {
                "model": xb.count_metrics(rows, actual_key="actual_xtc", pred_key="predicted_xtc"),
                "last4Benchmark": xb.count_metrics(rows, actual_key="actual_xtc", pred_key="benchmark_last4_xtc"),
            }
    established = [r for r in player_val if int(r["prior_games"]) >= 2]
    cold = [r for r in player_val if int(r["prior_games"]) == 0]
    role_bands = {}
    for name, lo, hi in (("LOW",0,.35),("MID",.35,.65),("CORE",.65,1.01)):
        rr = [r for r in player_val if lo <= float(r["prior_last4_snap_share"]) < hi]
        if rr:
            role_bands[name] = {
                "n": len(rr),
                "model": xb.count_metrics(rr, actual_key="actual_xtc", pred_key="predicted_xtc"),
                "last4Benchmark": xb.count_metrics(rr, actual_key="actual_xtc", pred_key="benchmark_last4_xtc"),
            }

    verdict = "MIXED_BASELINE"
    if team_xto_metrics["mae"] < team_xto_bench["mae"] and player_xtc_metrics["mae"] < player_xtc_bench["mae"]:
        verdict = "DIRECTIONALLY_PROMISING_BASELINE"
    elif team_xto_metrics["mae"] >= team_xto_bench["mae"] and player_xtc_metrics["mae"] >= player_xtc_bench["mae"]:
        verdict = "BASELINE_NOT_YET_USEFUL"

    outbase = root / "data/models/nfl/omega_tackle_02"
    out = outbase / sid
    if out.exists():
        raise SystemExit(f"Refusing overwrite immutable OMEGA 0.2 output: {out}")
    staging = outbase / ("." + sid + ".staging")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        write_csv(staging / "omega_2024_team_validation.csv", team_val)
        write_csv(staging / "omega_2024_player_validation.csv", player_val)
        (staging / "omega_xsnap_model.json").write_text(json.dumps(snap_model.to_dict(), indent=2) + "\n", encoding="utf-8")
        (staging / "omega_xto_model.json").write_text(json.dumps(xto_model.to_dict(), indent=2) + "\n", encoding="utf-8")
        spec = {
            "schemaVersion": SCHEMA,
            "version": xb.VERSION,
            "lineage": xb.LINEAGE,
            "sourceSnapshotId": sid,
            "developmentHistorySeed": [2016],
            "fitTargetSeasons": list(xb.FIT_TARGET_SEASONS),
            "chronologicalValidationSeason": 2024,
            "sealedOmegaHoldoutSeason": 2025,
            "teamHistoryWindow": xb.TEAM_WINDOW,
            "playerSnapWindow": xb.SNAP_WINDOW,
            "playerRateWindow": xb.RATE_WINDOW,
            "ridgeGrid": list(xb.RIDGE_GRID),
            "shrinkageAlphaGrid": list(xb.SHRINKAGE_ALPHA_GRID),
            "teamFeatures": list(xb.TEAM_FEATURE_NAMES),
            "xTCFormula": "xTeamDefSnaps * laggedPlayerSnapShare * shrunkLaggedStandardCreditRatePerDefSnap",
            "xTODefinition": "expected standard defensive scrimmage plays with >=1 original-defense tackle credit",
            "marketsUsed": False,
            "oddsPapiRequests": 0,
            "sportsbookSettlementAssumed": False,
            "propProbabilityProduced": False,
        }
        (staging / "OMEGA_0.2_SPEC.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        audit = {
            "schemaVersion": SCHEMA,
            "generatedAt": now(),
            "sourceSnapshotId": sid,
            "integrity": {
                "foundationReconciliationPass": True,
                "explicitZeroOutcomesIncluded": True,
                "omega2025RowsRead": 0,
                "postseasonIncluded": False,
                "marketFieldsRead": 0,
                "oddsPapiRequests": 0,
                "sportsbookSettlementAssumed": False,
                "bettingProbabilitiesProduced": False,
            },
            "sample": {
                "teamPregameRows": len(team_rows),
                "teamFitRows2017To2023": len(train_team),
                "teamValidationRows2024": len(team_val),
                "playerPregameRows": len(player_rows),
                "playerValidationRows2024": len(player_val),
                "playerValidationColdStarts": len(cold),
                "playerValidationEstablished2Plus": len(established),
            },
            "selection": {
                "xSnapL2": snap_l2,
                "xTOL2": xto_l2,
                "xTCAlphaPseudoSnaps": alpha,
                "xSnapSearch": snap_search,
                "xTOSearch": xto_search,
                "xTCAlphaSearch": alpha_search,
            },
            "validation2024": {
                "xDefensiveSnaps": {
                    "model": team_snap_metrics,
                    "lagBlendBenchmark": team_snap_bench,
                    "maeImprovementPct": pct_improve(team_snap_bench["mae"], team_snap_metrics["mae"]),
                },
                "xTO": {
                    "model": team_xto_metrics,
                    "lagBlendBenchmark": team_xto_bench,
                    "maeImprovementPct": pct_improve(team_xto_bench["mae"], team_xto_metrics["mae"]),
                },
                "xTCPlayer": {
                    "model": player_xtc_metrics,
                    "last4GameAverageBenchmark": player_xtc_bench,
                    "maeImprovementPct": pct_improve(player_xtc_bench["mae"], player_xtc_metrics["mae"]),
                    "byPositionGroup": by_pos,
                    "byProjectedRoleBand": role_bands,
                    "established2Plus": xb.count_metrics(established, actual_key="actual_xtc", pred_key="predicted_xtc") if established else None,
                    "coldStart": xb.count_metrics(cold, actual_key="actual_xtc", pred_key="predicted_xtc") if cold else None,
                },
            },
            "verdict": verdict,
            "nextGate": "Inspect 2024 validation and failure slices before any OMEGA 2025 tackle outcome is opened. Do not produce betting probabilities yet.",
        }
        (staging / "OMEGA_0.2_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        md = [
            "# OMEGA Tackle Model 0.2 — xTO/xTC Baseline Audit", "",
            f"Generated: {audit['generatedAt']}", "",
            "**RESEARCH BASELINE ONLY. NO SPORTSBOOK PROP PROBABILITIES OR BET RECOMMENDATIONS.**", "",
            "## Integrity", "",
            f"- Source snapshot: `{sid}`",
            "- 2016: history seed only",
            "- 2017–2023: development / fit targets",
            "- 2024: chronological validation",
            "- OMEGA 2025 tackle holdout rows read: **0**",
            "- Postseason: **EXCLUDED**",
            "- Market fields read: **0**",
            "- OddsPapi requests: **0**",
            "- Sportsbook settlement convention assumed: **NO**", "",
            "## Transparent baseline definitions", "",
            "- **xTO**: expected standard defensive scrimmage plays producing at least one original-defense tackle credit.",
            "- **xTC**: expected player standard defensive tackle-credit units, using predicted team defensive snaps × lagged player snap share × a position-shrunk lagged tackle-credit rate per defensive snap.",
            f"- Player snap window: **last {xb.SNAP_WINDOW} games**.",
            f"- Player tackle-rate window: **last {xb.RATE_WINDOW} games**.", "",
            "## Chronological model selection", "",
            f"- xDefensiveSnaps ridge L2 selected: **{snap_l2}**",
            f"- xTO ridge L2 selected: **{xto_l2}**",
            f"- xTC shrinkage pseudo-snaps selected: **{alpha}**", "",
            "Selections were made only through 2021–2023 chronological folds. 2024 was not used to choose these values.", "",
            "## 2024 team validation", "",
            f"- xDefensiveSnaps model MAE: **{team_snap_metrics['mae']:.4f}** vs lag-blend **{team_snap_bench['mae']:.4f}** ({audit['validation2024']['xDefensiveSnaps']['maeImprovementPct']:+.2f}% improvement)",
            f"- xTO model MAE: **{team_xto_metrics['mae']:.4f}** vs lag-blend **{team_xto_bench['mae']:.4f}** ({audit['validation2024']['xTO']['maeImprovementPct']:+.2f}% improvement)", "",
            "## 2024 player xTC validation", "",
            f"- Validation player-games: **{len(player_val)}**",
            f"- xTC model MAE: **{player_xtc_metrics['mae']:.4f}** vs last-4 game average **{player_xtc_bench['mae']:.4f}** ({audit['validation2024']['xTCPlayer']['maeImprovementPct']:+.2f}% improvement)",
            f"- xTC model RMSE: **{player_xtc_metrics['rmse']:.4f}** vs last-4 **{player_xtc_bench['rmse']:.4f}**",
            f"- Cold-start player-games: **{len(cold)}**",
            f"- Established (2+ prior games): **{len(established)}**", "",
            "## Verdict", "",
            f"**{verdict}**", "",
            "This verdict concerns predictive research value only. It is not evidence of sportsbook edge.", "",
            "## Next gate", "",
            "Inspect the 2024 validation CSVs and the position/role/cold-start failure slices. If the causal baseline is directionally useful, the next phase should add topology-conditioned xTO and allocation components one pre-registered hypothesis at a time. OMEGA 2025 remains sealed until a tackle specification is explicitly frozen.", "",
        ]
        (staging / "OMEGA_0.2_AUDIT.md").write_text("\n".join(md), encoding="utf-8")
        files = []
        for p in sorted(staging.iterdir()):
            if p.is_file():
                files.append({"filename": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size})
        (staging / "OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion": SCHEMA, "sourceSnapshotId": sid, "createdAt": now(), "files": files}, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, out)
        (root / "data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE").write_text(sid + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print("OMEGA TACKLE MODEL 0.2 — xTO/xTC BASELINE")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS 2024 xTO MAE: {team_xto_metrics['mae']:.4f} vs benchmark {team_xto_bench['mae']:.4f}")
    print(f"PASS 2024 xTC MAE: {player_xtc_metrics['mae']:.4f} vs last4 {player_xtc_bench['mae']:.4f}")
    print(f"VERDICT: {verdict}")
    print("PASS OMEGA 2025 holdout untouched · market fields 0 · OddsPapi 0")
    print(f"REPORT: {out/'OMEGA_0.2_AUDIT.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

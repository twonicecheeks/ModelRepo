#!/usr/bin/env python3
"""Freeze the OMEGA H008+H012 specification before opening 2025.

This command must not read 2025 tackle rows, market data, or OddsPapi.  It only
verifies the completed pre-holdout research chain and writes an immutable spec.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_nested(d: dict[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def require_float_alias(d: dict[str, Any], keys: tuple[str, ...], label: str) -> float:
    """Read a required numeric audit field with explicit schema aliases.

    Historical OMEGA artifacts are immutable.  If an older artifact used a
    different field name, the freeze gate must adapt to that schema rather
    than silently rewriting the historical audit.
    """
    for key in keys:
        if key not in d or d[key] is None:
            continue
        try:
            return float(d[key])
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                f"FAIL invalid {label}: key {key!r} has non-numeric value {d[key]!r}"
            ) from exc
    available = ", ".join(sorted(map(str, d.keys()))) or "<none>"
    expected = ", ".join(keys)
    raise SystemExit(
        f"FAIL missing {label}; expected one of [{expected}]; available selection keys: [{available}]"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    sys.path.insert(0, str(root / "packages/models/nfl/omega"))
    import frozen_spec as fs
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf

    pointers = {
        "foundation": root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION",
        "exposure": root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE",
        "baseline": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE",
        "diagnostics": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_DIAGNOSTICS",
        "h012": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER",
        "h011": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_OPPORTUNITY_CHALLENGER",
        "h008": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_FOOTPRINT_CHALLENGER",
        "h002": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_FUNNEL_CHALLENGER",
        "h003": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_ROLE_CONVEXITY_CHALLENGER",
        "h004": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_ASSIST_DECOMP_CHALLENGER",
        "h005": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_VENUE_ENVIRONMENT_CHALLENGER",
        "h007": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_RESIDUAL_PERSISTENCE_CHALLENGER",
        "h009": root / "data/models/nfl/CURRENT_OMEGA_TACKLE_GAME_SCRIPT_CHALLENGER",
    }
    for name, p in pointers.items():
        if not p.exists():
            raise SystemExit(f"FAIL prerequisite pointer missing: {name} {p}")
    sid = pointers["foundation"].read_text(encoding="utf-8").strip()
    for name, p in pointers.items():
        if p.read_text(encoding="utf-8").strip() != sid:
            raise SystemExit(f"FAIL OMEGA pointer mismatch: {name}")

    paths = {
        "foundation": root / "data/normalized/nfl/omega_tackle" / sid / "OMEGA_TACKLE_FOUNDATION_AUDIT.json",
        "exposure": root / "data/normalized/nfl/omega_tackle_exposure" / sid / "OMEGA_TACKLE_EXPOSURE_AUDIT.json",
        "baseline": root / "data/models/nfl/omega_tackle_02" / sid / "OMEGA_0.2_AUDIT.json",
        "diagnostics": root / "data/models/nfl/omega_tackle_021_diagnostics" / sid / "OMEGA_0.2.1_DIAGNOSTICS.json",
        "h012": root / "data/models/nfl/omega_tackle_022_exposure" / sid / "OMEGA_0.2.2_AUDIT.json",
        "h011": root / "data/models/nfl/omega_tackle_03_opportunity" / sid / "OMEGA_0.3_AUDIT.json",
        "h008": root / "data/models/nfl/omega_tackle_04_footprint" / sid / "OMEGA_0.4_AUDIT.json",
        "h002": root / "data/models/nfl/omega_tackle_05_funnel" / sid / "OMEGA_0.5_AUDIT.json",
        "h003": root / "data/models/nfl/omega_tackle_06_role_convexity" / sid / "OMEGA_0.6_AUDIT.json",
        "h004": root / "data/models/nfl/omega_tackle_07_assist_decomp" / sid / "OMEGA_0.7_AUDIT.json",
        "h005": root / "data/models/nfl/omega_tackle_08_venue_environment" / sid / "OMEGA_0.8_AUDIT.json",
        "h007": root / "data/models/nfl/omega_tackle_09_residual_persistence" / sid / "OMEGA_0.9_AUDIT.json",
        "h009": root / "data/models/nfl/omega_tackle_010_game_script" / sid / "OMEGA_0.10_AUDIT.json",
    }
    audits: dict[str, dict[str, Any]] = {}
    for name, p in paths.items():
        if not p.exists():
            raise SystemExit(f"FAIL prerequisite audit missing: {name} {p}")
        audits[name] = read_json(p)

    # Holdout/market integrity across every pre-holdout artifact.
    def holdout_count(name: str, a: dict[str, Any]) -> int:
        candidates = [
            a.get("omegaHoldoutPbpRowsRead"), a.get("omegaHoldoutTackleOutcomesRead"),
            a.get("omegaHoldoutRowsRead"), get_nested(a, "integrity", "omega2025RowsRead"),
        ]
        vals = [int(x) for x in candidates if x is not None]
        return max(vals) if vals else 0

    def market_count(a: dict[str, Any]) -> int:
        vals = [a.get("marketFieldsRead"), get_nested(a, "integrity", "marketFieldsRead")]
        vals = [int(x) for x in vals if x is not None]
        return max(vals) if vals else 0

    def odds_count(a: dict[str, Any]) -> int:
        vals = [a.get("oddsPapiRequests"), get_nested(a, "integrity", "oddsPapiRequests")]
        vals = [int(x) for x in vals if x is not None]
        return max(vals) if vals else 0

    for name, a in audits.items():
        if holdout_count(name, a) != 0:
            raise SystemExit(f"FAIL 2025 seal broken in {name}")
        if market_count(a) != 0:
            raise SystemExit(f"FAIL market contamination in {name}")
        if odds_count(a) != 0:
            raise SystemExit(f"FAIL OddsPapi usage in {name}")

    expected_verdicts = {
        "baseline": "DIRECTIONALLY_PROMISING_BASELINE",
        "h012": "H012_EXPOSURE_CHALLENGER_PASS",
        "h011": "H011_FAIL",
        "h008": "H008_TACKLE_OPPORTUNITY_FOOTPRINT_PASS",
        "h002": "H002_MIXED",
        "h003": "H003_FAIL",
        "h004": "H004_DIRECTIONAL_PASS",
        "h005": "H005_FAIL",
        "h007": "H007_FAIL_NULL_SELECTED",
        "h009": "H009_FAIL",
    }
    for name, expected in expected_verdicts.items():
        got = str(audits[name].get("verdict") or "")
        if got != expected:
            raise SystemExit(f"FAIL verdict drift {name}: expected {expected}, got {got}")

    # Exact parameter drift checks against both audits and installed model constants.
    # OMEGA 0.2's immutable JSON schema named the defensive-snap selection
    # `xSnapL2`; an early 0.11 freeze-gate implementation mistakenly looked
    # for `xDefensiveSnapsL2`, causing float(None).  Accept the historical key
    # explicitly (plus the descriptive alias for forward compatibility) and
    # fail with a schema-aware message if neither exists.
    bsel = audits["baseline"].get("selection", {})
    baseline_xsnap_l2 = require_float_alias(
        bsel, ("xSnapL2", "xDefensiveSnapsL2"), "baseline xDefensiveSnaps L2"
    )
    baseline_xto_l2 = require_float_alias(
        bsel, ("xTOL2", "xToL2"), "baseline xTO L2"
    )
    h012_l2 = require_float_alias(
        audits["h012"].get("selection", {}), ("selectedL2",), "H012 exposure L2"
    )
    h008_alpha = require_float_alias(
        audits["h008"].get("selection", {}),
        ("familyOpportunityShrinkageAlpha",),
        "H008 family alpha",
    )
    if abs(baseline_xsnap_l2 - fs.XDEFENSIVE_SNAPS_L2) > 1e-12:
        raise SystemExit("FAIL xDefensiveSnaps L2 drift")
    if abs(baseline_xto_l2 - fs.XTO_L2) > 1e-12:
        raise SystemExit("FAIL xTO L2 drift")
    if abs(h012_l2 - fs.EXPOSURE_L2) > 1e-12:
        raise SystemExit("FAIL H012 L2 drift")
    if abs(h008_alpha - fs.FAMILY_ALPHA) > 1e-12:
        raise SystemExit("FAIL H008 alpha drift")
    if tuple(tf.FAMILIES) != tuple(fs.FAMILIES):
        raise SystemExit(f"FAIL H008 family drift: {tf.FAMILIES}")
    if int(tf.RATE_WINDOW) != fs.PLAYER_FAMILY_RATE_WINDOW_GAMES or int(tf.TEAM_WINDOW) != fs.TEAM_WINDOW_GAMES:
        raise SystemExit("FAIL H008 window drift")
    if abs(fs.XTO_L2 - 0.3) > 1e-12 or abs(fs.EXPOSURE_L2 - 0.01) > 1e-12 or abs(fs.FAMILY_ALPHA - 50.0) > 1e-12:
        raise SystemExit("FAIL frozen constant self-check")

    out = root / "data/models/nfl/omega_tackle_frozen" / sid
    spec_path = out / "OMEGA_TACKLE_FROZEN_SPEC.json"
    sha_path = out / "OMEGA_TACKLE_FROZEN_SPEC.sha256"
    if out.exists():
        if not spec_path.exists() or not sha_path.exists():
            raise SystemExit("FAIL incomplete existing OMEGA freeze")
        if sha_path.read_text(encoding="utf-8").strip() != sha256_file(spec_path):
            raise SystemExit("FAIL existing OMEGA frozen spec hash mismatch")
        (root / "data/models/nfl/CURRENT_OMEGA_TACKLE_FROZEN").write_text(sid + "\n", encoding="utf-8")
        print(f"PASS existing immutable OMEGA freeze verified: {out}")
        return 0

    source_files = {
        "tackleEvents": root / "packages/models/nfl/omega/tackle_events.py",
        "exposureUniverse": root / "packages/models/nfl/omega/exposure_universe.py",
        "xtoXtcBaseline": root / "packages/models/nfl/omega/xto_xtc_baseline.py",
        "exposureRole": root / "packages/models/nfl/omega/exposure_role_challenger.py",
        "tackleOpportunityFootprint": root / "packages/models/nfl/omega/tackle_opportunity_footprint.py",
        "frozenSpecModule": root / "packages/models/nfl/omega/frozen_spec.py",
    }
    for name, p in source_files.items():
        if not p.exists():
            raise SystemExit(f"FAIL freeze source missing: {name} {p}")

    research = [
        ("0.2", "BASELINE", expected_verdicts["baseline"], False, "Transparent xTO/xTC baseline"),
        ("0.2.2", "H012", expected_verdicts["h012"], True, "Exposure/role ridge promoted"),
        ("0.3", "H011", expected_verdicts["h011"], False, "Scalar xTO coupling rejected"),
        ("0.4", "H008", expected_verdicts["h008"], True, "Opportunity-family topology promoted"),
        ("0.5", "H002", expected_verdicts["h002"], False, "Funnel rigidity not promoted"),
        ("0.6", "H003", expected_verdicts["h003"], False, "Replacement-role convexity rejected"),
        ("0.7", "H004", expected_verdicts["h004"], False, "Primary/assist decomposition retained for diagnostics only"),
        ("0.8", "H005", expected_verdicts["h005"], False, "Venue/year credit environment rejected"),
        ("0.9", "H007", expected_verdicts["h007"], False, "Residual persistence null selected"),
        ("0.10", "H009", expected_verdicts["h009"], False, "Game-script elasticity rejected"),
    ]

    h008_2024 = audits["h008"].get("validation2024", {})
    spec = {
        "schemaVersion": "OMEGA_TACKLE_FROZEN_SPEC_0.11",
        "frozenAt": now(),
        "sourceSnapshotId": sid,
        "lineage": fs.LINEAGE,
        "holdoutSeason": fs.HOLDOUT_SEASON,
        "gameType": fs.GAME_TYPE,
        "target": fs.TARGET,
        "targetDescription": fs.TARGET_DESCRIPTION,
        "champion": {
            "exposureComponent": "H012 / OMEGA 0.2.2",
            "topologyComponent": "H008 / OMEGA 0.4",
            "formula": "xTC = sum_family(predicted_xTO * predicted_family_share * H012_predicted_snap_share * shrunk_player_family_credit_rate)",
            "xDefensiveSnapsL2": fs.XDEFENSIVE_SNAPS_L2,
            "xTOL2": fs.XTO_L2,
            "exposureL2": fs.EXPOSURE_L2,
            "familyAlpha": fs.FAMILY_ALPHA,
            "teamWindowGames": fs.TEAM_WINDOW_GAMES,
            "playerFamilyRateWindowGames": fs.PLAYER_FAMILY_RATE_WINDOW_GAMES,
            "families": list(fs.FAMILIES),
        },
        "fitPolicy": {
            "historySeed": "2016 REG only",
            "globalCoefficientFit": "2017-2024 REG only after freeze; fixed hyperparameters; 2025 never enters global coefficient fitting",
            "holdoutWalkForward": "2025 predictions are emitted week-by-week. After an entire target week is predicted, that week's realized football/tackle history may update rolling histories for later 2025 weeks. No same-week or future-week outcome may enter a prediction.",
            "postseason": "EXCLUDED_SEPARATE_REGIME",
        },
        "benchmark": {
            "name": fs.BENCHMARK,
            "description": "Strictly-lagged last-4 player standard-defensive T+A count mean, using the frozen position-based cold-start fallback from OMEGA 0.2.",
        },
        "holdoutProtocol": {
            "freezeBeforeOpen": True,
            "blindPredictionLedgerBeforeScore": True,
            "scoreExactlyOnce": True,
            "bootstrapCluster": "game_id",
            "bootstrapReps": 10000,
            "primaryMetrics": ["MAE", "RMSE"],
            "diagnostics": ["bias", "calibration_intercept", "calibration_slope", "R2", "position_slices", "history_slices"],
            "verdictRules": fs.VERDICT_RULES,
            "marketFieldsForbidden": True,
            "oddsPapiRequests": 0,
            "sportsbookSettlementAssumed": False,
            "participantUniverseLimitation": "Historical count evaluation is conditional on player-games with resolved defensive snap exposure. This is not a pregame active/inactive availability model and cannot by itself create VERIFIED live prop Trust.",
            "postHoldoutRule": "OMEGA 2025 becomes consumed forever after one-shot scoring. It may not be reused to select features, hyperparameters, transformations, subgroups, market thresholds, or rescue rejected mechanisms.",
        },
        "researchClosure": {
            "promoted": ["H012", "H008"],
            "notPromoted": ["H011", "H002", "H003", "H004", "H005", "H007", "H009"],
            "deferredProspective": ["H006 early-week information asymmetry", "H010 information-source disagreement"],
            "rule": "No additional football-only historical mechanism search before the one-shot 2025 OMEGA holdout.",
        },
        "preHoldoutEvidence": {
            "h0082024MAE": get_nested(h008_2024, "overallVsH012", "challenger", "mae"),
            "h008VsH012MAEImprovement": get_nested(h008_2024, "overallVsH012", "maeImprovement"),
            "h008VsRawLast4MAE": get_nested(h008_2024, "vsRawLast4", "challenger", "mae"),
            "rawLast4MAE": get_nested(h008_2024, "vsRawLast4", "baseline", "mae"),
            "confirmationStatus": "DIAGNOSTIC_DIRECTED_NOT_PRISTINE_HOLDOUT",
        },
        "sourceHashes": {name: sha256_file(p) for name, p in source_files.items()},
        "auditHashes": {name: sha256_file(p) for name, p in paths.items()},
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.parent / ("." + sid + ".freeze.staging")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        data = canonical_bytes(spec)
        sp = staging / "OMEGA_TACKLE_FROZEN_SPEC.json"
        sp.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        (staging / "OMEGA_TACKLE_FROZEN_SPEC.sha256").write_text(digest + "\n", encoding="utf-8")

        with (staging / "OMEGA_RESEARCH_DECISION_LEDGER.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["phase", "hypothesis", "verdict", "promoted", "decision"])
            for row in research:
                w.writerow(row)

        md = f"""# OMEGA Tackle Model 0.11 — Explicit Frozen Specification

Frozen: {spec['frozenAt']}

**2025 OMEGA tackle outcomes remain sealed. This is the pre-holdout contract.**

## Frozen champion

- Source snapshot: `{sid}`
- Lineage: `{fs.LINEAGE}`
- Target: **standard defensive scrimmage combined tackle credits** only
- Exposure component: **H012 / OMEGA 0.2.2**
- Topology component: **H008 / OMEGA 0.4**
- xDefensiveSnaps ridge L2: **{fs.XDEFENSIVE_SNAPS_L2}**
- xTO ridge L2: **{fs.XTO_L2}**
- H012 exposure ridge L2: **{fs.EXPOSURE_L2}**
- H008 family shrinkage alpha: **{fs.FAMILY_ALPHA}**
- Team opportunity window: **{fs.TEAM_WINDOW_GAMES} games**
- Player family-rate window: **{fs.PLAYER_FAMILY_RATE_WINDOW_GAMES} games**
- Families: **{', '.join(fs.FAMILIES)}**

## Research closure

Promoted: **H012 exposure** and **H008 opportunity footprint**.

Not promoted: **H011 scalar opportunity coupling, H002 funnel rigidity, H003 replacement convexity, H004 primary/assist decomposition for T+A, H005 venue environment, H007 residual persistence, H009 game-script elasticity**.

H006 early-week information asymmetry and H010 source disagreement are deferred to prospective/diagnostic research. No additional football-only historical mechanism search is permitted before the OMEGA 2025 holdout.

## 2025 holdout contract

- 2016 is history seed.
- Global coefficients fit **2017-2024 REG only** using these frozen hyperparameters.
- 2025 is evaluated **walk-forward/as-of**: a week's realized history may update later weeks only after the entire week was predicted.
- Same-week/future-week 2025 outcomes are prohibited from prediction.
- Market fields and OddsPapi are prohibited.
- Postseason is excluded.
- Blind prediction ledger must be hashed before score attachment.
- One-shot score only; after scoring, **OMEGA 2025 is consumed forever**.

### Precommitted verdict

- **STRONG_PASS:** MAE and RMSE both improve vs the frozen strict-lag last-4 benchmark and both paired game-cluster bootstrap 95% CI lower bounds are > 0.
- **DIRECTIONAL_PASS:** MAE and RMSE both improve, without STRONG_PASS bootstrap support.
- **FAIL_BOTH:** both MAE and RMSE worsen.
- **MIXED:** anything else.

Regardless of verdict, this count holdout is **not evidence of sportsbook edge** and does not settle a sportsbook T+A formula.

Historical evaluation is conditional on player-games with resolved defensive exposure. A future live availability/active-roster layer is still required before VERIFIED prop Trust.

Frozen spec SHA256: `{digest}`
"""
        (staging / "OMEGA_TACKLE_FROZEN_SPEC.md").write_text(md, encoding="utf-8")
        os.replace(staging, out)
        (root / "data/models/nfl/CURRENT_OMEGA_TACKLE_FROZEN").write_text(sid + "\n", encoding="utf-8")
    except Exception:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print("OMEGA TACKLE MODEL 0.11 — EXPLICIT PRE-HOLDOUT FREEZE")
    print(f"PASS source snapshot: {sid}")
    print("PASS champion: H012 exposure + H008 topology")
    print("PASS rejected/mixed mechanisms remain unpromoted")
    print("PASS 2025 OMEGA rows read: 0 · market fields 0 · OddsPapi 0")
    print("PASS no further football-only historical mechanism search before holdout")
    print(f"FROZEN SPEC SHA256: {digest}")
    print(f"SPEC: {out/'OMEGA_TACKLE_FROZEN_SPEC.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""OMEGA 0.31.4 runner: frozen protocol + hardened 2025 ESPN depth adapter.

Preserves the prior 0.31 zero-depth-coverage result as an immutable audit artifact,
but refuses to treat it as a valid completed confirmatory test.  A result is eligible
for one-time rerun only when the prior report proves the challenger received zero
role input (depthCoverage == 0 and H012 == ROLE overall).  Any nonzero-coverage
existing result remains immutable and blocks a second score run.
"""
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import sys


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FAIL cannot load {path}")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def main() -> int:
    root = Path("/Users/abbeyfelix/Developer/MODEL").resolve()
    for i, arg in enumerate(sys.argv[:-1]):
        if arg == "--root":
            root = Path(sys.argv[i + 1]).expanduser().resolve()
            break

    shim = load_module("omega0311_feature_shim", root / "scripts/nfl/score_omega_2025_current_role_holdout_0311.py")
    shim.install_eval_only_feature_builder(root)

    scorer = load_module("omega031_frozen_protocol_scorer", root / "scripts/nfl/score_omega_2025_current_role_holdout_0310.py")
    adapter = load_module("omega0314_depth_adapter", root / "scripts/nfl/omega_2025_depth_espn_adapter_0314.py")

    # Empty diagnostic groups are n=0 and cannot satisfy a gate; avoid formatting crash.
    original_compare = scorer.compare
    def safe_compare(rows):
        if rows:
            return original_compare(rows)
        empty = {"n": 0, "actualMean": 0.0, "predictedMean": 0.0, "mae": 0.0, "rmse": 0.0, "biasPredMinusActual": 0.0}
        return {"n": 0, "h012": dict(empty), "role": dict(empty), "maeImprovement": 0.0, "rmseImprovement": 0.0, "biasChangeRoleMinusH012": 0.0}
    scorer.compare = safe_compare

    original_depth_map = scorer.depth_map_2025
    def adapted_depth_map(root2, depth25, depth25_sha):
        try:
            return adapter.build_depth_map(scorer, root2, depth25, depth25_sha)
        except RuntimeError as e:
            if str(e) == "LEGACY_SCHEMA_DELEGATE":
                return original_depth_map(root2, depth25, depth25_sha)
            raise
    scorer.depth_map_2025 = adapted_depth_map

    # Preserve immutable invalid run but do not let its CURRENT pointer suppress the
    # first scientifically valid score. Only zero-depth/no-op challenger runs qualify.
    original_existing = scorer.existing_result
    invalid_prior: Path | None = None
    def existing_result_with_invalid_plumbing_exception(root2):
        nonlocal invalid_prior
        p = original_existing(root2)
        if p is None:
            return None
        rp = p / "OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_REPORT.json"
        try:
            r = json.loads(rp.read_text(encoding="utf-8"))
            cov = float(r.get("coverage", {}).get("depthCoverage") or 0.0)
            o = r.get("overall", {})
            h = o.get("h012", {}); role = o.get("role", {})
            no_op = (
                cov == 0.0 and
                abs(float(h.get("mae") or 0.0) - float(role.get("mae") or 0.0)) < 1e-15 and
                abs(float(h.get("rmse") or 0.0) - float(role.get("rmse") or 0.0)) < 1e-15 and
                abs(float(o.get("maeImprovement") or 0.0)) < 1e-15 and
                abs(float(o.get("rmseImprovement") or 0.0)) < 1e-15
            )
            if no_op:
                invalid_prior = p
                print(f"OMEGA 0.31.4 — PRIOR RUN INVALIDATED FOR DECISION USE ONLY · immutable artifact preserved · zero depth coverage · {p}")
                return None
        except Exception:
            pass
        return p
    scorer.existing_result = existing_result_with_invalid_plumbing_exception

    rc = int(scorer.main())
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""OMEGA 0.31.3 runner: frozen protocol + 2025 ESPN depth schema adapter."""
from __future__ import annotations

from pathlib import Path
import importlib.util
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

    # Evaluation-only H012 chronology extension through 2025; no package write/refit.
    shim = load_module("omega0311_feature_shim", root / "scripts/nfl/score_omega_2025_current_role_holdout_0311.py")
    shim.install_eval_only_feature_builder(root)

    scorer = load_module("omega031_frozen_protocol_scorer", root / "scripts/nfl/score_omega_2025_current_role_holdout_0310.py")
    adapter = load_module("omega0313_depth_adapter", root / "scripts/nfl/omega_2025_depth_espn_adapter_0313.py")

    # Preserve 0.31.1 empty-diagnostic hardening.
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

    return int(scorer.main())


if __name__ == "__main__":
    raise SystemExit(main())

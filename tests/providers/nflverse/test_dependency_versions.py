#!/usr/bin/env python3
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[3]
CHECK = ROOT / "scripts/nfl/check_phase1b_dependencies.py"
spec = importlib.util.spec_from_file_location("nfl_phase1b_dependency_check", CHECK)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

assert mod.numeric_version("2026.07.22") == (2026, 7, 22)
assert mod.numeric_version("2026.7.22") == (2026, 7, 22)
assert mod.versions_equivalent("2026.07.22", "2026.7.22") is True
assert mod.versions_equivalent("25.0.1", "25.0.1") is True
assert mod.versions_equivalent("25.0.1", "25.0.2") is False

try:
    mod.numeric_version("2026.7rc1")
except ValueError:
    pass
else:
    raise AssertionError("nonnumeric version should fail closed")

print("PASS NFL dependency version normalization: zero-padded certifi runtime is equivalent to pinned calendar version")

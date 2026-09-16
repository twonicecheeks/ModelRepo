#!/usr/bin/env python3
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "packages/models/nfl/game/qb_starter_resolver_013.py"
spec = importlib.util.spec_from_file_location("m", P)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)

assert m.assert_development_only([2016, 2024]) == (2016, 2024)
try:
    m.assert_development_only([2024, 2025])
except ValueError:
    pass
else:
    raise AssertionError("2025 must remain sealed")

r = m.resolve_starter(prior_primary_qb="QB1", depth_qb1="QB1", active_qbs=["QB1", "QB2"])
assert r.qb_gsis_id == "QB1" and r.rule == "CONSENSUS_INCUMBENT_ACTIVE"
assert m.eligible_for_variant(r, "STRICT")

r = m.resolve_starter(prior_primary_qb="OLD", depth_qb1="NEW", active_qbs=["NEW", "BKP"])
assert r.qb_gsis_id == "NEW" and r.rule == "FORCED_CHANGE_DEPTH_ACTIVE"

r = m.resolve_starter(prior_primary_qb="OLD", depth_qb1="NEW", active_qbs=["OLD", "NEW"])
assert not r.resolved and r.rule == "ACTIVE_QB_CONFLICT"

r = m.resolve_starter(prior_primary_qb="OLD", depth_qb1="", active_qbs=["OLD", "BKP"])
assert r.resolved and r.rule == "INCUMBENT_ACTIVE_DEPTH_UNRESOLVED"
assert not m.eligible_for_variant(r, "STRICT")
assert m.eligible_for_variant(r, "EXTENDED")

r = m.resolve_starter(prior_primary_qb="", depth_qb1="QBX", active_qbs=["QBX", "QBY"])
assert r.resolved and r.rule == "DEPTH_ACTIVE_NO_PRIOR"
assert not m.eligible_for_variant(r, "STRICT")

assert m.gate(coverage_pct=80.0, first_qb_accuracy_pct=98.0) == "HISTORICAL_STARTER_RESOLVER_READY_FOR_QB_CHALLENGER"
assert m.gate(coverage_pct=65.0, first_qb_accuracy_pct=95.5) == "HISTORICAL_STARTER_RESOLVER_USABLE_WITH_QUARANTINE"
assert m.gate(coverage_pct=90.0, first_qb_accuracy_pct=94.0) == "HISTORICAL_STARTER_RESOLVER_NOT_READY"

print("PASS NFL QB State 0.1.3 starter resolver contracts · 2025 sealed")

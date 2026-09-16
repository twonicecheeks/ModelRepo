#!/usr/bin/env python3
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "packages/models/nfl/game/qb_state_data_audit_010.py"
spec = importlib.util.spec_from_file_location("m", P)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)

assert m.assert_development_only([2016, 2024]) == (2016, 2024)
try:
    m.assert_development_only([2024, 2025])
except ValueError as e:
    assert "sealed 2025" in str(e)
else:
    raise AssertionError("2025 must remain sealed")

schema = {
    "position", "depth_chart_position", "status", "starter",
    "depth_chart_order", "team", "week",
}
assert "depth_chart_position" in m.candidate_starter_fields(schema)
order = m.authoritative_order_candidates(schema)
assert "starter" in order
assert "depth_chart_order" in order
assert "depth_chart_position" not in order

assert m.coverage_status({f: True for f in m.QB_CORE_FIELDS}) == "CORE_QB_PBP_SCHEMA_AVAILABLE"
partial = {f: True for f in m.QB_CORE_FIELDS}
partial["yards_after_catch"] = False
assert m.coverage_status(partial) == "CORE_QB_PBP_SCHEMA_PARTIAL"

assert m.identity_status(
    unique_passers=100, resolved_passers=100,
    attributed_dropbacks=10000, resolved_dropbacks=9995,
) == "GSIS_IDENTITY_STRONG"
assert m.identity_status(
    unique_passers=100, resolved_passers=99,
    attributed_dropbacks=10000, resolved_dropbacks=9950,
) == "GSIS_IDENTITY_USABLE_WITH_QUARANTINE"

assert m.roster_starter_status([]) == "NO_AUTHORITATIVE_STARTER_ORDER_FIELD_OBSERVED"
assert m.depth_chart_source_status(asset_present=False, contract_status="DEFERRED_UNTIL_SCHEMA_ADAPTER") == "DECLARED_BUT_NOT_CAPTURED_DEFERRED_ADAPTER"

print("PASS NFL QB State 0.1.0 data/identity audit contracts · 2025 sealed")

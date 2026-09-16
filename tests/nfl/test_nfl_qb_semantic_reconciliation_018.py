#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
import qb_semantic_reconciliation_018 as q

assert q.assert_development_only([2016, 2024]) == (2016, 2024)
try:
    q.assert_development_only([2025])
except ValueError:
    pass
else:
    raise AssertionError("2025 must remain sealed")

row = {
    "passing_yards": 8,
    "receiving_yards": 8,
    "lateral_receiving_yards": 0,
    "lateral_reception": 0,
    "air_yards": 2,
    "yards_after_catch": 5,
}
r = q.official_receiving_reconciliation(row)
assert r["official_nonlateral_match"]
assert q.reconciliation_class(row) == "OFFICIAL_STAT_COHERENT_AIR_YAC_COMPONENT_MISMATCH"

bad = dict(row)
bad["receiving_yards"] = 7
assert q.reconciliation_class(bad) == "UNRESOLVED_OFFICIAL_STAT_MISMATCH"

lat = {
    "passing_yards": 10,
    "receiving_yards": 7,
    "lateral_receiving_yards": 3,
    "lateral_reception": 1,
}
assert q.reconciliation_class(lat) == "OFFICIAL_STAT_COHERENT_LATERAL_ACCOUNTING"
assert q.model_fit_authorized(prior_nonreview_conflicts=0, unresolved_rows=0, reconciled_rows=1)
assert not q.model_fit_authorized(prior_nonreview_conflicts=1, unresolved_rows=0, reconciled_rows=1)
assert not q.model_fit_authorized(prior_nonreview_conflicts=0, unresolved_rows=1, reconciled_rows=1)

print("PASS NFL QB State 0.1.8 semantic reconciliation contracts · 2025 sealed")

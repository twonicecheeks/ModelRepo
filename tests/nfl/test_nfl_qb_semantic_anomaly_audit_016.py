#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
import qb_semantic_anomaly_audit_016 as q

assert q.assert_development_only([2016, 2024]) == (2016, 2024)
try:
    q.assert_development_only([2025])
except ValueError:
    pass
else:
    raise AssertionError("2025 must remain sealed")

base = {"passing_yards":15,"air_yards":10,"yards_after_catch":5,"lateral_reception":0}
assert q.completion_residual(base) == 0
assert q.residual_class(base) == "EXACT"

lat = {"passing_yards":20,"air_yards":10,"yards_after_catch":5,"lateral_reception":1}
assert q.completion_residual(lat) == 5
assert q.residual_class(lat) == "LATERAL_RECEPTION"

other = {"passing_yards":20,"air_yards":10,"yards_after_catch":5,"lateral_reception":0}
assert q.residual_class(other) == "UNEXPLAINED_NONLATERAL"
assert q.residual_class({"passing_yards":None,"air_yards":1,"yards_after_catch":2}) == "MISSING_COMPONENT"
assert q.sack_scramble_conflict({"sack":1,"qb_scramble":1})
assert not q.sack_scramble_conflict({"sack":1,"qb_scramble":0})

print("PASS NFL QB State 0.1.6 semantic anomaly audit contracts · 2025 sealed")

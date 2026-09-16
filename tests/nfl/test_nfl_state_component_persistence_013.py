#!/usr/bin/env python3
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "packages/models/nfl/game/state_component_persistence_research.py"
spec = importlib.util.spec_from_file_location("m", P)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)

# Tercile assignment is deterministic and leaves no fabricated tier when there
# are fewer than three usable teams.
assert m._assign_terciles({"A": (0.1, 20), "B": (0.2, 20)}) == {}
tiers = m._assign_terciles({"A": (0.1, 20), "B": (0.2, 20), "C": (0.3, 20)})
assert tiers["A"]["tier"] == "LOW"
assert tiers["C"]["tier"] == "HIGH"

# Weighted summaries use underlying opportunity counts, not a mean of noisy
# per-game rates.
records = {
    "offense": [
        {"game_id":"g1","season":2024,"pregame_tier":"LOW",
         "target_third_downs":10,"target_exposed_third_downs":2,"target_dropbacks":8,
         "target_sacks":1,"target_conversions":4,"target_exposed_dropbacks":2,"target_exposed_sacks":0},
        {"game_id":"g2","season":2024,"pregame_tier":"HIGH",
         "target_third_downs":10,"target_exposed_third_downs":6,"target_dropbacks":9,
         "target_sacks":2,"target_conversions":3,"target_exposed_dropbacks":6,"target_exposed_sacks":1},
    ],
    "defense": [
        {"game_id":"g1","season":2024,"pregame_tier":"LOW",
         "target_third_downs":10,"target_exposed_third_downs":5,"target_dropbacks":8,
         "target_sacks":1,"target_conversions":4,"target_exposed_dropbacks":4,"target_exposed_sacks":0},
        {"game_id":"g2","season":2024,"pregame_tier":"HIGH",
         "target_third_downs":10,"target_exposed_third_downs":5,"target_dropbacks":8,
         "target_sacks":2,"target_conversions":3,"target_exposed_dropbacks":4,"target_exposed_sacks":1},
    ],
}
s = m.summarize_persistence(records)
assert abs(s["offense"]["groups"]["LOW"]["exposure_rate"] - 0.2) < 1e-12
assert abs(s["offense"]["groups"]["HIGH"]["exposure_rate"] - 0.6) < 1e-12
assert abs(s["offense"]["high_minus_low"] - 0.4) < 1e-12
assert abs(s["defense"]["groups"]["HIGH"]["exposed_sack_rate"] - 0.25) < 1e-12

try:
    m.assert_development_only([2024, 2025])
except ValueError as e:
    assert "sealed 2025" in str(e)
else:
    raise AssertionError("2025 must remain sealed")

assert m.assert_development_only([2016, 2024]) == (2016, 2024)
print("PASS NFL State Intelligence 0.1.3 component-persistence contracts · 2025 sealed")

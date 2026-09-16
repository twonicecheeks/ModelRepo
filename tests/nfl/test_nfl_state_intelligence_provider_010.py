#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import sys

root = Path(__file__).resolve().parents[2]
provider_dir = root / "packages/providers/nflverse/src"
sys.path.insert(0, str(provider_dir))

path = provider_dir / "state_intelligence_normalize.py"
spec = importlib.util.spec_from_file_location("state_intelligence_normalize_010", path)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)

names = set(m.REQUIRED_COLUMNS) | {"wp", "qb_scramble", "complete_pass"}
plan = m._schema_plan(names)
assert set(m.REQUIRED_COLUMNS).issubset(plan["columns"])
assert "wp" in plan["optionalAvailable"]
assert "air_yards" in plan["optionalMissing"]

try:
    m._schema_plan(names - {"ydstogo"})
except ValueError as exc:
    assert "ydstogo" in str(exc)
else:
    raise AssertionError("required schema drift must fail closed")

row = m._adapt_row({
    "posteam": "KC", "defteam": "DEN", "play_type": "qb_kneel",
    "punt_attempt": 0,
})
assert row["qb_kneel"] == 1
assert row["no_play"] == 0
assert row["punt"] == 0

print("PASS NFL State Intelligence 0.1.0 nflverse schema contracts")

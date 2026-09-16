#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "packages/models/nfl/game/state_mechanism_research.py"
spec = importlib.util.spec_from_file_location("m", P)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)


def row(play_id, down, ydstogo, *, success=0, first_down=0, intent="DESIGNED_RUN", pressure="BASE_STRUCTURAL_EXPOSURE", drive="1"):
    return {
        "game_id": "2024_01_A_B",
        "season": 2024,
        "posteam": "A",
        "drive": drive,
        "play_id": play_id,
        "down": down,
        "ydstogo": ydstogo,
        "success": success,
        "first_down": first_down,
        "state_intelligence": {
            "football_tendency_eligible": True,
            "competitive_state": "COMPETITIVE",
            "play_intent": intent,
            "down_distance_bucket": (
                f"D{down}_SHORT" if ydstogo <= 3 else
                f"D{down}_MEDIUM" if ydstogo <= 6 else
                f"D{down}_LONG" if ydstogo <= 10 else f"D{down}_VERY_LONG"
            ),
            "pressure_opportunity_bucket": pressure,
        },
    }

# Failed first down -> 2nd-and-long -> 3rd-and-long sack.
failed = [
    row(1, 1, 10, success=0, intent="DESIGNED_PASS"),
    row(2, 2, 10, success=0),
    row(3, 3, 9, success=0, intent="DROPBACK_SACK", pressure="HIGH_STRUCTURAL_EXPOSURE"),
    row(4, 4, 15, success=0),
]
# Successful first down -> manageable second down -> conversion.
success = [
    row(10, 1, 10, success=1, intent="DESIGNED_RUN", drive="2"),
    row(11, 2, 3, success=1, drive="2"),
    row(12, 3, 1, success=1, first_down=1, intent="DESIGNED_RUN", drive="2"),
]
records = m.build_series_records(failed + success)
assert len(records) == 2, records
f = next(r for r in records if r["first_down_success"] == 0)
s = next(r for r in records if r["first_down_success"] == 1)
assert f["second_long_plus"] == 1
assert f["reached_third"] == 1
assert f["third_high"] == 1
assert f["third_dropback"] == 1
assert f["third_sack"] == 1
assert f["series_first_down"] == 0
assert s["second_long_plus"] == 0
assert s["third_high"] == 0
assert s["third_conversion"] == 1
assert s["series_first_down"] == 1

summary = m.summarize_records(records)
assert summary["overall"]["failure"]["second_long_plus_rate"] == 1.0
assert summary["overall"]["success"]["second_long_plus_rate"] == 0.0
assert m.observed_differences(records)["second_long_plus_rate"] == 1.0

try:
    m.assert_development_only([2016, 2025])
except ValueError as exc:
    assert "sealed 2025" in str(exc)
else:
    raise AssertionError("2025 holdout must remain sealed")

assert m.assert_development_only([2016, 2024]) == (2016, 2024)
print("PASS NFL State Intelligence 0.1.1 early-down mechanism contracts · 2025 sealed")

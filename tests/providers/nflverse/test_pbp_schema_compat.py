#!/usr/bin/env python3
"""Regression: current nflverse PBP may omit standalone `no_play`.

The adapter must preserve nullified-play and QB-kneel exclusions via `play_type`,
and must fail closed if those semantics cannot be represented.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "packages/providers/nflverse/src"
sys.path.insert(0, str(SRC))
import normalize

base = set(normalize.PBP_REQUIRED_COLUMNS)

# Reproduce the live failure: standalone no_play absent, play_type present.
plan = normalize._pbp_schema_plan(base | {"play_type", "qb_kneel"})
assert plan["noPlaySource"] == "play_type", plan
assert plan["qbKneelSource"] == "qb_kneel", plan
r = normalize._adapt_pbp_semantics({"play_type": "no_play", "qb_kneel": 0}, plan)
assert r["no_play"] == 1 and r["qb_kneel"] == 0, r
r = normalize._adapt_pbp_semantics({"play_type": "pass", "qb_kneel": 0}, plan)
assert r["no_play"] == 0, r

# If both standalone semantic flags drift, play_type can safely represent both.
plan2 = normalize._pbp_schema_plan(base | {"play_type"})
r = normalize._adapt_pbp_semantics({"play_type": "qb_kneel"}, plan2)
assert r["no_play"] == 0 and r["qb_kneel"] == 1, r

# Native flags remain authoritative when they are present.
plan3 = normalize._pbp_schema_plan(base | {"no_play", "qb_kneel", "play_type"})
r = normalize._adapt_pbp_semantics({"no_play": 1, "qb_kneel": 0, "play_type": "pass"}, plan3)
assert r["no_play"] == 1 and r["qb_kneel"] == 0, r

# Fail closed: do not silently admit nullified plays if neither representation exists.
try:
    normalize._pbp_schema_plan(base | {"qb_kneel"})
except ValueError as exc:
    assert "no_play or play_type" in str(exc), exc
else:
    raise AssertionError("schema without no_play/play_type did not fail closed")

# Exercise the exact parquet adapter with a fake ParquetFile: no native no_play.
class FakeSchema:
    names = list(base | {"play_type", "qb_kneel"})
class FakeTable:
    def __init__(self, rows): self._rows = rows
    def to_pylist(self): return self._rows
class FakePF:
    schema_arrow = FakeSchema()
    def read(self, columns):
        assert "play_type" in columns
        assert "no_play" not in columns
        return FakeTable([{k: 0 for k in columns} | {
            "game_id": "2015_01_A_B", "season": 2015, "week": 1,
            "posteam": "A", "defteam": "B", "play_type": "no_play",
            "qb_kneel": 0,
        }])
class FakePQ:
    @staticmethod
    def ParquetFile(path): return FakePF()

old_pq = normalize.pq
try:
    normalize.pq = FakePQ()
    rows, p = normalize._pbp_parquet_rows(Path("fixture.parquet"))
finally:
    normalize.pq = old_pq
assert p["noPlaySource"] == "play_type"
assert rows[0]["no_play"] == 1

print("PASS NFL PBP schema compatibility: play_type fallback preserves no-play/kneel filtering and fails closed when semantics are unavailable")

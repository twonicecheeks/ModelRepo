#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root = Path(__file__).resolve().parents[2]


def load(name: str, rel: str):
    path = root / rel
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


m = load("state_intelligence", "packages/models/nfl/game/state_intelligence.py")
r = load("nuance_registry", "packages/models/nfl/game/nuance_registry.py")

# Registry integrity: preserve all 88 source items and source status counts.
assert len(r.NUANCE_REGISTRY) == 88
assert r.SOURCE_STATUS_COUNTS == {
    "BACKTEST": 15,
    "CORE": 70,
    "EXTERNAL DATA": 1,
    "IMPLEMENT": 1,
    "WATCH": 1,
}
assert r.FROZEN_OMEGA_MUTATION_ALLOWED is False
assert m.FROZEN_OMEGA_MUTATION_ALLOWED is False

# M01/M39: scramble remains dropback-origin, not a designed run.
scramble = {
    "game_id": "G1", "play_id": 10, "posteam": "KC",
    "qb_dropback": 1, "qb_scramble": 1, "rush": 1,
    "down": 3, "ydstogo": 8, "yardline_100": 55,
}
f = m.snap_state_features(scramble)
assert f["play_intent"] == "DROPBACK_SCRAMBLE"
assert f["dropback_origin"] is True
assert f["designed_run_origin"] is False
assert f["third_down_distance_bucket"] == "THIRD_LONG"
assert f["pressure_opportunity_bucket"] == "HIGH_STRUCTURAL_EXPOSURE"

# M86/M87: kneel isolated from football tendency but preserved for settlement.
kneel = {
    "game_id": "G1", "play_id": 20, "posteam": "KC",
    "qb_kneel": 1, "rush": 1, "play_type": "qb_kneel", "qtr": 4, "wp": .999,
}
f = m.snap_state_features(kneel)
assert f["play_intent"] == "VICTORY_FORMATION"
assert f["competitive_state"] == "VICTORY_FORMATION"
assert f["football_tendency_eligible"] is False
assert f["official_stat_qb_kneel"] is True

# M34: a completion short of the sticks is not a functional conversion.
short_completion = {
    "game_id": "G1", "play_id": 30, "posteam": "DEN",
    "qb_dropback": 1, "play_type": "pass", "complete_pass": 1,
    "down": 3, "ydstogo": 6, "yards_gained": 4,
}
assert m.snap_state_features(short_completion)["functional_completion"] == "SHORT_OF_STICKS"

# M27/M72/M73: strip-sack disruption is decomposed.
strip_sack = {
    "game_id": "G1", "play_id": 40, "posteam": "DEN",
    "qb_dropback": 1, "sack": 1, "fumble": 1, "fumble_lost": 1,
    "down": 2, "ydstogo": 9, "yardline_100": 42,
}
f = m.snap_state_features(strip_sack)
assert f["play_intent"] == "DROPBACK_SACK"
assert f["turnover_type"] == "FUMBLE_LOST"
assert {"SACK", "FUMBLE", "FUMBLE_LOST"}.issubset(set(f["disruption_types"]))

# M68: next possession after turnover is sudden-change offense.
rows = [
    {
        "game_id": "G2", "play_id": 1, "drive": 1, "posteam": "KC",
        "qb_dropback": 1, "interception": 1, "down": 1, "ydstogo": 10,
        "yardline_100": 95,
    },
    {
        "game_id": "G2", "play_id": 2, "drive": 2, "posteam": "DEN",
        "rush": 1, "down": 1, "ydstogo": 5, "yardline_100": 5,
    },
]
annotated = m.annotate_game_states(rows)
assert annotated[0]["state_intelligence"]["sudden_change_offense"] is False
assert annotated[1]["state_intelligence"]["sudden_change_offense"] is True
assert annotated[1]["state_intelligence"]["inherited_turnover_type"] == "INTERCEPTION"
assert annotated[1]["state_intelligence"]["field_position_bucket"] == "RED_ZONE"

# M77-M80: closeout is a research candidate only when supplied WP supports it.
closeout = {
    "game_id": "G3", "play_id": 1, "posteam": "KC",
    "rush": 1, "down": 1, "ydstogo": 10, "qtr": 4, "wp": .985,
}
assert m.snap_state_features(closeout)["competitive_state"] == "CLOSEOUT_CANDIDATE"

# Aggregate remains descriptive and coefficient-free.
profile = m.aggregate_state_profile([scramble, kneel, short_completion, strip_sack])
assert profile["total_snaps"] == 4
assert profile["football_tendency_eligible_snaps"] == 3
assert profile["turnovers"] == 1

print("PASS NFL State Intelligence 0.1.0 contracts · M01-M88 registry intact · frozen OMEGA untouched")

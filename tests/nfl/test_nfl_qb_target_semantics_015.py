#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
import qb_target_semantics_015 as q

assert q.assert_development_only([2016, 2024]) == (2016, 2024)
try:
    q.assert_development_only([2024, 2025])
except ValueError:
    pass
else:
    raise AssertionError("2025 must remain sealed")

rows = [
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":1,
        "qb_dropback":1,"pass_attempt":1,"complete_pass":1,"sack":0,"qb_scramble":0,
        "qb_spike":0,"qb_kneel":0,"two_point_attempt":0,"rush_attempt":0,
        "passer_player_id":"QB1","rusher_player_id":"","passing_yards":15,
        "rushing_yards":None,"air_yards":10,"yards_after_catch":5,"yards_gained":15,
        "play_type":"pass","no_play":0,"interception":0,"qb_epa":0.4,"cpoe":3.0,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":2,
        "qb_dropback":1,"pass_attempt":1,"complete_pass":0,"sack":1,"qb_scramble":0,
        "qb_spike":0,"qb_kneel":0,"two_point_attempt":0,"rush_attempt":0,
        "passer_player_id":"QB1","rusher_player_id":"","passing_yards":None,
        "rushing_yards":None,"air_yards":None,"yards_after_catch":None,"yards_gained":-7,
        "play_type":"pass","no_play":0,"interception":0,"qb_epa":-1.0,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":3,
        "qb_dropback":1,"pass_attempt":0,"complete_pass":0,"sack":0,"qb_scramble":1,
        "qb_spike":0,"qb_kneel":0,"two_point_attempt":0,"rush_attempt":1,
        "passer_player_id":"QB1","rusher_player_id":"QB1","passing_yards":None,
        "rushing_yards":8,"air_yards":None,"yards_after_catch":None,"yards_gained":8,
        "play_type":"run","no_play":0,"interception":0,"qb_epa":0.3,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":4,
        "qb_dropback":0,"pass_attempt":0,"complete_pass":0,"sack":0,"qb_scramble":0,
        "qb_spike":0,"qb_kneel":0,"two_point_attempt":0,"rush_attempt":1,
        "passer_player_id":"","rusher_player_id":"QB1","passing_yards":None,
        "rushing_yards":4,"air_yards":None,"yards_after_catch":None,"yards_gained":4,
        "play_type":"run","no_play":0,"interception":0,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":5,
        "qb_dropback":0,"pass_attempt":1,"complete_pass":0,"sack":0,"qb_scramble":0,
        "qb_spike":1,"qb_kneel":0,"two_point_attempt":0,"rush_attempt":0,
        "passer_player_id":"QB1","rusher_player_id":"","passing_yards":0,
        "rushing_yards":None,"air_yards":None,"yards_after_catch":None,"yards_gained":0,
        "play_type":"qb_spike","no_play":0,"interception":0,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":6,
        "qb_dropback":1,"pass_attempt":1,"complete_pass":1,"sack":0,"qb_scramble":0,
        "qb_spike":0,"qb_kneel":0,"two_point_attempt":1,"rush_attempt":0,
        "passer_player_id":"QB1","rusher_player_id":"","passing_yards":2,
        "rushing_yards":None,"air_yards":1,"yards_after_catch":1,"yards_gained":2,
        "play_type":"pass","no_play":0,"interception":0,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":7,
        "qb_dropback":0,"pass_attempt":0,"complete_pass":0,"sack":0,"qb_scramble":0,
        "qb_spike":0,"qb_kneel":1,"two_point_attempt":0,"rush_attempt":1,
        "passer_player_id":"","rusher_player_id":"QB1","passing_yards":None,
        "rushing_yards":-1,"air_yards":None,"yards_after_catch":None,"yards_gained":-1,
        "play_type":"qb_kneel","no_play":0,"interception":0,
    },
]

assert q.dropback_outcome(rows[0]) == "THROW"
assert q.dropback_outcome(rows[1]) == "SACK"
assert q.dropback_outcome(rows[2]) == "SCRAMBLE"
assert q.dropback_outcome(rows[5]) == "NOT_STRUCTURAL_DROPBACK"
assert q.settlement_pass_attempt(rows[0])
assert not q.settlement_pass_attempt(rows[1])
assert q.settlement_pass_attempt(rows[4])
assert not q.settlement_pass_attempt(rows[5])

first, primary, db = q.observed_qb_labels(rows)
assert (first, primary, db) == ("QB1", "QB1", 3)
a = q.aggregate_team_game(rows)
assert a is not None
assert a["starter_structural_dropbacks"] == 3
assert a["structural_throw_attempts"] == 1
assert a["structural_sacks"] == 1
assert a["structural_scrambles"] == 1
assert a["structural_dropback_residual"] == 0
assert a["raw_pass_attempt_indicator_on_structural_db"] == 2
assert a["raw_sacks_with_pass_attempt_indicator"] == 1
assert a["settlement_pass_attempts"] == 2
assert a["settlement_spike_attempts"] == 1
assert a["settlement_completions"] == 1
assert a["passing_yards"] == 15
assert a["two_point_pass_plays_excluded"] == 1
assert a["completed_air_yards"] == 10
assert a["completion_yac"] == 5
assert a["completion_yards_decomp_residual"] == 0
assert a["structural_qb_rush_attempts"] == 2
assert a["designed_qb_rush_attempts"] == 1
assert a["structural_qb_rush_yards"] == 12
assert a["settlement_qb_rush_attempts"] == 3
assert a["settlement_kneels"] == 1
assert a["settlement_qb_rush_yards"] == 11

print("PASS NFL QB State 0.1.5 target semantics contracts · 2025 sealed")

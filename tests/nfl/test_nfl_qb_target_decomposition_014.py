#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
import qb_target_decomposition_014 as q

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
        "rush_attempt":0,"passer_player_id":"QB1","rusher_player_id":"",
        "passing_yards":15,"air_yards":10,"yards_after_catch":5,"yards_gained":15,
        "play_type":"pass","no_play":0,"qb_kneel":0,"interception":0,"qb_epa":0.4,"cpoe":3.0,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":2,
        "qb_dropback":1,"pass_attempt":0,"complete_pass":0,"sack":1,"qb_scramble":0,
        "rush_attempt":0,"passer_player_id":"QB1","rusher_player_id":"",
        "passing_yards":None,"air_yards":None,"yards_after_catch":None,"yards_gained":-7,
        "play_type":"pass","no_play":0,"qb_kneel":0,"interception":0,"qb_epa":-1.0,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":3,
        "qb_dropback":1,"pass_attempt":0,"complete_pass":0,"sack":0,"qb_scramble":1,
        "rush_attempt":1,"passer_player_id":"QB1","rusher_player_id":"QB1",
        "passing_yards":None,"air_yards":None,"yards_after_catch":None,"yards_gained":8,
        "play_type":"run","no_play":0,"qb_kneel":0,"interception":0,"qb_epa":0.3,
    },
    {
        "game_id":"2019_01_A_B","season":2019,"week":1,"posteam":"A","play_id":4,
        "qb_dropback":0,"pass_attempt":0,"complete_pass":0,"sack":0,"qb_scramble":0,
        "rush_attempt":1,"passer_player_id":"","rusher_player_id":"QB1",
        "passing_yards":None,"air_yards":None,"yards_after_catch":None,"yards_gained":4,
        "play_type":"run","no_play":0,"qb_kneel":0,"interception":0,
    },
]

first, primary, db = q.observed_qb_labels(rows)
assert (first, primary, db) == ("QB1", "QB1", 3)
a = q.aggregate_observed_starter_team_game(rows)
assert a is not None
assert a["starter_dropbacks"] == 3
assert a["pass_attempts"] == 1
assert a["completions"] == 1
assert a["sacks"] == 1
assert a["scrambles"] == 1
assert a["dropback_component_residual"] == 0
assert a["passing_yards"] == 15
assert a["completed_air_yards"] == 10
assert a["completion_yac"] == 5
assert a["completion_yards_decomp_residual"] == 0
assert a["qb_rush_attempts"] == 2
assert a["designed_qb_rush_attempts"] == 1
assert a["qb_rush_yards"] == 12
assert a["team_offensive_plays"] == 4

print("PASS NFL QB State 0.1.4 target/decomposition contracts · 2025 sealed")

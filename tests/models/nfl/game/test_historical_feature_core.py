#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import copy

ROOT = Path(__file__).resolve().parents[4]
MOD = ROOT / "packages/models/nfl/game/historical_feature_core.py"
spec = importlib.util.spec_from_file_location("nfl_hist", MOD)
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

assert core.VERSION == "0.1.0"
assert core.CALIBRATION_STATUS == "UNFIT_RESEARCH_FOUNDATION"

def metric(game_id, season, week, team, val):
    return {
        "game_id": game_id, "season": season, "week": week, "team": team,
        "off_dropback_epa": val,
        "off_rush_epa": val / 2,
        "off_success_rate": .40 + val / 100,
        "off_cpoe": val * 2,
        "off_sack_rate": .07,
        "off_explosive_pass_rate": .10,
        "off_explosive_rush_rate": .08,
        "off_turnover_rate": .02,
        "def_dropback_epa_allowed": -val,
        "def_rush_epa_allowed": -val / 2,
        "def_success_rate_allowed": .40 - val / 100,
        "def_sack_rate_generated": .08,
        "def_explosive_pass_rate_allowed": .09,
        "def_explosive_rush_rate_allowed": .07,
        "def_takeaway_rate": .025,
    }

# 2024 prior-season rows plus 2025 Weeks 1-3. Week 2 features must only see Week 1.
metrics = [
    metric("2024_18_A_B", 2024, 18, "A", .10), metric("2024_18_A_B", 2024, 18, "B", -.10),
    metric("2025_01_A_B", 2025, 1, "A", .20), metric("2025_01_A_B", 2025, 1, "B", -.20),
    metric("2025_02_B_A", 2025, 2, "A", 9.99), metric("2025_02_B_A", 2025, 2, "B", -9.99),
    metric("2025_03_A_B", 2025, 3, "A", 88.0), metric("2025_03_A_B", 2025, 3, "B", -88.0),
]
games = [
    {"game_id":"2025_01_A_B","season":2025,"week":1,"game_type":"REG","away_team":"A","home_team":"B","away_score":17,"home_score":20,"home_rest":7,"away_rest":7,"spread_line":-3.0,"home_moneyline":-150},
    {"game_id":"2025_02_B_A","season":2025,"week":2,"game_type":"REG","away_team":"B","home_team":"A","away_score":10,"home_score":24,"home_rest":7,"away_rest":7,"spread_line":-7.0,"home_moneyline":-300},
    {"game_id":"2025_03_A_B","season":2025,"week":3,"game_type":"REG","away_team":"A","home_team":"B","away_score":31,"home_score":27,"home_rest":7,"away_rest":7},
]
rows = core.build_pregame_feature_rows(games, metrics, windows=(1,2))
assert len(rows) == 3
wk1, wk2, wk3 = rows
assert wk1["feature_state"] == "EARLY_SEASON_PRIOR_HEAVY"
assert wk1["split_state"] == "HOLDOUT_NEVER_FIT"
assert wk2["features"]["home_games_available"] == 1
assert abs(wk2["features"]["home_last1_off_dropback_epa"] - .20) < 1e-12
assert abs(wk2["features"]["home_prior_season_off_dropback_epa"] - .10) < 1e-12
assert wk2["target"] == {"home_win": 1, "home_margin": 14.0}
for forbidden in ("spread_line", "home_moneyline", "away_moneyline", "home_score", "away_score", "result"):
    assert forbidden not in wk2["features"]

# Current-game result mutation must never change the current game's pregame features.
games_mut = copy.deepcopy(games)
games_mut[1]["home_score"] = 0; games_mut[1]["away_score"] = 99; games_mut[1]["spread_line"] = 14.5
rows_mut = core.build_pregame_feature_rows(games_mut, metrics, windows=(1,2))
assert rows_mut[1]["features"] == wk2["features"]
assert rows_mut[1]["target"] != wk2["target"]

# Current/future team metric mutation must not leak into Week 2.
metrics_mut = copy.deepcopy(metrics)
for r in metrics_mut:
    if r["season"] == 2025 and r["week"] >= 2 and r["team"] == "A":
        r["off_dropback_epa"] = -999
rows_mut2 = core.build_pregame_feature_rows(games, metrics_mut, windows=(1,2))
assert rows_mut2[1]["features"] == wk2["features"]

# Week 3 now sees Weeks 1-2, proving lagged progression works.
assert wk3["features"]["away_games_available"] == 2
assert abs(wk3["features"]["away_last1_off_dropback_epa"] - 9.99) < 1e-12
assert abs(wk3["features"]["away_last2_off_dropback_epa"] - ((.20+9.99)/2)) < 1e-12

# Basic PBP aggregation smoke test, including sacks and opponent-derived defense metrics.
pbp = [
 {"game_id":"2024_01_A_B","season":2024,"week":1,"posteam":"A","defteam":"B","qb_dropback":1,"rush":0,"epa":.5,"success":1,"cpoe":4,"sack":0,"yards_gained":22,"interception":0,"fumble_lost":0},
 {"game_id":"2024_01_A_B","season":2024,"week":1,"posteam":"A","defteam":"B","qb_dropback":1,"rush":0,"epa":-1.0,"success":0,"cpoe":None,"sack":1,"yards_gained":-7,"interception":0,"fumble_lost":0},
 {"game_id":"2024_01_A_B","season":2024,"week":1,"posteam":"B","defteam":"A","qb_dropback":0,"rush":1,"epa":.2,"success":1,"yards_gained":12,"interception":0,"fumble_lost":0},
]
agg = core.aggregate_pbp_to_team_games(pbp)
a = next(r for r in agg if r["team"] == "A")
b = next(r for r in agg if r["team"] == "B")
assert abs(a["off_dropback_epa"] - (-.25)) < 1e-12
assert abs(a["off_sack_rate"] - .5) < 1e-12
assert abs(a["off_explosive_pass_rate"] - .5) < 1e-12
assert abs(a["def_rush_epa_allowed"] - b["off_rush_epa"]) < 1e-12
print("PASS NFL historical feature core: prior-only lagging, holdout state, market isolation, and PBP aggregation")

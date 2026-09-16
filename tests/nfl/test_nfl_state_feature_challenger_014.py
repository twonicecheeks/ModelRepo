#!/usr/bin/env python3
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "packages/models/nfl/game/state_feature_challenger_014.py"
spec = importlib.util.spec_from_file_location("m", P)
m = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)

records = {
    "offense": [
        {"game_id":"g1","team":"H","pregame_exposure_rate":0.60,"prior_third_downs":40},
        {"game_id":"g1","team":"A","pregame_exposure_rate":0.75,"prior_third_downs":45},
    ],
    "defense": [
        {"game_id":"g1","team":"H","pregame_exposed_sack_rate":0.12,"prior_exposed_dropbacks":30},
        {"game_id":"g1","team":"A","pregame_exposed_sack_rate":0.08,"prior_exposed_dropbacks":35},
    ],
}
features = m.build_game_state_features(records,[{"game_id":"g1","home_team":"H","away_team":"A"}])
g = features["g1"]
assert abs(g["state_offense_exposure_advantage"] - 0.15) < 1e-12
assert abs(g["state_defense_exposed_sack_advantage"] - 0.04) < 1e-12
assert g["combined_feature_available"] is True

v = m.vectorize_state_features(g,"COMBINED")
assert len(v) == 4
assert abs(v[0]-0.15) < 1e-12 and v[1] == 0.0
assert abs(v[2]-0.04) < 1e-12 and v[3] == 0.0

missing = m.vectorize_state_features({},"COMBINED")
assert missing == (None,1.0,None,1.0)

try:
    m.assert_development_only([2024,2025])
except ValueError as e:
    assert "sealed 2025" in str(e)
else:
    raise AssertionError("2025 must remain sealed")

# Negative deltas with a fully negative log-loss CI and 3/4 season direction
# are only a NEXT_STAGE signal, never production promotion.
gate = m.promotion_signal(
    {"metrics":{
        "log_loss_delta":{"observed":-0.01,"ci95_high":-0.001},
        "brier_delta":{"observed":-0.002,"ci95_high":0.001},
    }},
    seasons_improved_log_loss=3,
    seasons_total=4,
)
assert gate["status"] == "NEXT_STAGE_CHALLENGER_SIGNAL"
assert gate["requiresProductionValidation"] is True

print("PASS NFL State Intelligence 0.1.4 challenger contracts · 2025 sealed")

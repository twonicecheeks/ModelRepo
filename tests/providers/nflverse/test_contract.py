#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[3]
MOD = ROOT / "packages/providers/nflverse/src/contract.py"
spec = importlib.util.spec_from_file_location("nflverse_contract", MOD)
contract = importlib.util.module_from_spec(spec); spec.loader.exec_module(contract)

c = contract.load_contract()
assert c["contractVersion"] == "0.2.0"
assert c["projectPhase"] == "MODEL_2.9.0_NFL_PHASE1B_SNAPSHOT"
assert c["historicalEvaluationPolicy"]["holdoutSeason"] == 2025
assert c["historicalEvaluationPolicy"]["prospectiveSeason"] == 2026

specs = contract.source_specs()
for required in ("schedules", "play_by_play", "players", "weekly_rosters"):
    assert specs[required].required_for_phase1, required
assert specs["play_by_play"].url_for_season(2024).endswith("play_by_play_2024.parquet")
assert specs["weekly_rosters"].url_for_season(2025).endswith("roster_weekly_2025.parquet")

assert contract.canonical_game_id(2026, 1, "DAL", "PHI") == "2026_01_DAL_PHI"
assert contract.parse_game_id("2026_01_DAL_PHI") == {"season": 2026, "week": 1, "away_team": "DAL", "home_team": "PHI"}
assert contract.season_role(2015) == "HISTORY_SEED_ONLY"
assert contract.season_role(2024) == "DEVELOPMENT_CANDIDATE"
assert contract.season_role(2025) == "HOLDOUT_NEVER_FIT"
assert contract.season_role(2026) == "PROSPECTIVE_ONLY"

contract.assert_independent_feature_names(["pass_epa", "rest_days"])
for bad in ("spread_line", "home_moneyline", "home_score", "result"):
    try:
        contract.assert_independent_feature_names(["pass_epa", bad])
    except ValueError:
        pass
    else:
        raise AssertionError(f"forbidden field admitted: {bad}")

assert contract.normalize_team_abbr("OAK") == "LV"
assert contract.normalize_team_abbr("SD") == "LAC"
assert contract.normalize_team_abbr("LAR") == "LA"
assert contract.normalize_team_abbr("WSH") == "WAS"

raw = json.loads((ROOT / "packages/providers/nflverse/NFLVERSE_DATA_CONTRACT.json").read_text())
assert raw["sources"]["injuries"]["status"] == "NOT_A_2026_PRODUCTION_PROVIDER"
assert raw["sources"]["depth_charts"]["status"] == "DEFERRED_UNTIL_SCHEMA_ADAPTER"
print("PASS nflverse Phase 1B contract: canonical identity, team-history continuity, holdout policy, and market isolation")

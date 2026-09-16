#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
sys.path.insert(0, str(ROOT / "packages/providers/nflverse/src"))

import qb_official_target_authority_019 as q
import qb_official_stats_adapter_019 as p

assert q.assert_development_only([2016, 2024]) == (2016, 2024)
assert p.assert_development_only([2016, 2024]) == (2016, 2024)
for mod in (q, p):
    try:
        mod.assert_development_only([2025])
    except ValueError:
        pass
    else:
        raise AssertionError("2025 must remain sealed")

assert p.PARQUET_URL.format(season=2024).endswith("/stats_player_week_2024.parquet")

target = {
    "game_id": "2022_16_LAC_IND",
    "season": 2022,
    "week": 16,
    "team": "IND",
    "observed_start_qb_gsis_id": "QB1",
    "settlement_pass_attempts": 29,
    "settlement_completions": 17,
    "passing_yards": 144,
    "structural_sacks": 7,
}
official = {
    "game_id": "2022_16_LAC_IND",
    "player_id": "QB1",
    "team": "IND",
    "attempts": 29,
    "completions": 17,
    "passing_yards": 143,
    "sacks_suffered": 7,
    "carries": 1,
    "rushing_yards": 0,
    "source_sha256": "abc",
}
assert q.target_key(target) == ("2022_16_LAC_IND", "QB1")
assert q.official_key(official) == ("2022_16_LAC_IND", "QB1")
joined = q.attach_official_target(target, official)
assert joined["official_attempts"] == 29
assert joined["official_passing_yards"] == 143
assert joined["pbp_vs_official_passing_yards_delta"] == 1

s = q.comparison_summary(
    [{"p": 29, "o": 29}, {"p": 144, "o": 143}],
    "p", "o",
)
assert s["n"] == 2
assert s["exact"] == 1
assert s["nonzero"] == 1
assert s["maxAbsoluteDelta"] == 1

comparisons = {
    name: {"exactPct": 99.0}
    for name, _, _ in q.COMPARISONS
}
ok, disp = q.authorization(
    target_rows=100,
    joined_rows=100,
    duplicate_official_keys=0,
    missing_required_values=0,
    team_mismatches=0,
    comparisons=comparisons,
)
assert ok and disp == "OFFICIAL_TARGET_LAYER_READY_FOR_QB_MODELING"

bad = dict(comparisons)
bad["passing_yards"] = {"exactPct": 89.9}
ok, disp = q.authorization(
    target_rows=100,
    joined_rows=100,
    duplicate_official_keys=0,
    missing_required_values=0,
    team_mismatches=0,
    comparisons=bad,
)
assert not ok and disp == "OFFICIAL_TARGET_SANITY_FAIL_PASSING_YARDS"

print("PASS NFL QB State 0.1.9 official target authority contracts · 2025 sealed")

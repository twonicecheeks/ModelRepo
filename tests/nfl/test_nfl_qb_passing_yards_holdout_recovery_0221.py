#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))

import qb_passing_yards_holdout_recovery_0221 as q221


def main() -> int:
    assert q221.resolve_pbp_scope_field({"season_type", "game_type"}) == "season_type"
    assert q221.resolve_pbp_scope_field({"game_type"}) == "game_type"
    try:
        q221.resolve_pbp_scope_field({"season", "week"})
        raise AssertionError("missing explicit REG scope field should fail")
    except ValueError:
        pass

    assert q221.is_regular_pbp_row({"season": 2025, "season_type": "REG"}, "season_type")
    assert not q221.is_regular_pbp_row({"season": 2025, "season_type": "POST"}, "season_type")
    assert not q221.is_regular_pbp_row({"season": 2024, "season_type": "REG"}, "season_type")

    q221.assert_no_completed_holdout(False)
    try:
        q221.assert_no_completed_holdout(True)
        raise AssertionError("completed holdout rerun should fail")
    except ValueError:
        pass

    meta = q221.recovery_metadata(prior_source_snapshots=1, excluded_nonreg_team_games=26, scope_field="season_type")
    assert meta["postOpenInfrastructureCorrection"] is True
    assert meta["excludedNonRegularTeamGames"] == 26
    assert meta["modelChanged"] is False
    assert meta["featureContractChanged"] is False
    assert meta["dispositionPolicyChanged"] is False

    print("PASS NFL QB Model 0.2.2.1 recovery contracts · REG scope explicit · completed holdout rerun blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

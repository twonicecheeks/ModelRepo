"""NFL QB Model 0.2.2.1 — post-open infrastructure recovery helpers.

The 0.2.2 holdout seal was opened, but evaluation aborted before scoring because the
PBP side admitted non-regular-season games while the frozen development target and
official weekly target source were REG-only. This patch is intentionally limited to
restoring the preregistered REG target universe. It does not change the frozen model,
features, benchmark, bootstrap rule, or disposition policy.
"""
from __future__ import annotations

from typing import Any

VERSION = "0.2.2.1"
LINEAGE = "nfl-qb-passing-yards-2025-holdout-reg-scope-recovery-v0.2.2.1-2026-09-16"
HOLDOUT_SEASON = 2025
CORRECTION = (
    "post-open infrastructure correction only: restrict 2025 PBP mechanism universe "
    "to REG, matching the frozen 2016-2024 development target and REG-only official weekly stats"
)


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def resolve_pbp_scope_field(schema_fields: set[str]) -> str:
    """Require an explicit regular/postseason discriminator; never infer by join success."""
    if "season_type" in schema_fields:
        return "season_type"
    if "game_type" in schema_fields:
        return "game_type"
    raise ValueError("2025 PBP has no season_type/game_type field; cannot establish frozen REG holdout universe")


def is_regular_pbp_row(row: dict[str, Any], scope_field: str) -> bool:
    return int(row.get("season") or 0) == HOLDOUT_SEASON and clean(row.get(scope_field)).upper() == "REG"


def assert_no_completed_holdout(pointer_exists: bool) -> None:
    if pointer_exists:
        raise ValueError(
            "QB 0.2.2 holdout already has a completed result pointer; rerun/reselection is forbidden"
        )


def recovery_metadata(*, prior_source_snapshots: int, excluded_nonreg_team_games: int, scope_field: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "lineage": LINEAGE,
        "postOpenInfrastructureCorrection": True,
        "correction": CORRECTION,
        "priorHoldoutSourceSnapshots": int(prior_source_snapshots),
        "pbpScopeField": str(scope_field),
        "targetUniverse": "2025 REG team-games only",
        "excludedNonRegularTeamGames": int(excluded_nonreg_team_games),
        "modelChanged": False,
        "featureContractChanged": False,
        "benchmarkChanged": False,
        "bootstrapPolicyChanged": False,
        "dispositionPolicyChanged": False,
    }


if __name__ == "__main__":
    print(f"NFL QB holdout recovery {VERSION} · {LINEAGE}")

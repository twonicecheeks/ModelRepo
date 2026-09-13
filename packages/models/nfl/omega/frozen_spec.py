"""OMEGA 0.11 explicit frozen specification constants.

This module contains no sportsbook logic and no model fitting.  It is the
pre-holdout contract for the frozen OMEGA standard-defensive T+A count model.
"""
from __future__ import annotations

VERSION = "0.11.0"
LINEAGE = "omega-tackle-v0.11.0-frozen-h008-h012-2026-09-11"
HOLDOUT_SEASON = 2025
HISTORY_SEED_SEASON = 2016
GLOBAL_FIT_SEASONS = tuple(range(2017, 2025))
GAME_TYPE = "REG"

# Frozen selections already made before opening the OMEGA 2025 holdout.
XDEFENSIVE_SNAPS_L2 = 0.1
XTO_L2 = 0.3
EXPOSURE_L2 = 0.01
FAMILY_ALPHA = 50.0
TEAM_WINDOW_GAMES = 8
PLAYER_FAMILY_RATE_WINDOW_GAMES = 8
FAMILIES = ("RUSH", "COMPLETE_PASS", "SCRAMBLE", "SACK", "OTHER_PASS")

TARGET = "combined_standard_def_scrimmage"
TARGET_DESCRIPTION = (
    "Original-defense standard-scrimmage combined tackle credit units only; "
    "special teams and nullified/deleted plays excluded. This is a research "
    "count target, not an assumed sportsbook settlement formula."
)

# The benchmark is the exact strict-lag baseline used in OMEGA 0.2.
BENCHMARK = "strict_lag_last4_xtc_with_position_cold_start_fallback"

VERDICT_RULES = {
    "STRONG_PASS": (
        "Frozen OMEGA improves both MAE and RMSE versus the frozen benchmark, "
        "and paired game-cluster bootstrap 95% CI lower bounds for both MAE and "
        "RMSE improvements are > 0."
    ),
    "DIRECTIONAL_PASS": (
        "Frozen OMEGA improves both MAE and RMSE versus the frozen benchmark, "
        "but the STRONG_PASS bootstrap criterion is not met."
    ),
    "FAIL_BOTH": "Frozen OMEGA worsens both MAE and RMSE versus the frozen benchmark.",
    "MIXED": "All other outcomes.",
}


def verdict(
    benchmark_mae: float,
    model_mae: float,
    benchmark_rmse: float,
    model_rmse: float,
    mae_ci_low: float,
    rmse_ci_low: float,
) -> str:
    mae_imp = benchmark_mae - model_mae
    rmse_imp = benchmark_rmse - model_rmse
    if mae_imp > 0 and rmse_imp > 0 and mae_ci_low > 0 and rmse_ci_low > 0:
        return "STRONG_PASS"
    if mae_imp > 0 and rmse_imp > 0:
        return "DIRECTIONAL_PASS"
    if mae_imp < 0 and rmse_imp < 0:
        return "FAIL_BOTH"
    return "MIXED"

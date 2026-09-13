# OMEGA Tackle Model 0.1.1 — Exposure Universe Hardening

## Problem discovered after the 0.1 semantic audit

OMEGA 0.1's tackle event ledger is valid, but `omega_tackle_player_games.csv` is event-seeded. A player who logs defensive snaps and records zero tackle credits has no event and therefore no player-game row. Fitting a player tackle model on only event-positive player-games would condition on success and bias tackle rates upward.

## Fix

0.1.1 uses the existing nflverse snap-count snapshot to create every regular-season 2016–2024 player-game with `defense_snaps > 0`, resolves PFR identity to GSIS where possible, and left-joins the immutable 0.1 tackle-credit event ledger. Zero-credit games become explicit zeros.

Event-positive rows with no snap join are preserved as `EVENT_ONLY_NO_SNAP` for reconciliation but are not eligible for exposure-rate fitting.

## Fit rule for future OMEGA phases

Player-level standard defensive tackle models may only train on rows where:

- `eligible_standard_rate_fit == 1`
- `game_type == REG`
- season is in the development/validation universe permitted by that phase

The 2025 OMEGA holdout remains unopened. Market data remains outside the prediction path.

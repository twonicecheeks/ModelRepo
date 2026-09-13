# OMEGA Tackle Model 0.6 — H003 Replacement-Role Convexity

H003 tests a specific pre-registered niche: **a defender whose projected role expands materially may not scale tackle production linearly with snaps**.

Frozen champion before this phase: OMEGA 0.4 H008 topology + OMEGA 0.2.2 H012 exposure. OMEGA 0.5 H002 was mixed and is **not promoted**.

The target-game participant set is never used. The role jump is strictly prior:

- `prechange_baseline_snap_share`: mean of up to four appearances before the most recent appearance, falling back to a strictly-prior position average.
- `predicted_snap_share`: frozen H012 prediction.
- activation: predicted role is at least **10 percentage points** above the pre-change baseline and the player has at least one prior game.

For activated rows only:

`xTC_H003 = xTC_H008 × min(1.50, 1 + beta × role_jump × history_confidence)`

`history_confidence = min(1, prior_games / 2)`

Beta is selected on 2021–2023 only. 2024 is diagnostic-directed confirmation, and OMEGA 2025 remains sealed.

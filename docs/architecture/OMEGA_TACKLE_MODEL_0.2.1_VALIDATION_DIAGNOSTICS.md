# OMEGA Tackle Model 0.2.1 — Validation Diagnostics

This phase is a diagnostic gate between the transparent 0.2 baseline and any new causal challenger. It does **not** fit or tune a model and does **not** read 2025, sportsbook prices, or settlement data.

## Why it exists

The 0.2 headline improvements are directionally positive, but aggregate MAE can hide failure modes. 0.2.1 therefore measures paired game-cluster bootstrap uncertainty, position/role/history slices, count calibration, player snap-exposure error, and residual coupling between player tackle misses and team xTO misses.

## Pre-registered diagnostic hypotheses

**H011 — Opportunity-Density Coupling.** If tackle-generating opportunity density contains player-level signal beyond raw defensive snaps, OMEGA 0.2 player residuals should move positively with team xTO/opportunity-density residuals. This is a diagnostic only; a positive result would justify a later preregistered xTO-allocation challenger.

**H012 — Exposure Error Dominance in Sparse Histories.** Players with 0–1 prior games should show larger snap/exposure and xTC errors than established players if role uncertainty is the principal cold-start failure mechanism.

## Integrity

2024 is diagnostic only. No parameter is selected from 2024. OMEGA 2025 remains sealed.

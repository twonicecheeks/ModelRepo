# OMEGA 0.16 — Prospective Probability Alpha

## Purpose

OMEGA 0.15 established that a role-conditioned Negative Binomial distribution (`NB_ROLE`) converts the frozen H008+H012 mean into better count probabilities than Poisson, both in chronological 2021–2023 selection and 2024 confirmation.

OMEGA 0.16 freezes that probability architecture and begins the 2026 prospective regime.

## Permanent model boundary

- Frozen independent mean: H008 opportunity footprint + H012 exposure.
- Frozen count distribution: NB2, dispersion conditioned only on H012 **predicted** snap-share role tier.
- Mean coefficients remain the exact 0.12 coefficients fit on 2017–2024.
- Distribution parameters remain fit through 2024.
- 2025 is never a tuning season again.
- Completed 2025 football/tackle state may enter 2026 only as strictly-prior rolling history after all architecture/parameters are frozen.

## 2026 target-player universe

The historical holdout was conditional on target-game defensive participation. That is not acceptable live. OMEGA 0.16 instead defines the prospective candidate universe from a timestamped **pregame roster capture**.

The first adapter uses nflverse schedule, weekly roster, injury-report, player, and depth-chart feeds. This is intentionally labeled `SECONDARY_PROVIDER`. It can support prospective research but cannot by itself establish authoritative game-day active/inactive status.

Therefore `verified_ready` remains false for all nflverse-only rows. A later official NFL/team inactive adapter or explicit verified manual overlay is still required for VERIFIED Trust.

## Week 1 integrity

The first prospective mean/probability builder is intentionally restricted to 2026 Week 1. It uses complete 2025 realized football state as prior history but admits **zero 2026 outcomes**, including the Wednesday/Thursday games that may already have been played when the remaining Week 1 slate is predicted.

This preserves the same-week chronology doctrine used by the holdout.

## No market data

The prospective probability ledger contains model probabilities and fair prices for half-point T+A thresholds 0.5 through 14.5, but no sportsbook prices, no edge, no EV, no pick, and no settlement result.

Market comparison remains a separate downstream phase.

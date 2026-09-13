# OMEGA Tackle Model 0.8 — H005 Venue / Year Credit Environment

## Purpose

Test the pre-registered H005 hypothesis that official assist-credit behavior may have a persistent game-location environment after OMEGA has already modeled player role, opportunity topology, position and prior player credit behavior.

## Important limitation

The frozen Phase1 schedule artifact does **not** contain a stadium ID or official statistician/crew identity. OMEGA 0.8 therefore uses `source_home_team` on games whose `location` equals `Home` as a **home-franchise venue proxy**. Neutral-site games receive no venue adjustment. A positive result is a research lead only; production use would require actual stadium/stat-crew verification.

## Champion discipline

H004 was only a directional combined-T+A pass. Its separate primary/assist predictions are used as a research scaffold because H005 concerns assist credit, but **H008 remains the T+A champion** unless H005 robustly beats H008 under the combined-count gate.

## Fixed mechanism

For 2024 confirmation:

- year factor: 2023 league actual/predicted assist ratio;
- venue residual: 2021–2023 home-franchise assist actual/predicted ratio relative to league;
- credibility: venue factor is linearly shrunk toward 1.0 until 24 prior home games;
- primary prediction is unchanged;
- assist prediction receives year × venue adjustment.

No H005 hyperparameter grid is fit to 2024.

## Holdout

2025 OMEGA tackle outcomes remain sealed. Market data and sportsbook settlement conventions remain outside the model.

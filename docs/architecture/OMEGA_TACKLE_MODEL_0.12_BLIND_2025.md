# OMEGA 0.12 — Blind 2025 Holdout Ledger

Purpose: produce the immutable, hashed 2025 prediction ledger required by the OMEGA 0.11 frozen contract **before** score attachment.

The package is pinned to frozen spec SHA256 `c2ca80b6a144c3aa86bc41bdb82f6f5618ffa279a38f4c6d358025ed7fbd69fb`.

Global coefficients are fit on 2017–2024 REG only with frozen hyperparameters. 2025 then runs walk-forward by week. Predictions for the entire week are emitted before that week's realized football/tackle state may update later weeks.

The historical count holdout remains conditional on players who actually logged >0 defensive snaps in the target game. Only that participation boolean defines the evaluation universe; target snap magnitude and target tackle counts are not prediction inputs and are not serialized. A future live active/inactive/depth-chart layer is still required.

This phase does not score 2025, read market data, call OddsPapi, or assume a sportsbook settlement formula.

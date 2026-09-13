# OMEGA 0.14 — Post-Holdout Production Gate

Purpose: move from a sealed, validated historical count model to a fail-closed live pregame architecture without reopening 2025 model selection.

This release does **not** refit OMEGA, create betting probabilities, ingest sportsbook prices, or claim market edge.

It adds:

1. An immutable seal of the completed 2025 STRONG_PASS result.
2. A raw source-neutral pregame availability/role schema.
3. Immutable snapshot ingestion that forbids market/model-derived fields.
4. A fail-closed freshness/completeness audit for target player-games.
5. An offline inventory of existing repo/provider capabilities so the next release can choose the authoritative source adapter from evidence rather than assumption.

The future live chain is intended to be:

`authoritative football status source -> raw immutable pregame snapshot -> identity/status/depth normalization -> fail-closed readiness gate -> independent OMEGA-I count prediction -> distribution -> market comparison -> Trust`

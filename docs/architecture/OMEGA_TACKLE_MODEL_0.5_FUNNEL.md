# OMEGA Tackle Model 0.5 — H002 Funnel Rigidity / Allocation

OMEGA 0.5 tests one pre-registered mechanism from the OMEGA 0.1 registry:

> **H002 — Tackle funnel rigidity:** some defenses allocate tackle credit to a stable set of players across opponents. High rigidity should make within-defense allocation more predictable.

Frozen upstream champion components are OMEGA 0.2.2 H012 exposure and OMEGA 0.4 H008 opportunity topology. H011 remains rejected.

The challenger measures prior-only similarity of a team's player tackle-credit-share vectors, forms a player's lagged share of exact team standard defensive credits, adjusts that share for the already-frozen H012 expected snap role, and blends that allocation prediction with H008 only in proportion to prior rigidity and player-history confidence.

A critical integrity rule is that the model **never normalizes across the players who actually appeared in the target game**. The realized target participant set is future information and would create hidden lineup leakage.

2021–2023 choose only the blend coefficient. 2024 is diagnostic-directed confirmation. OMEGA 2025 remains sealed.

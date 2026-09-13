# OMEGA 0.17 — Downstream Market Comparison Alpha

Purpose: compare the immutable OMEGA-I Week 1 probability ledger to immutable raw T+A prices without allowing prices to influence the independent model.

## Frozen reference

Expected OMEGA-I ledger SHA256:
`fe4991a743a1c02994b59d473a1bec9a1ccafa61a60548df43f2f5292e4ca08a`

## Market rules

- Raw market snapshots may contain posted prices and settlement metadata only.
- Raw snapshots reject model probability, xTC, edge, EV, fair-price, or pick fields.
- T+A comparison supports half-point lines from 0.5 through 14.5.
- Two-sided prices: posted-price EV plus proportional no-vig sanity check.
- One-sided prices: EV-only. No no-vig market probability is manufactured.
- Unknown settlement conventions block actionability.
- OMEGA 0.16 player rows are not VERIFIED-ready until an authoritative game-day inactive feed is integrated, so 0.17 produces zero actionable rows by design.
- Positive calculated EV is research output, not a recommended bet.

## Workflow

1. `init_omega_tackle_market_017.command`
2. Populate/export raw T+A market rows into the canonical schema.
3. `append_omega_tackle_market_snapshot_017.command <file>`
4. `compare_omega_tackle_market_017.command`
5. Use `inventory_omega_tackle_market_sources_017.command` to inspect existing PropsMadness/local capture infrastructure without network access.

# Decision 0005 — Quarantine legacy live model state

Created: 2026-09-06T18:59:40Z

The structured PropsMadness table provider and official-starter board are now authoritative for live pitcher-market identity and pricing.

Removed from live operational storage on extension startup:
- propsmadnessBoardV05 / V04
- propsmadnessMoneylineSlateV05 / V04
- old scan/batch diagnostics and freeze-selection caches
- versioned table-probe / old pipeline operational keys

Preserved intentionally:
- historical moneyline prediction ledger
- historical K prediction ledger
- reference-market history

The old workflow UI is hidden/quarantined so stale cached model inputs cannot generate new live recommendations while the K and moneyline consumers are migrated.

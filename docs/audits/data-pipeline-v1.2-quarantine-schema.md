# Data Pipeline v1.2 audit

Installed: 2026-09-06T18:59:40Z
Backup: `/Users/abbeyfelix/Developer/MODEL/archive/migrations/data-pipeline-v12-before-20260906-145936`

Changes:
- stable pipeline storage keys
- legacy live operational caches quarantined/removed
- historical evaluation ledgers preserved
- old workflow UI hidden from normal operation
- compact source-schema inventory added to the structured provider for one migration step
- active tests moved from versioned tests/data-pipeline-v1.1 to stable tests/data_pipeline
- no K, moneyline, offense, or OddsPapi trust coefficients changed

The schema inventory is temporary migration instrumentation and should be removed once the structured K/ML input map is confirmed.

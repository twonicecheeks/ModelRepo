# Data Pipeline v1.1 clean-cut audit

Installed: 2026-09-06T18:45:53Z
Backup: `/Users/abbeyfelix/Developer/MODEL/archive/migrations/data-pipeline-v11-before-20260906-144548`

Changes:
- Structured PropsMadness table provider promoted to stable module paths.
- Official MLB probable-starter reconciliation added.
- Market quality states: PRICED / PARTIAL / UNPRICED / MISSING.
- Both starters must map to the same PropsMadness match ID or the game is BLOCKED.
- Extra/stale PropsMadness pitcher rows never enter the official starter board.
- v1 raw-response duplication removed from the active snapshot.
- Legacy scan-scope/probe modules removed from active runtime.
- Legacy Hydrate entry points blocked from normal operation.
- MLB moneyline, K, offense equations and OddsPapi trust math were not changed.

# Data Pipeline v1.2.1 — UI mount repair

Installed: 2026-09-06T19:09:09Z
Archive: `/Users/abbeyfelix/Developer/MODEL/archive/migrations/data-pipeline-v121-ui-before-20260906-150905`

Regression fixed:
- v1.2 could update the extension shell to 2.3.1 while the Data Pipeline controller failed to mount, leaving the SYNC button absent and the retired Batch Workflow visible.

Repair:
- stable bootstrap guard loads before popup.js
- stable starter core + controller load deterministically before popup.js
- duplicate pipeline script tags are removed before canonical reinsertion
- boot guard immediately quarantines the retired Batch Workflow
- controller publishes a runtime-ready signal
- if controller boot fails, the UI now shows an explicit RUNTIME LOAD ERROR + retry button instead of silently disappearing

No K, moneyline, offense, or OddsPapi trust coefficient was changed.
No versioned runtime directory was added.

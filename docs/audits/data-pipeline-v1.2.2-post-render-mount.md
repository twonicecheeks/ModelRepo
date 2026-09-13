# Data Pipeline v1.2.2 — post-render mount repair

Installed: 2026-09-06T19:24:02Z
Archive: `/Users/abbeyfelix/Developer/MODEL/archive/migrations/data-pipeline-v122-post-render-before-20260906-152358`

Root cause fixed:
- v1.2.1 loaded the pipeline before popup.js.
- popup.js then rebuilt/replaced the popup DOM and erased the pipeline host/panel.
- the runtime itself could be healthy while its UI disappeared, explaining why no boot error appeared.

Repair:
- pipeline starter core + controller now load after popup.js and model_v2.js
- bootstrap is the final script and verifies/remounts the panel
- startup remount checks are bounded to ~5 seconds; no permanent observer/interval is left running
- retired Batch Workflow remains CSS-quarantined
- no new versioned runtime folder was created

No K, moneyline, offense, or OddsPapi trust coefficient changed.

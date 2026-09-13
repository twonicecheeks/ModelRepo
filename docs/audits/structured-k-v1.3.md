# MODEL 2.4.0 Structured K integrated post-install audit

Installed: 2026-09-06T21:06:06Z
Archive: `/Users/abbeyfelix/Developer/MODEL/archive/migrations/structured-k-v240-before-20260906-170600`

Active runtime:
- providers/propsmadness/table_core.js
- providers/propsmadness/table_main.js
- providers/mlb_official/starter_core.js
- providers/baseball_savant/savant_core.js
- models/mlb/k/structured_k_core.js
- features/data_pipeline/controller.js
- model_v2.js consumes `model_mlb_k_projection_board_current` for K edges

Retired from active runtime:
- player-page Hydrate scanner UI/scan-scope files
- schema-probe/schema-inventory instrumentation
- remount/bootstrap Data Pipeline runtime
- version-numbered live PropsMadness board caches

Intentionally not physically deleted yet:
- the old K/ML/offense functions still co-located inside popup.js. They are quarantined and no longer consumed for live structured K. Deleting pieces of that monolith before dependency extraction would risk the still-unmigrated moneyline/offense code. The next cleanup cut should extract those consumers first, then delete the legacy scanner/K block as one dependency-verified change.

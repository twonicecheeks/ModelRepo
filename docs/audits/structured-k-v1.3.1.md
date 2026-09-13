# MODEL 2.4.1 Independent K Distribution post-install audit

Installed: 2026-09-06T21:47:33Z
Archive: \

Active runtime:
- providers/propsmadness/table_core.js
- providers/propsmadness/table_main.js
- providers/mlb_official/starter_core.js
- providers/baseball_savant/savant_core.js
- models/mlb/k/structured_k_core.js v1.2
- features/data_pipeline/controller.js v1.3.1
- model_v2.js consumes \ and evaluates the distribution at OddsPapi lines

Model/market separation invariant:
- target K line weight in expected K = 0
- target K price weight in expected K = 0
- moving only the target K line/price must leave expected K unchanged
- OddsPapi exact-line evaluation happens downstream in Trust

Fail-closed boundaries remain:
- pregame only
- verified official starter/event identity
- current Pitcher Outs line required
- ER / Hits Allowed / Walks must each expose either a structured current line or usable table history
- official 9/9 opposing lineup required
- Savant skill row required for starter + all nine hitters
- missing/stale/unsynchronized model-source timestamps block
- opener/bulk role is blocked by Trust

Retired runtime remains retired; no probe, scan-scope or remount bootstrap files are restored.

# Decision 0003 — Retire player-page Hydrate from normal operation

Created: 2026-09-06T18:45:52Z

The PropsMadness whole-table API is now the primary MLB pitcher-market acquisition path.
The legacy player-page scanner is blocked from normal UI/workspace operation.

Deleted from active extension source:
- scan_scope_v2_2.js
- scan_scope_v2_2_core.js
- PropsMadness table probe runtimes
- v1.0 root-level table-ingestor runtimes

Migration hold:
- popup.js still contains legacy scan implementation because the existing K/ML model runtime also lives in that file and still consumes profile-derived lineup/bullpen fields. The scanner entry points are blocked; this code will be physically removed when those model inputs are migrated to structured providers.

This prevents a risky "delete first, discover hidden dependency later" refactor while ensuring the obsolete scanner cannot be used normally.

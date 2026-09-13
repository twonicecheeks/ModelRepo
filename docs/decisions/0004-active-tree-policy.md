# Decision 0004 — Active tree stays clean

Created: 2026-09-06T18:45:52Z

Rules:
1. Chrome loads only:       /Users/abbeyfelix/Developer/MODEL/apps/chrome-extension/src
2. Active runtime contains no zip, backup, rollback, probe, or versioned-patch folders.
3. Active provider source uses stable paths under packages/providers/*/src.
4. Superseded code moves to archive/migrations, never beside active source.
5. Every migration records what was deleted, what remains on migration hold, and why.

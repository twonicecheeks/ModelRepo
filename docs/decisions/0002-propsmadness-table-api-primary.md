# Decision 0002 — PropsMadness table API is the primary MLB pitcher-market provider

Created: 2026-09-06T18:29:51Z

The primary PropsMadness acquisition path is the structured same-origin table API:

- /api/offer/mlb/matches
- /api/team-rankings/mlb/season/current/all/by-season
- /api/offer/mlb/explore/player-strikeouts
- /api/offer/mlb/explore/player-pitcher-outs
- /api/offer/mlb/explore/player-earned-runs
- /api/offer/mlb/explore/player-hits-allowed
- /api/offer/mlb/explore/player-walks

Individual player-page Hydrate is legacy fallback only and is not used by the Table Ingestor.
The provider fails closed if any required market endpoint or schema is missing.

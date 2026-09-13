# Decision 0007 — Structured K source contract

Installed: 2026-09-06T21:06:05Z

Production K inputs now have one owner each:
- PropsMadness table API: current K / Outs / ER / Hits Allowed / Walks lines, prices, recent arrays and season market averages
- MLB Stats API schedule with `hydrate=probablePitcher(note),lineups`: gamePk, official starters and first-pass published batting orders
- MLB Stats API `/game/{gamePk}/boxscore`: fallback only when a pregame lineup is not complete in schedule hydration; starting batting order + MLB player IDs
- Baseball Savant Custom Leaderboard CSV: current-season K%, Whiff%, Swing% and player sample size keyed by MLB player ID, with prior-season fallback when the current sample is thin
- Derived Contact% = 100 - Whiff%; derived SwStr% = Swing% * Whiff% / 100
- OddsPapi: market truth/value comparison only; never an input to the independent K probability

PropsMadness team rankings are ranks (1-30), not raw rates. They are preserved as ordinal matchup context and never converted into fake percentages. The official nine-man MLB lineup joined to Savant supplies the matchup-rate inputs. PropsMadness tables remain the primary workload/recent-performance source for K, Outs, ER, Hits Allowed and Walks.

The structured K lineage is `mlb-k-v0.8.1-structured-table-savant-2026-09-06` and begins in `PROSPECTIVE_INPUT_MIGRATION`. Trust Layer cannot promote it to VERIFIED until forward validation explicitly changes that status to VALIDATED.

# OMEGA Tackle Model 0.1 — Event Foundation

OMEGA is a separate NFL player-prop research line. It does not modify the frozen NFL game model.

## Core thesis

Do not model tackle totals as rolling averages. Model the process that creates official tackle credit:

`defensive play volume -> situational exposure -> tackle-generating play topology -> player involvement -> official credit allocation -> market settlement`

The first hidden variable is **xTO: Expected Tackle Opportunity**. 0.1 does not fit xTO yet; it builds the event ledger required to do so without losing the official credit distinctions.

## Source / holdout policy

- Development event universe: 2016–2024 regular season only.
- 2025 is a new **OMEGA-specific tackle holdout** and is not opened by this build.
- Postseason is a separate regime and is intentionally excluded.
- Existing nflverse immutable Phase1 PBP is reused; OddsPapi is not called.
- Existing Phase2C snap counts are joined when available. The event build remains valid without them.

## Credit semantics

nflverse exposes three distinct credit families that map to official NFL statistical concepts:

1. `SOLO`
2. `PRIMARY_WITH_ASSIST` — the primary tackler on a play where another player assisted
3. `ASSIST`

OMEGA stores all three separately. A sportsbook's displayed market name does **not** determine the formula automatically. Book rules must later specify whether special-teams tackles, assists, stat corrections, and other categories settle the market.

## Output tables

- `omega_tackle_credit_events.csv` — one row per raw tackle-credit slot.
- `omega_tackle_play_opportunities.csv` — one row per regular-season play, including play topology and credit counts.
- `omega_tackle_player_games.csv` — player-game aggregates with separated credit classes and defensive snap joins when resolvable.
- `omega_duplicate_credit_anomalies.csv` — repeated same-player/same-role credits surfaced for review, never silently deleted.
- `OMEGA_HYPOTHESIS_REGISTRY.csv` — pre-registered causal research questions.

## Market ledger

0.1 also creates an append-only raw market-snapshot workflow. It accepts CSV/JSON/JSONL exports for:

- tackles + assists
- solo tackles
- assists

Raw market snapshots explicitly reject model probability, edge, EV, or pick fields. This lets us collect price history now without contaminating future model fitting.

## Next research gate

After the real 0.1 audit is reviewed:

1. Build a first xTO baseline on 2016–2023.
2. Use 2024 for chronological validation only.
3. Test position/role-specific tackle opportunity generation, not raw T+A averages.
4. Keep 2025 sealed until the OMEGA feature/distribution specification is frozen.
5. In parallel, discover the PropsMadness NFL tackle-market payload and begin timestamped line capture.

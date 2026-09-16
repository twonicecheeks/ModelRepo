# OMEGA 0.36 — PropsMadness NFL T+A multibook main-line layer

Purpose: capture the sportsbook-comparison feed displayed by PropsMadness for NFL Player Tackles + Assists without changing frozen OMEGA forecasts.

## Source endpoints

Discovery:
`/api/offer/nfl/explore/player-tackles-assists`

Matches:
`/api/offer/nfl/matches`

Per-player main-line comparison:
`/api/players/{playerId}/match/{matchId}/bet-offers/player-tackles-assists`

The alternate-line endpoint is intentionally not called in 0.36. It may be used later for a small, explicitly selected research shortlist only.

## Capture policy

- Browser-session capture only from the user's authenticated PropsMadness page.
- Credentials/cookies are used by the browser request but are never serialized into the capture.
- Maximum concurrency is 4.
- A partial per-player board is rejected if any requested player endpoint fails HTTP validation.
- Raw responses, request observation timestamps, and the final JSON capture are preserved immutably.
- Every normalized quote is labeled `PROPSMADNESS_AGGREGATED_BOOK_QUOTE_NOT_DIRECT_VERIFIED`.
- PropsMadness is an intermediary source; a quoted sportsbook price is not considered directly verified at that sportsbook until separately checked.

## Downstream comparison

The 0.36 importer compares these market quotes only after the immutable Week 2 OMEGA 0.33 freeze. No sportsbook information enters model fitting or forecast generation.

Decision probability track remains `FROZEN_OMEGA_CONTROL`.

Current-role probability remains `SHADOW_ONLY_NOT_PROMOTED`.

Role-state policy remains unchanged:
- `ROLE_ALIGNED`: eligible for primary direct-price verification when control EV is positive and control/role shadow agree on side.
- `STARTER_CONFLICT_REVIEW`: review only.
- `REVIEW_BACKUP_CONFLICT`: quarantined.
- `NO_DEPTH_FALLBACK_H012`: review only.

## Sharp reference policy

`Pinnacle` and `Circa Sports` are retained as sharp-reference books when present.

Sharp comparisons are made only at the exact same half-line. No interpolation, conversion, or averaging across different lines is allowed.

When one or both sharp books have two-sided prices at the same line, their individual no-vig probabilities are computed. If both are present, their no-vig probabilities are averaged for a same-line sharp consensus. A single available sharp book remains a one-book reference and is explicitly count-tagged.

## Retail shortlist

The main-line retail shortlist considers DraftKings, FanDuel, Caesars, BetMGM, Hard Rock, Fanatics, and bet365. For each player, it selects the observed retail line/price combination with the largest frozen-control EV. This is market triage only, not a bet recommendation.

Every shortlist row still requires direct sportsbook verification before a decision-ledger entry.

## Integrity

OMEGA 0.36 performs:
- model refits: 0
- frozen model writes: 0
- OddsPapi requests: 0
- alternate-line requests: 0

The multibook layer is downstream market observation only.

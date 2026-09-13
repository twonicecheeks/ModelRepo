# Decision 0010 — OddsPapi MLB player-prop market truth

Installed: 2026-09-07T00:53:44Z

Moneyline and player-prop market ownership are intentionally different.

- MLB game moneyline sharp reference: Pinnacle + Circa when available.
- MLB starter strikeout market truth: OddsPapi US retail player-prop books.
- Default K books: DraftKings, FanDuel, Caesars, BetMGM, Hard Rock Bet.
- Player-prop prices are parsed from `outcomes[*].players[playerId]`; `players["0"]` is skipped.
- OddsPapi names such as `Last, First` are normalized conservatively to the official MLB starter name.
- Strikeout lines are resolved from the OddsPapi `/v4/markets` catalogue by playerProp + strikeout name + handicap; no single K market id is hardcoded.
- Same-line two-way prices are devigged per book, then averaged into a retail no-vig consensus. A single retail reference is WATCH, not VERIFIED.
- K market freshness uses the underlying OddsPapi selection `changedAt` timestamps when available, not merely HTTP fetch completion time.
- Independent expected K remains upstream. OddsPapi only supplies target lines/prices after the model distribution exists.
- If the tournament feed returns zero starter-K markets for a verified pregame fixture, service 2.3.2 performs one unfiltered `/v4/odds?fixtureId=...` fallback for that fixture.
- The fallback does not send a bookmaker filter, because an absent requested slug can zero the whole fixture response.
- K catalogue discovery does not require a specific `marketType`; it requires baseball sportId, playerProp=true, strikeout market name, numeric handicap, and Over/Under outcomes.

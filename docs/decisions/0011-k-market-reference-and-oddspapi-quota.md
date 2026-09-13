# Decision 0011 — K market reference and OddsPapi quota protection

Installed: 2026-09-07T02:01:15Z

## Hard account constraint
- OddsPapi plan: free, 250 requests/month.
- Player props are not included.
- Production code must not spend OddsPapi quota probing player-prop endpoints.

## K ownership
- Expected-K distribution remains independent of the target K line/price.
- PropsMadness supplies the current K line and local sportsbook price only after the distribution is built.
- Two-sided local prices are devigged into a local no-vig reference.
- A one-sided local price can produce EV for the available side but cannot produce no-vig edge; it is capped at WATCH if otherwise interesting.
- K rows using PropsMadness market truth cannot become VERIFIED from the market-reference layer alone; single-source local reference remains WATCH.

## OddsPapi ownership
- OddsPapi is reserved for supported MLB game markets.
- Default full-slate game-market books remain Pinnacle, Circa, and FanDuel unless the user's config already specifies another moneyline set.
- No K market catalogue request.
- No fixture-level player-prop discovery request.
- No retail player-prop bookmaker requests.

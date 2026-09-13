# Decision 0008 — Target K market separation

Installed: 2026-09-06T21:47:32Z

The expected-K distribution must not consume the target strikeout line or target strikeout price.

Production expected-K inputs:
- PropsMadness table API: Pitcher Outs / ER / Hits Allowed / Walks current lines + recent/season history; K recent/season history may contribute when present, but the current K line and K odds have weight 0
- MLB Stats API: gamePk, official starter identity, official nine-man batting order
- Baseball Savant: starter + exact nine hitters K%, Whiff%, Swing%/derived SwStr%, Contact%
- PropsMadness opponent rankings: ordinal diagnostic context only

Target-market evaluation:
- OddsPapi official-starter K markets are joined after expected K exists
- the same expected-K distribution is evaluated independently at each verified OddsPapi K line
- Trust Layer then applies identity, freshness, sharp-consensus, anomaly, edge and EV gates
- local PropsMadness K line/price is diagnostic only and cannot move expected K

The lineage is \ and remains \ until forward validation explicitly promotes it.

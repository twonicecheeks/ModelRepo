# MODEL 3.0.1 — Matchup Detail Panels

- Extension: **3.0.1**
- Trust: **3.0.0** unchanged
- Matchup Center: **1.1.0**
- Slate Radar: **1.6** unchanged
- RCE: **RCE-0.5** unchanged
- MLB Public Research provider: **0.5.0** unchanged
- NFL Public Research provider: **0.2.0**
- Local service: **2.3.7** (read-only OMEGA bridge added; OddsPapi game-market behavior unchanged)

## Matchup detail additions

MLB cards now expand to show game outlook, Trust and market movement, both starting pitchers, K context, offense/recent form, bullpen context, research support/opposition, independent ML projection, sourced material news, and a bottom-line diagnostic.

NFL cards now fetch ESPN game-summary detail in addition to the weekly scoreboard, showing named injury/availability rows, QB-specific context, weather/venue, public market context, sourced research, and the existing OMEGA tackle model when the local prospective ledgers are available.

## OMEGA boundary

The local service exposes `/v1/nfl/omega/current` as a **read-only** bridge over the existing OMEGA prospective tackle probability and market-comparison ledgers. It performs **0 OddsPapi requests**, does not rebuild OMEGA, and does not let public research alter OMEGA probabilities or actionability. Matchup Center does not invent an NFL game-side win model.

MLB K/ML probability math, model lineages, and Trust thresholds are unchanged.

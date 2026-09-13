# MODEL 3.2.0 — Personnel & Matchup Impact checkpoint

- Chrome extension: **3.2.0**
- Matchup Center: **1.4.0**
- Matchup Intelligence: **0.2.0**
- Slate Radar: **1.7**
- Data Pipeline: **1.13.0**
- NFL Public Research: **0.4.0**
- Local service: **2.3.7 unchanged**

## New non-mutating intelligence

### MLB
The Radar now persists compact lineup snapshots. The pipeline captures the last pre-official-lineup baseline when official orders begin posting. Matchup Center compares the current official lineup with that baseline and can show:
- proxy hitters added/removed versus the official order,
- offense-rating movement,
- projected-runs movement,
- selected-side probability movement.

The baseline is audit metadata only. It never feeds back into the model.

### NFL
NFL public research fetches ESPN team depth charts only for teams with structured injury rows. Injuries are enriched with depth-chart rank/role, then weighted by status × role × position importance. Matchup Intelligence can surface personnel pressure points by unit (OL/pass rush, receiver/coverage, secondary/passing game, front seven/run game, etc.).

This remains public-context intelligence only. It does not create an NFL game-side MODEL probability and does not mutate OMEGA.

## Frozen boundaries
- MLB Structured K math unchanged.
- MLB Structured ML math unchanged.
- Trust core / thresholds unchanged.
- Existing NFL model tree unchanged.
- Local service 2.3.7 unchanged.
- Installer OddsPapi requests: 0.

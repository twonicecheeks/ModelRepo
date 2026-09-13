# MODEL 3.0.0 — Matchup Center

- Extension/Trust: **3.0.0**
- Matchup Center: **1.0.0**
- Slate Radar: **1.6**
- RCE: **RCE-0.5**
- MLB Public Research provider: **0.5.0**
- NFL Public Research provider: **0.1.1**
- Local service: **2.3.6** unchanged

## Matchup Center
The Workspace now includes a persistent per-game matchup panel with MLB/NFL toggle. MLB cards assemble current starter, Trust, moneyline, K, recent-form, external-projection, and sourced RCE context. NFL cards use the public ESPN weekly scoreboard plus freshness-aware Google News research. NFL Matchup Center is research-only and does not mutate or silently import OMEGA/NFL model probabilities.

MLB K/ML probability math and Trust thresholds are unchanged.

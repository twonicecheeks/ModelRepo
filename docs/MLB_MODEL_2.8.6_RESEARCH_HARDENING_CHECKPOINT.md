# MLB MODEL 2.8.6 — Research Hardening checkpoint

Prepared: 2026-09-12

## Versions

- Chrome extension: 2.8.6 Research Hardening
- Local market service: 2.3.6 (unchanged)
- Data Pipeline: 1.12.0
- Slate Radar: 1.4
- Research Confirmation Engine: RCE-0.3
- Public Research provider: 0.3.0
- Structured K: 1.4 / lineage `mlb-k-v0.8.3-sample-shrinkage-workload-2026-09-07`
- Structured ML: 1.3 / lineage `mlb-moneyline-v0.8.0-offense-strength-2026-09-06`

## 2.8.6 changes

1. `SYNC + BUILD K + ML + TRUST` auto-rebuilds Trust from `/v1/markets/latest` with 0 new OddsPapi requests. Fresh game-market calls remain explicit.
2. Trust persistence keeps the prior materially distinct market signature so repeated identical rebuilds do not erase useful market-movement baselines.
3. Radar separates wagering state from research: **BET STATUS / WHY**, **MODEL THESIS**, and **RESEARCH CONFIDENCE** are distinct.
4. WATCH/BLOCKED reasons are shown directly in the expanded explanation.
5. Strongest supporting/opposing RCE signals are highlighted.
6. Public headlines/transactions are distilled into bounded **MATERIAL FINDINGS** and a neutral/review impact.
7. ML independent projections display selected-side model probability, external probability, delta in percentage points, and agreement/conflict assessment.
8. K/ML prediction math, Trust thresholds, lineages, service 2.3.6, and OddsPapi plan policy are unchanged. Research remains non-mutating.

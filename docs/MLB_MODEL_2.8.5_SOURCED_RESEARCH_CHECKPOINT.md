# MLB MODEL 2.8.5 — Sourced Research checkpoint

**Checkpoint date:** 2026-09-12  
**Status:** prepared source; local/synthetic validation required before packaging; live Mac/provider verification still required.

## Versions

- Chrome extension: 2.8.5 Sourced Research
- Local market service: 2.3.6 (unchanged)
- Data Pipeline: 1.11.0
- Structured K: 1.4
- Structured ML: 1.3
- Slate Radar: 1.3
- Research Confirmation Engine: RCE-0.2
- Public Research provider: 0.2.0
- Workspace shell: 1.0

## What 2.8.5 adds

1. Keeps 2.8.4 model-component explanations and Recent Form HOT / AVERAGE / COLD.
2. Adds recent MLB StatsAPI transactions as sourced roster/workload context.
3. Adds Google News RSS research for the highest-ranked ML/K opportunities, with headline classification for injury, scratch, workload, role change, transaction, lineup, weather and velocity signals.
4. Adds `NEWS HOLD — REVIEW` for K opportunities when sourced evidence indicates a material current-status risk. The hold is display/research only; Trust and probability are unchanged.
5. Adds numberFire daily MLB win probabilities from FanDuel Research as an independent ML projection benchmark when available.
6. Adds explicit independent-projection agreement/disagreement. Opposite-side disagreement with >=12pp gap is `CONFLICT`; smaller opposite-side disagreement is at least `MIXED`.
7. Adds a research-only refresh path. It does not refresh model math, sportsbook markets, or OddsPapi.

## Non-mutation contract

The following remain frozen in 2.8.5:

- K and ML coefficients/formulas
- K/ML model lineages
- Trust thresholds and status rules
- target K market weight = 0
- OddsPapi player-prop requests = 0
- local service = 2.3.6

Sourced research is an audit layer only. It may change the **research verdict/display bucket**, never the underlying probability or Trust state.

## Provider boundaries

- MLB StatsAPI: structured public transaction facts.
- Google News RSS: public headline discovery only; article bodies are not treated as numeric model inputs.
- numberFire / FanDuel Research: independent ML probability benchmark only.
- K numeric external projection: not connected in Public Research 0.2.0.

## Live-verification requirement

Container/synthetic tests cannot prove that Google News RSS or the FanDuel Research page is reachable from the user's Chrome environment on a future date. After installing/reloading the extension on the Mac, run `SYNC + BUILD K + ML` or `REFRESH RESEARCH` and confirm the Public Research status in Workspace. Failures must degrade to PARTIAL/ERROR without changing model probabilities.

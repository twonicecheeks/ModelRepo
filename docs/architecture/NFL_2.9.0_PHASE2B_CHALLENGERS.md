# MODEL NFL 2.9.0 — Phase 2B Dynamic Challenger Research

Status: **development research only; 2025 holdout sealed; no production probability.**

Phase 2B implements the immediate lessons from the NFL modeling research without inventing unsupported weights.

## Implemented now

1. **Team L2 logistic baseline** remains the Phase 2A interpretable full-feature model.
2. **Passing-core sparse challenger** tests whether a smaller passing-centric signal set generalizes better than the broad team feature family.
3. **Margin ridge challenger** predicts expected home margin, estimates training residual dispersion, and maps expected margin to win probability with a Normal residual CDF.
4. **Online Elo challenger** remains deliberately simple and hard to overfit.
5. **Constrained logit ensemble** stacks challenger logits with nonnegative weights constrained to sum to one. Ensemble evaluation is chronological: weights for each reported season are fit only from earlier out-of-fold seasons.
6. **Empirical persistence audit** estimates lag-1 stability for each PBP-derived team metric using data through 2024 only. Turnover/takeaway persistence receives an explicit noise guard. These persistence estimates are diagnostic in Phase 2B; they do not silently mutate probabilities.
7. **Internal model disagreement** is computed as a future Trust/uncertainty primitive.
8. **QB layer is DATA_GATED.** The current `qb_roster_weekly.csv` is an identity scaffold, not verified starter-QB history. Phase 2B refuses to manufacture QB weights from roster presence or arbitrary positional percentages.

## Mathematical contracts

Direct model: `P(home win)=logistic(beta0 + X beta)` with standardized L2 regularization selected chronologically.

Passing-core model: same family, but only passing offense/defense, CPOE, sack and explosive-pass features across prior-season/current/last-4/last-8 horizons plus rest/neutral context.

Margin model: `M = gamma0 + X gamma + e`; residual sigma is estimated on training games; `P(home win)=Phi(E[M]/sigma)`.

Ensemble: `logit(p_final)=alpha + sum(w_m logit(p_m))`, with `w_m >= 0` and `sum(w_m)=1`.

## Explicitly not implemented yet

- historical verified starting-QB resolver / QB state model
- roster/snap continuity features for OL/WR/defense
- offseason Week-1 transition model
- live injury/inactive adapter
- weather/travel effects
- market residual lab
- 2025 holdout evaluation
- 2026 production runtime

Those are subsequent gates, not placeholders to be filled with intuition.

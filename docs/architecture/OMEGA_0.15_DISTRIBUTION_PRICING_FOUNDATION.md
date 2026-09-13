# OMEGA 0.15 — Distribution & Pricing Foundation

## Objective

OMEGA 0.13.1 validated the independent mean-count model on the sealed 2025 holdout. OMEGA 0.15 addresses the next distinct problem: a mean count is not a bet probability.

The required chain is now:

`football state -> OMEGA-I mean xTC -> discrete count distribution -> P(T+A > line) -> fair price -> downstream posted-price/market comparison`

The sportsbook market remains outside the independent prediction path.

## Cumulative release

The user did not install OMEGA 0.14. Therefore 0.15 includes the complete 0.14 post-holdout production gate:

- permanent STRONG_PASS seal,
- raw pregame availability/role contract,
- fail-closed snapshot audit,
- offline live-source inventory.

No separate 0.14 installation is required.

## Distribution doctrine

The educational spreadsheet that motivated this phase correctly separates a projection from a probability and demonstrates how distributional shape can flip a wager decision. OMEGA adopts that doctrine, but not its yardage-specific distribution assumptions.

T+A is a nonnegative integer count. OMEGA therefore tests discrete count models:

1. `POISSON` — no free dispersion parameter, variance = mean.
2. `NB_GLOBAL` — NB2 with one global size parameter, variance = mean + mean² / size.
3. `NB_ROLE` — the same NB2 family, but dispersion can vary by H012 **predicted** exposure tier.

Exposure tiers are fixed before research:

- LOW: predicted snap share < 0.35
- ROTATIONAL: 0.35 to < 0.65
- STARTER: 0.65 to < 0.85
- EVERY_DOWN: >= 0.85

Only H012 predicted snap share defines the tier. Target-game realized snap magnitude is forbidden.

## Selection protocol

- Frozen H008+H012 xTC mean: unchanged.
- Reconstruct strictly-lagged H008 means for 2018–2023.
- Candidate selection folds: 2021, 2022, 2023.
- Each fold fits distribution parameters using only earlier reconstructed seasons.
- Primary score: count negative log likelihood.
- Secondary score: average Brier score across over thresholds 0.5 through 14.5.
- NLL tie tolerance: 0.001 per observation.
- Within the tie tolerance, choose lower threshold Brier; remaining tie goes to the simpler architecture.
- 2024 is confirmation only and cannot change the selected architecture.
- 2025 outcomes are forbidden from fitting, architecture choice, thresholds, rescue analysis or subgroup selection.
- 2026 is the prospective probability/market validation regime.

The final research parameters may be refit through 2024 only after the architecture has been selected. This mirrors the frozen mean-model practice: architecture/hyperparameter choice and final pre-prospective coefficient estimation are separate steps.

## Full-ladder pricing

A single fitted PMF prices every half-point threshold coherently:

- 4.5 -> P(T+A >= 5)
- 5.5 -> P(T+A >= 6)
- 6.5 -> P(T+A >= 7)
- etc.

No separate projection is fit for each alternate line.

The included `price_omega_tackle_ladder_015.command` is research-only. It converts an independent xTC mean and H012 predicted snap share into fair over/under probabilities and American prices.

## Posted price versus market opinion

The release also includes a manual downstream comparison utility. It preserves two separate questions:

1. **Mechanical bet math:** compare OMEGA probability with the break-even probability of the executable posted price and compute expected ROI.
2. **Market sanity check:** de-vig a two-sided market proportionally and compare the independent OMEGA probability with the market's no-vig probability.

The second number must never enter OMEGA-I. A large disagreement triggers investigation; it is not automatically interpreted as a large edge.

## What 0.15 still does not establish

- No sportsbook settlement equivalence.
- No authoritative live active/inactive/depth source yet.
- No prospective 2026 probability calibration yet.
- No CLV evidence.
- No VERIFIED prop Trust.

The distribution output is explicitly labeled `RESEARCH_ONLY_PROSPECTIVE_2026_VALIDATION_REQUIRED`.

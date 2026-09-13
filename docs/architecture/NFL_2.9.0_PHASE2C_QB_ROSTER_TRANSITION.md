# MODEL NFL 2.9.0 Phase 2C — QB State / Roster Continuity / Transition Research

Status: **HISTORICAL DEVELOPMENT CHALLENGER ONLY**. The 2025 holdout remains unopened and no 2026 production probability is emitted.

## Purpose

Phase 2C tests whether explicit quarterback state and personnel continuity add stable probabilistic signal beyond the Phase 2A team-efficiency model. It does not assign subjective QB point values or position weights. Every candidate coefficient is learned from historical development data under chronological validation.

## Historical source contract

Phase 2C reuses the immutable Phase 1 nflverse schedules, weekly rosters, players and play-by-play snapshot. The explicit context build adds nflverse/PFR game-level snap-count files for 2015–2024 only. These supplemental bytes are stored in the existing SHA256 content-addressed raw store and described by an immutable supplemental `SOURCE_MANIFEST.json`.

The context builder never opens 2025 PBP, 2025 weekly-roster files, or 2025 snap counts. OddsPapi requests are zero and sportsbook fields are disallowed.

## QB research state

For each team-game, Phase 2C derives postgame QB observations from attributed `passer_player_id` dropbacks. Current-game observations are **never** used in that same game's pregame features. Observed QB history is strictly lagged.

The research QB proxy uses the previous observed primary QB when that QB appears on the target week's active roster. If that incumbent is not active and exactly one active QB is present, the single QB is used as a replacement proxy. Multiple-QB changes remain unresolved. This is deliberately called a **proxy**, not verified starter identity.

QB histories are dropback-weighted and include prior-season, last-4 and last-8 windows for EPA/dropback, CPOE, sack rate, explosive-pass rate and interception rate. Sample size is represented by games and log dropbacks. Week-1 continuity/change indicators are explicit.

## Roster continuity research

For each target game, snap-weighted continuity compares the previous observed game’s participants with the target week’s active-roster membership. Separate features are kept for overall offense, offensive line, skill positions, defense and unweighted active-roster return rate. Week 1 uses the previous season’s last observed game as the snap-share baseline.

**Source-timing gate:** nflverse exposes week-level historical rosters, but this release does not claim that each historical weekly-roster row has an independently verified exact pre-kickoff archival timestamp. Therefore target-week roster membership is accepted only as a development-research proxy. No QB/roster feature can be frozen for production until this provenance is resolved or replaced with a timestamp-verifiable source.

## Model comparison discipline

The previously reviewed Phase 2A report is the exact baseline. Phase 2C does not refit or approximate that score.

Three challengers are evaluated:

- team + QB context
- team + roster continuity
- team + QB + roster continuity

Each challenger independently selects its L2 penalty on chronological 2020–2021 folds from a predeclared grid. Final comparison is made only on the exact same 2022–2024 evaluation games used by Phase 2A. Missing values are imputed and standardized from the training fold only and paired with explicit missingness features.

The Phase 2C logistic objective is

`mean[-y log(p) - (1-y) log(1-p)] + 0.5 * lambda * ||beta||^2`

with an unpenalized intercept. The vectorized solver uses damped Newton/IRLS with deterministic backtracking line search. NumPy is pinned in MODEL's isolated NFL Python environment; it is not installed globally by the release installer.

A challenger is considered statistically interesting only when it improves both Brier score and log loss versus the exact Phase 2A baseline. Even then, the result remains research-only while the roster-timing and verified-starter gates remain open.

## Outputs

Context:

- `qb_game_history.csv`
- `qb_pregame_context.csv`
- `roster_continuity_context.csv`
- `phase2c_features.csv`
- `PHASE2C_CONTEXT_AUDIT.json`
- `PHASE2C_CONTEXT_AUDIT.md`

Model:

- `PHASE2C_SPEC.json`
- `PHASE2C_SPEC.sha256`
- `PHASE2C_BAKEOFF.json`
- `PHASE2C_BAKEOFF.md`

## Non-negotiable next gate

Do not evaluate 2025 from Phase 2C automatically. First inspect the 2022–2024 paired results, especially the weak 2023 development fold, verify roster/QB source timing, and decide which feature families survive. Only a separately guarded freeze/holdout release may open 2025.

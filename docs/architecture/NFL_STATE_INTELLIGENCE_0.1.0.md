# NFL State Intelligence 0.1.0 — DEN@KC M01-M88 Integration

Status: **research infrastructure only; coefficient-free; frozen Week 2 OMEGA unchanged.**

Source learning event: DEN @ KC, 2026-09-14. The live drive-by-drive analysis produced the M01-M88 ledger. The central principle is:

> The final score is an outcome. The model should learn the sequence of states and decisions that made the outcome probable.

## Governance boundary

This work MUST NOT mutate the frozen Week 2 NFL OMEGA T+A forecasts, CONTROL probabilities, role-shadow probabilities, freeze manifests, or prospective market snapshots. New DEN@KC logic enters only as downstream/research infrastructure and must earn promotion through historical leakage-safe testing and later prospective validation.

`packages/models/nfl/game/nuance_registry.py` is the canonical machine-readable M01-M88 index. Registration means the hypothesis is preserved, not that a coefficient or production effect has been accepted.

Source status counts are locked to the analysis ledger:

- CORE: 70
- BACKTEST: 15
- WATCH: 1
- IMPLEMENT: 1
- EXTERNAL DATA: 1

Evidence discipline from the source ledger remains mandatory:

- **CONFIRMED** — structured play-by-play / final-stat evidence.
- **LIVE OBSERVATION** — broadcast/viewer observation captured during the game; must be verified before becoming a ground-truth training label.
- **HYPOTHESIS** — model-development inference requiring backtest and/or film/charting validation.

## Architecture

The shared causal sequence is:

`pre-snap state -> play caller chooses concept -> defense responds -> protection/routes develop -> QB reads/decides -> pass/scramble/sack or designed run -> receiver/YAC/tackle outcome -> new state -> coordinator adaptation -> repeat`

The State Intelligence layer exists below game, QB and player-prop challengers so they do not independently reconstruct incompatible football states.

### 1. State-transition offense

Every snap should eventually expose down, distance, field position, score, clock, win-probability state, personnel, formation, coverage/front, recent drive state, disruption state and matchup context. Models then predict both the branch chosen and the resulting state transition.

### 2. Volume and efficiency are separate

QB attempts are driven by possessions, pace, game state and caller preference. QB efficiency is driven by protection, pressure opportunity, coverage, receiver separation, decision quality and YAC. They should be modeled separately before recombination.

### 3. Play-caller layer

The eventual caller model must track actual caller identity, situational fingerprint, adaptation speed, halftime change, use of discovered matchup edges, caller x QB fit, offensive-caller x defensive-caller interaction, success-weighted concept reuse and counterfactual play-call value. Static coach grades are not a substitute.

### 4. Attribution layer

Box-score ownership is not causal ownership. Future layers should decompose outcomes among QB, protection, receiver, scheme, defensive coverage, tackling, penalties/operations, turnover return and luck. Passing yards should ultimately be decomposed through routes -> targets -> catch probability -> yards at catch -> YAC.

### 5. Data-state hygiene

Competitive, closeout, comeback-forced, end-half, victory-formation and terminal states must be labeled separately. Kneels are excluded from normal football tendency while remaining available to a separate sportsbook-settlement layer when official scoring requires them.

## Executable 0.1.0 primitives

`packages/models/nfl/game/state_intelligence.py` implements deterministic primitives only; no weights are fitted.

Direct primitives now exist for:

- **M01 / M39** — designed run vs dropback intent; scrambles and sacks remain dropback-origin plays.
- **M19** — third-down distance environment.
- **M27** — explicit disruption labels for sacks, penalties, TFL, turnovers, fumbles, aborted plays and QB hits when fields are available.
- **M29 / M64 / M69 / M76 foundation** — field-position state including backed-up, own territory, midfield, plus territory, red zone and goal-to-go.
- **M34** — functional completion vs short-of-sticks completion.
- **M37** — first-down generation source.
- **M04 / M05 / M07 foundation** — coefficient-free structural pressure-opportunity bucket from pre-snap down/distance. This is a proxy to be calibrated, not observed pressure.
- **M68** — sudden-change offense following a turnover/possession change.
- **M77-M80 foundation** — competitive-state/closeout candidate hygiene when win probability is supplied.
- **M83** — provisional ruling marker hook; live pipelines must not finalize unresolved replay state.
- **M86 / M87** — kneel separation from football tendency while preserving an official-stat settlement marker.
- **M88 foundation** — terminal-state exclusion hook.

0.1.0 deliberately does **not** alter `historical_feature_core.py`, existing fitted/frozen artifacts, OMEGA Week 2, or any market pipeline.

## Research roadmap inherited from the ledger

### Phase 1 — standard play-by-play

Implement and backtest M01/M02 designed-play normalization; M04/M19 down-distance state engine; M22 game-script elasticity; M27 disruption; M31 QB volume vs efficiency; M37 first-down source; M59 fourth-down state; M64-M71 turnover/state value; M77-M80 closeout classification; M83 ruling finalization; M86-M88 kneel/terminal cleanup.

### Phase 2 — richer public tracking/charting

Add M05/M06 pressure opportunity/suppression; M08-M10 leverage/coverage target share; M21/M24 shell/personnel state; M34/M35 functional completion and tackling; M41/M48-M50 air/YAC/explosive attribution; M49 missed-tackle probability.

### Phase 3 — play caller/coordinator

Add M14 and M42-M47 caller identity/fingerprint/adaptation/matchup; M53/M54 success-weighted and counterfactual selection; M56-M60 substitution-denial tempo, personnel deception, fourth-down concept and halftime adjustment delta.

### Phase 4 — operations, health and live intelligence

Add M11-M18 injury/health/rotation; M33 operation continuity; M38 timestamped broadcast/transcript intelligence with verification; M61-M63 drops/operational-error attribution; M72-M76 pressure ball security and penalty interaction.

### Phase 5 — player-prop settlement

Add M79 late-game RB redistribution; M84 starter exposure; M85 clock-burn efficiency; M86 football-performance kneel removal; M87 official-stat settlement re-addition where required.

## Immediate engineering gates after 0.1.0

1. Build a richer nflverse normalized snap snapshot from the immutable raw source blobs. Do not broaden the old Phase 1B normalized schema in place.
2. Run the 0.1.0 state engine over historical seasons with immutable output/audit manifests.
3. Quantify state frequencies and schema coverage before fitting anything.
4. Create a state-transition challenger that predicts next-state/drive-continuation components without market inputs.
5. Validate the M04 -> M19 -> pressure-exposure mechanism historically rather than merely adding correlated columns to a regression.
6. Build QB volume and QB efficiency challengers separately, then test recombination.
7. Add the caller layer only after caller identity/provenance is reliable.
8. Keep 2025 holdout and 2026 prospective leakage contracts intact.

## Non-negotiable interpretation rule

A high-value idea from one game is a **research hypothesis**, not a discovered coefficient. The DEN@KC analysis changes what we measure and how we structure the problem; it does not authorize fitting Week 2 outcomes back into frozen Week 2 predictions.

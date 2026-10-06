# Canonical MODEL Repository Structure

```
MODEL/
├── apps/
│   └── chrome-extension/
│       └── src/                 # ONLY unpacked extension Chrome should load
├── services/
│   └── market-service/
│       └── src/                 # OddsPapi/local service source
├── packages/
│   ├── core/                    # sport-agnostic identity/trust/edge logic
│   ├── providers/
│   │   ├── propsmadness/        # PropsMadness ingestion adapters
│   │   ├── oddspapi/            # OddsPapi normalization/adapters
│   │   └── nflverse/            # NFL historical/provider contract (2.9.0 research)
│   └── models/
│       ├── mlb/
│       ├── nfl/
│       └── cfb/
├── data/
│   ├── raw/                     # ignored; immutable captures
│   ├── normalized/              # normalized snapshots
│   └── fixtures/                # small committed test fixtures
├── docs/
│   ├── architecture/
│   ├── audits/
│   └── decisions/
├── tests/
├── scripts/
├── omega_delta/              # self-contained OMEGA + DELTA 0.1.3 release
├── releases/                    # packaged release artifacts only
├── logs/                        # ignored runtime logs
├── tmp/                         # ignored temporary work
└── archive/                     # old clean-root versions, not active source
```

## Rules

1. Chrome loads exactly one path: `apps/chrome-extension/src`.
2. Never develop from Downloads, Desktop, or a version-numbered release folder.
3. Release ZIPs belong only in `releases/`.
4. Old source copies belong only in `archive/`; never beside active source.
5. Runtime/API secrets never live in the extension source tree.
6. Raw provider captures are immutable and timestamped.
7. Models consume normalized snapshots, not provider-specific DOM objects.
8. PropsMadness and OddsPapi are providers; neither is allowed to overwrite the other.
9. MLB/NFL/CFB model code stays inside its own model package.
10. Shared trust/edge/event identity logic is sport-agnostic.

11. NFL historical training data must be leakage-safe: current/future outcomes and sportsbook fields never enter independent features.
12. NFL 2025 is the untouched holdout and 2026 is prospective until the NFL model is frozen.
13. `omega_delta/` is the versioned, runnable MLB postseason release; its frozen audits and source receipts travel with the code.

## NFL 2.9.0 Phase 1B research data

- `packages/providers/nflverse/src/snapshot.py` — immutable SHA256 source snapshots
- `packages/providers/nflverse/src/normalize.py` — deterministic normalization + coverage audit
- `scripts/nfl/build_phase1_snapshot.command` — explicit networked nflverse snapshot build; OddsPapi 0
- `scripts/nfl/audit_phase1b_snapshot.command` — local/synthetic Phase 1B integrity audit
- `data/raw/nfl/nflverse/` — generated content-addressed raw source store
- `data/normalized/nfl/phase1/` — generated immutable normalized snapshots

## NFL 2.9.0 Phase 2A historical model research

- `packages/models/nfl/game/research_model.py` — deterministic development-only L2 logistic + baselines
- `scripts/nfl/build_phase2_development.command` — consumes the current normalized Phase 1 snapshot; OddsPapi 0
- `scripts/nfl/audit_phase2_model.command` — verifies holdout/market/runtime boundaries
- `data/models/nfl/phase2a/` — generated immutable candidate specs and development validation reports
- 2025 holdout evaluation is intentionally **not** implemented in Phase 2A; review development metrics first.

## NFL 2.9.0 Phase 2B additions
- `packages/models/nfl/game/challenger_models.py` — sparse passing challenger, margin model, constrained ensemble, disagreement metric
- `packages/models/nfl/game/persistence.py` — empirical metric persistence audit
- `scripts/nfl/build_phase2b_challengers.py` — chronological challenger bake-off; 2025 sealed
- `scripts/nfl/build_phase2b_challengers.command`
- `scripts/nfl/audit_phase2b_challengers.command`
- `docs/architecture/NFL_2.9.0_PHASE2B_CHALLENGERS.md`

## NFL 2.9.0 Phase 2C additions
- `packages/models/nfl/game/phase2c_context.py` — strictly lagged observed-QB history and snap-weighted roster continuity research primitives
- `packages/models/nfl/game/phase2c_model.py` — QB/roster feature vectorization plus deterministic NumPy-backed L2 logistic challenger fitter
- `scripts/nfl/build_phase2c_context.command` — explicit supplemental nflverse snap-count acquisition for 2015–2024 and immutable context normalization; 2025 unopened
- `scripts/nfl/build_phase2c_model.command` — 2020–2021 hyperparameter selection, exact paired 2022–2024 challenger evaluation against the existing Phase 2A baseline
- `scripts/nfl/audit_phase2c.command` — local integrity regression audit; no network
- `requirements/nfl-phase2c.txt` — isolated NumPy pin for vectorized research fitting
- `data/raw/nfl/nflverse/phase2c_context/` — generated immutable supplemental snap-count source snapshots
- `data/normalized/nfl/phase2c_context/` — generated QB/roster context snapshots
- `data/models/nfl/phase2c/` — generated Phase 2C bake-off/spec artifacts
- Phase 2C is **research only**. nflverse week-level roster state is not yet claimed to have an exact archived pre-kickoff timestamp; that provenance is an explicit gate before any feature freeze.

## OMEGA DELTA 0.1.3 release

- `omega_delta/README.md` — Mac launch instructions and model boundaries.
- `omega_delta/app/` — runnable OMEGA persistence and DELTA integration; `delta_model.py` remains the frozen scored engine.
- `omega_delta/tools/` — source preparation, chronological replay, platoon/arsenal research, hazard/residual trainers, prospective freeze audit, and market benchmarking.
- `omega_delta/audit/` — frozen parameters, 775-start development predictions, prospective 2026 freeze, replay reports and verification logs.
- `omega_delta/seed/` — the complete normalized MLB replay inputs and outcome ledger used by the release.
- `omega_delta/research_sources/` — public-source research scripts, provider adapters, attribution notes and the bundled offline cache.
- `omega_delta/DELTA_RESEARCH_0.1.3.md` and `omega_delta/DELTA_MARKET_BACKTEST.md` — research contracts and historical market-line audit instructions.

The DELTA package is deliberately self-contained so a clone can reproduce the
release without depending on files outside this repository. It contains no
credentials or authenticated sportsbook data. Advanced research layers remain
unpromoted until timestamped historical fitting and prospective scoring support
them.

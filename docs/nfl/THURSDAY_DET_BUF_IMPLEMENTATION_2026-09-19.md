# DET-BUF Thursday Findings — Implementation Map

Date implemented: 2026-09-19  
Source discovery game: 2026 Week 2 DET @ BUF  
Architecture rule: Thursday's result is diagnostic evidence only. Frozen OMEGA/QB forecasts are not retroactively mutated or refit.

## What changed

### State Intelligence 0.1.5 — Thursday interaction research

New module: `packages/models/nfl/game/thursday_interaction_research_015.py`

The module turns the drive-ledger findings into historical, leakage-safe diagnostics using the existing immutable nflverse State Intelligence snapshots. The default runner admits 2016-2024 only; 2025 remains sealed and 2026 prospective data is excluded.

Implemented PBP-supported mechanisms:

| Ledger finding | Implementation |
| --- | --- |
| M03 / M26 pressure can fail against a mobile QB | Sack-vs-scramble outcome proxy and scramble rate per dropback. True rush-lane geometry remains a declared data gap. |
| M10 / M27 adaptive play calling | Drive-to-drive mechanism vector and total-variation shift across designed runs, designed passes and scrambles. |
| M14 defensive load | Cumulative opponent defensive snap-load before each drive, explicitly labeled a load proxy rather than physiological fatigue. |
| M16 catastrophic negative-play tax | Per-drive sacks, turnovers, fumbles and aborted-play count. |
| M18 field position | Drive-start `yardline_100` retained for field-position diagnostics. |
| M19 penalty leverage | Penalty rows retain observed EPA/WPA, red-zone/goal-to-go context, and erased-event flags. |
| M20 nullified impact | No-play parser preserves nullified INT, sack, fumble and 20+ yard events for diagnostics. |
| M22 / M24 offensive structure controls pressure exposure | Early-down designed-run success is compared descriptively with later high-structural-exposure dropback rate. |
| M25 / M28 explosive suppression / concentration | 20+ yard play count and explosive share of positive yards by drive. |
| M30 scoreboard changes play mix | Pass/run intent rates are stratified by pre-snap score differential. Scrambles and sacks remain pass-origin plays. |
| M31 QB rushing as drive survival | Scramble first downs and third/fourth-down scramble conversions are tracked separately from scramble yardage. |
| M32 response-drive efficiency | Drives immediately following an opponent scoring drive are marked and scored. |
| M34 run threat versus run production | Designed-run share and early-down run success are retained separately. |
| M35 adaptation after early pressure | Team offense dropback EPA before/through first sack versus after first sack. |
| M36 containment x explosive suppression | PBP proxy identifies drives with no late-down scramble conversion and no 20+ yard play, then records scoring rate. |

### Explicitly not fabricated from current PBP

The following Thursday findings require richer inputs and are emitted as `DATA_GAPS` rather than silently proxied as truth:

- true pressure geometry / rush-lane integrity,
- time to throw,
- receiver separation,
- coverage shell,
- designed-QB-run gravity versus RB rushing,
- receiver position / route location for TE-deep-middle interactions,
- player-specific tackler opportunity redistribution for OMEGA.

These should become separate data-source projects before entering a production challenger.

## OMEGA 0.35.0 — postgame market calibration

New module: `packages/models/nfl/game/omega_market_calibration_0350.py`

New scorer: `scripts/nfl/score_omega_market_calibration_0350.py`

The scorer consumes the immutable OMEGA 0.34.2 game-day market overlay plus the existing postgame nflverse T+A reconstruction. It grades, without refitting:

- control vs role-shadow hit rate,
- Brier score and log loss,
- realized flat-unit ROI at captured prices,
- probability calibration bins,
- EV bands including `EV_35_PLUS`,
- position-group results,
- role-state results,
- operational-status results,
- control/role side-agreement strata,
- clean executable role-aligned rows versus quarantined/reference/conflict rows.

No automatic EV compression or probability recalibration is permitted from a single game or small bucket. The `EV_35_PLUS` audit is explicitly `SAMPLE_INSUFFICIENT` until at least 50 graded selected-side rows accumulate.

## Commands

Historical Thursday interaction audit:

```zsh
zsh scripts/nfl/analyze_nfl_thursday_interactions_015.command
```

Postgame OMEGA calibration for a completed game:

```zsh
zsh scripts/nfl/score_omega_market_calibration_0350.command 2026_02_DET_BUF
```

The OMEGA command first runs the existing 0.25 results-readiness gate and refuses to score until the dedicated results snapshot marks the game complete.

## Promotion rule

Nothing in this patch changes a production coefficient. Supported State 0.1.5 mechanisms must first be converted into strictly lagged pregame features and beat the existing baseline in paired chronological challenger testing. Tracking-dependent findings must first obtain a valid data source. OMEGA calibration requires a multi-game prospective sample before any probability or EV calibration change.

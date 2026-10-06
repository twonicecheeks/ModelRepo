# MLB MODEL / NFL OMEGA PROJECT CHECKPOINT
**Date:** 2026-09-16  
**Purpose:** Paste/upload this file into the next ChatGPT thread so the new thread can continue immediately without re-deriving the current state.

---

## 1. PROJECT CONTEXT / CURRENT PRIORITY

This project is called **MLB MODEL**, but the current active development focus is the **NFL OMEGA tackles + assists model and market-tracking workflow**.

Repository:
- Local repo: `/Users/abbeyfelix/Developer/MODEL`
- GitHub: `twonicecheeks/ModelRepo`
- Main branch: `main`

The immediate objective is to run the already-frozen Week 2 NFL OMEGA T+A model prospectively, compare it against market/reference prices, track how the reference board changes through time, and eventually surface only meaningful market movement in the extension.

---

## 2. NON-NEGOTIABLE SCIENTIFIC / AUDIT RULES

These rules must continue to be respected in every future step.

### Frozen model
- **NFL OMEGA coefficients/features/distributions are frozen.**
- Do **not** change frozen OMEGA coefficients or refit the model during Week 2 prospective tracking.
- Any new logic must be downstream only: challengers, diagnostics, trust layers, movement tracking, identity hardening, market adapters, etc.
- Do not mutate or overwrite frozen forecast artifacts.

### Pregame / leakage
- All Week 2 model forecasts are frozen pregame.
- Pregame predictions, market snapshots, and decisions must remain immutable.
- Post-kickoff market data must never contaminate pregame comparison.
- Post-game outcomes are scored separately after the fact.

### Market truth / execution distinction
- PropsMadness `referenceBet` data is **reference-only** and **not executable**.
- Never represent a PropsMadness reference quote as a confirmed directly-bettable sportsbook price.
- Direct sportsbook confirmation is still required before any actual execution decision.
- No fabricated book prices, no guessed multibook prices, no interpolation between different lines.

### Identity
- Deterministic identity matching only.
- No fuzzy matching.
- Known explicit narrow aliases only.
- Unmatched players remain unmatched/quarantined rather than guessed.

### Availability / role
- Availability/inactives are distinct from conditional defensive snap share.
- No authoritative Week 2 inactive overlay is currently integrated.
- Role-shadow challenger remains diagnostic only.
- `BACKUP_CONFLICT` remains quarantined.
- `STARTER_CONFLICT` remains review-only.

---

## 3. FROZEN OMEGA MODEL STATE

Current Week 2 freeze:

- Freeze ID: `20260916T153110Z_3d61b710`
- Freeze path:
  `data/prospective/nfl/omega_week2_dual_track_0330/20260916T153110Z_3d61b710/`
- Manifest:
  `OMEGA_0.33_WEEK2_MANIFEST.json`
- Week 2 forecasts: **800**
- Games: **16**
- Week 2 outcomes in freeze: **0**
- Market fields in freeze: **0**
- OddsPapi requests for props: **0**

Trust/role-state counts in the frozen Week 2 board:
- `NO_DEPTH_FALLBACK_H012`: 5
- `REVIEW_BACKUP_CONFLICT`: 39
- `ROLE_ALIGNED`: 607
- `STARTER_CONFLICT_REVIEW`: 149

### Frozen decision tracks
1. **CONTROL** = frozen decision probability track.
2. **ROLE_POINT / role shadow** = research-only challenger.
3. Full snap mixture = research-only, not current decision track.
4. `STARTER_CONFLICT` = review warning.
5. `BACKUP_CONFLICT` = quarantine.

Do **not** imply that the role-point challenger replaced/promoted over CONTROL.

---

## 4. HISTORICAL ROLE-CHALLENGER WORK ALREADY COMPLETED

Historical work that should not be repeated:

### OMEGA 0.31.4
Confirmatory holdout testing on 2025 component-level holdout:
- H012 MAE: `0.14181`
- ROLE MAE: `0.13852`
- Strong bootstrap support for ROLE improvement.
- Backup conflicts stayed quarantined.

### OMEGA 0.32
Post-holdout point-to-T+A diagnostic:
- All rows: MAE `1.65709 → 1.64789`
- Starter-conflict slice worsened.
- Backup-conflict slice improved posthoc, but remains quarantined.
- This was directional research only.
- It did **not** promote ROLE probability to production.

---

## 5. PROPSMADNESS REFERENCE CAPTURE PIPELINE

### Direct Explore capture
Existing browser capture script:
`packages/providers/propsmadness/omega-nfl/omega_propsmadness_nfl_ta_direct_capture_0176.js`

Endpoints used:
- `/api/offer/nfl/explore/player-tackles-assists`
- `/api/offer/nfl/matches`

Importer:
`scripts/nfl/import_omega_propsmadness_nfl_ta_direct_01711.py`

Command:
```bash
zsh scripts/nfl/prepare_omega_propsmadness_nfl_ta_direct_0176.command
```

Then after the JSON downloads:
```bash
zsh scripts/nfl/import_omega_propsmadness_nfl_ta_direct_01711.command
```

Current direct Explore board characteristics:
- Offers: 149
- Normalized: 149
- Quarantine: 0
- Games: 16
- Teams: 32
- Two-sided: 145
- One-sided: 4
- Books observed in `referenceBet`: DraftKings, BetMGM, Props Builder, Underdog Fantasy
- All rows classified `REFERENCE_ONLY_NON_EXECUTABLE`

The raw market snapshot importer writes immutable snapshots under:
`data/raw/nfl/omega/market_snapshots/`

Current market pointer:
`data/raw/nfl/omega/CURRENT_MARKET_SNAPSHOT`

---

## 6. PROPSMADNESS MULTIBOOK INVESTIGATION — CLOSED FOR NOW

We reverse-engineered the player market endpoints.

For markets such as passing yards, the main comparison endpoint works:
`/api/players/{playerId}/match/{matchId}/bet-offers/{marketSlug}`

The alternate-line endpoint works for passing yards:
`/api/players/{playerId}/match/{matchId}/bet-offers/alt/{marketSlug}`

However, for **NFL Player Tackles + Assists**, the same routes do **not** currently expose usable multibook prices.

### OMEGA 0.36 diagnostic result
All 149 T+A player requests:
- HTTP 200: 149/149
- `bets[]` rows: 2,086
- Market slug: `player-tackles-assists`
- Rows with non-null line: **0**
- Rows with any odds: **0**

They are placeholder book rows only.

### OMEGA 0.36.2 route probe
Sampled 32 players, 2 per matchup:
- Generic player offers HTTP 200: 32
- Alt route HTTP 200: 32
- Generic T+A rows: 32
- Generic usable line+odds: **0**
- Generic offer types: `noOffer`
- Alt T+A rows: **0**
- Alt usable line+odds: **0**

Conclusion:
- PropsMadness currently exposes populated T+A pricing only through the Explore `referenceBet` layer.
- Do **not** spend more time trying to force the null multibook T+A endpoints unless PropsMadness changes later.
- OMEGA 0.36.2 should remain a capability probe that can be rerun later.

---

## 7. WEEK 2 DOWNSTREAM MARKET COMPARISON

Current comparison script:
`scripts/nfl/compare_omega_week2_dual_track_market_0341.py`

Current behavior:
- Reads frozen CONTROL and role-shadow tracks.
- Reads current immutable PropsMadness market snapshot.
- Uses deterministic identity matching.
- Excludes post-kickoff data.
- Computes probabilities/EV at exact half-lines.
- CONTROL remains decision track.
- ROLE remains shadow-only.
- All PropsMadness Explore reference rows remain:
  `REFERENCE_ONLY_NOT_EXECUTABLE`

Most recent comparison:
- Comparison rows: 146
- Two-sided: 142
- One-sided: 4
- Unmatched: 3
- Ambiguous: 0
- Unsupported: 0
- Post-kickoff excluded: 0

The 3 recurring unmatched identities:
- Henry To'oTo'o — HOU
- JuJu Brents — MIA
- Cam Bynum — IND

No fuzzy matching should be introduced for these.

---

## 8. OMEGA 0.35 VERIFICATION QUEUE

Already built:
`scripts/nfl/build_omega_week2_market_verification_queue_0350.py`

Successful queue:
- Queue ID: `20260916T162840Z_fd959391`
- Primary verify: 99
- Starter review: 13
- Backup quarantine: 6
- Track disagree: 0

Important:
- **99 primary verify rows are NOT 99 bets.**
- They are a triage queue for direct sportsbook checking.
- Direct sportsbook confirmation is still needed for execution.
- Reference-only market prices are research context only.

---

## 9. OMEGA 0.37 REFERENCE-MARKET MOVEMENT LEDGER

Built and working.

Script:
`scripts/nfl/build_omega_ta_reference_market_movement_0370.py`

Command:
```bash
zsh scripts/nfl/build_omega_ta_reference_market_movement_0370.command
```

Purpose:
- Track PropsMadness reference board over time.
- Preserve immutable chronology.
- Detect:
  - line changes
  - price-only changes
  - book changes
  - line + price changes
  - players added to board
  - players removed from board
- Recompute frozen CONTROL and role-shadow probabilities/EV at the **new exact line**
- Never mutate frozen model
- Never treat movement as proof of sharp money

Outputs:
- `OMEGA_0.37_REFERENCE_MARKET_OBSERVATIONS.csv`
- `OMEGA_0.37_REFERENCE_MARKET_TRANSITIONS.csv`
- `OMEGA_0.37_LATEST_MOVEMENT_BOARD.csv`
- `OMEGA_0.37_APPEARANCE_EVENTS.csv`
- `OMEGA_0.37_REFERENCE_MARKET_MOVEMENT_AUDIT.json`
- `OMEGA_OUTPUT_HASHES.json`

Current pointer:
`data/prospective/nfl/omega/CURRENT_OMEGA_TA_REFERENCE_MARKET_MOVEMENT`

### First baseline run
- Snapshots: 1
- Observations: 146
- Canonical players: 146
- Transitions: 0
- Changed: 0
- Unmatched: 3

### Second run
- Snapshots: 2
- Observations: 292
- Transitions: 146
- Changed: 0
- Unmatched: 6

### Current automated third run
- Snapshots: **3**
- Observations: **438**
- Canonical players: **146**
- Transitions: **292**
- Latest changed: **0**
- Adds/removals: **0**
- Unmatched: **9**
- Ambiguous: 0
- Unsupported: 0
- Post-kickoff: 0
- Model refits/writes: 0
- OddsPapi: 0

The unmatched count is simply the same 3 unresolved players across 3 snapshots.

No actual PropsMadness reference movement has been observed yet. This is a useful negative-control result: the movement ledger is not inventing moves.

---

## 10. OMEGA 0.37.1 — AUTOMATION NOW WORKING

This was the major final step completed in the current thread.

### What automation now does
The Chrome extension background process automatically captures the PropsMadness NFL T+A Explore board.

The Mac-side LaunchAgent detects the downloaded capture and automatically runs:

```text
0.17.11 import
    ↓
0.34.1 downstream comparison
    ↓
0.37 reference-market movement ledger rebuild
```

The pipeline hashes captures so the same file is not reprocessed as a fake new observation.

### Adaptive capture cadence
Current automation logic is designed to capture approximately:
- Every ~3 hours normally
- Hourly within 12 hours of next kickoff
- Every 30 minutes within 3 hours of kickoff
- Stops after the final Week 2 kickoff

### Extension controls
The MODEL extension now has OMEGA T+A automation controls:
- `OMEGA T+A AUTO`
- ON/OFF toggle
- `CAPTURE NOW`
- Last capture
- Next capture
- Week 2 stop state

### Installer
```bash
zsh scripts/nfl/install_omega_ta_auto_ingest_0371.command
```

After install, reload extension once at:
`chrome://extensions`

### Logs
Main automation log:
```bash
tail -f "$HOME/Library/Logs/MODEL/omega-ta-auto.log"
```

Error log:
```bash
tail -f "$HOME/Library/Logs/MODEL/omega-ta-auto.err.log"
```

`Ctrl-C` only stops `tail -f`; it does **not** stop automation.

### Confirmed end-to-end automated PASS
Most recent automated log:

```text
PASS snapshots 3 · observations 438 · canonical players 146 · transitions 292
PASS latest changed 0 · adds/removals 0 · unmatched 9 · ambiguous 0 · unsupported 0 · postkick 0
PASS reference-only/non-executable · frozen CONTROL unchanged · ROLE shadow-only · model refits/writes 0 · OddsPapi 0

OMEGA 0.37.1 AUTO INGEST · processing OMEGA_0176_PROPSMADNESS_NFL_TA_DIRECT_CAPTURE_20260916T181218434Z.json · sha b46737de447b
PASS automated capture imported and OMEGA 0.37 movement ledger rebuilt
```

That confirms the complete automated chain is working.

### Operational caveat
The capture side still depends on:
- Chrome being available/running
- MODEL extension being active
- PropsMadness session staying valid/logged in

The Mac LaunchAgent can process captures independently, but cannot create a browser capture if Chrome/session access is unavailable.

---

## 11. CURRENT EXTENSION / LOCAL SERVICE CONTEXT

Extension:
- `apps/chrome-extension/src/`
- Current manifest had been advanced to support the OMEGA automation work.
- PropsMadness host permission is already present.
- Local service runs on:
  `http://127.0.0.1:8765`

The existing local market service is primarily MLB/OddsPapi-oriented.
Do **not** route NFL T+A through OddsPapi because the current plan does not include player props.

OddsPapi plan constraint:
- Free plan
- 250 requests/month
- No player props
- Preserve quota for supported game markets.

---

## 12. CURRENT MODEL / MARKET INTERPRETATION

A large model/reference EV is **not** automatically a bet.

Example current high divergences from the latest board include names such as:
- Mansoor Delane UNDER 3.5 — starter conflict review
- Kendal Daniels UNDER 7.5
- Jacob Parrish UNDER 5.5 — starter conflict review
- Dee Winters UNDER 5.5
- Frankie Luvu UNDER 5.5
- Cody Barton UNDER 6.5
- Chris Johnson OVER 4.5
- Antonio Johnson UNDER 5.5
- Eric Murray UNDER 4.5
- Foye Oluokun UNDER 8.5
- Brandon Jones UNDER 5.5
- Jessie Bates UNDER 6.5
- Daiyan Henley UNDER 7.5
- DaVon Hamilton UNDER 2.5 — starter conflict review
- Quincy Williams UNDER 6.5

These are **reference-only divergences**, not directly executable sportsbook opportunities.

The next proper workflow remains:
1. Frozen model identifies divergence.
2. Market-movement layer adds context.
3. Trust-state/role-state is applied.
4. Actual sportsbook quote is checked directly before any execution decision.

---

## 13. WHAT HAS BEEN SOLVED IN THIS THREAD

Do not redo these investigations unless something changes:

- Week 2 OMEGA freeze completed.
- Frozen CONTROL / role-shadow architecture established.
- Deterministic identity bridge hardened.
- PropsMadness T+A Explore capture normalized.
- Reference-only vs executable distinction enforced.
- Multibook T+A endpoints investigated and proven unusable for now.
- Null multibook placeholders explicitly rejected.
- Week 2 downstream comparison hardened.
- Verification queue built.
- Reference-market movement ledger built.
- Movement ledger tested on multiple snapshots.
- Automatic capture → import → comparison → movement rebuild pipeline built.
- Automation successfully passed an end-to-end real run.
- No market movement has occurred yet; this is not a bug.

---

## 14. NEXT DEVELOPMENT STEP

### Immediate next milestone
Wait for the first **genuine PropsMadness T+A reference-board move**.

When a real move appears, validate:
1. Old line vs new line is correct.
2. Old price vs new price is correct.
3. Book change is correct if applicable.
4. Frozen CONTROL probability is recomputed at the **new exact half-line**.
5. Role-shadow probability is also recomputed at the exact new line.
6. EV/divergence change is mathematically correct.
7. The event remains reference-only/non-executable.
8. No post-kickoff contamination exists.

### After first real movement validates
Build **OMEGA 0.38 — Meaningful Movement Radar**.

OMEGA 0.38 should:
- Suppress unchanged/noise rows.
- Distinguish:
  - threshold/line movement
  - juice-only movement
  - book-source change
  - adds/removals
- Show movement direction relative to the frozen model.
- Track repeated directional moves across multiple snapshots.
- Track whether model divergence is shrinking or widening.
- Preserve role-state warnings:
  - ROLE_ALIGNED
  - STARTER_CONFLICT_REVIEW
  - REVIEW_BACKUP_CONFLICT
- Never label a move “sharp money” without actual evidence.
- Never rank reference movement as executable betting truth.
- Prefer extension display so CSV inspection is no longer necessary.

Potential downstream idea after 0.38:
- Add a compact NFL OMEGA movement panel to the extension showing:
  - player
  - game
  - old → new line
  - old → new price
  - book
  - movement type
  - CONTROL probability
  - CONTROL/reference divergence before/after
  - role state
  - direct-verification-needed flag

---

## 15. IMPORTANT ENGINEERING STYLE / USER PREFERENCES

- Prefer direct commands and operational steps.
- Avoid unnecessary theory when a concrete fix can be made.
- Version every meaningful change.
- Never overwrite historical artifacts.
- Preserve immutable audit trails.
- Use GitHub repo as source of truth.
- Before coding, inspect current live files rather than assuming prior versions.
- Keep scripts robust against schema drift.
- Do not silently relax integrity checks just to make a script pass.
- If a source is missing/null, fail or quarantine rather than fabricate.
- Keep automated work auditable and reproducible.

---

## 16. USEFUL CURRENT COMMANDS

### Manual direct capture
```bash
cd /Users/abbeyfelix/Developer/MODEL
zsh scripts/nfl/prepare_omega_propsmadness_nfl_ta_direct_0176.command
```

### Manual import/comparison
```bash
zsh scripts/nfl/import_omega_propsmadness_nfl_ta_direct_01711.command
```

### Manual movement-ledger rebuild
```bash
zsh scripts/nfl/build_omega_ta_reference_market_movement_0370.command
```

### Install/reinstall automation
```bash
zsh scripts/nfl/install_omega_ta_auto_ingest_0371.command
```

### Watch automation
```bash
tail -f "$HOME/Library/Logs/MODEL/omega-ta-auto.log"
```

### Watch errors
```bash
tail -f "$HOME/Library/Logs/MODEL/omega-ta-auto.err.log"
```

---

## 17. LATEST KNOWN GIT / VERSION CONTEXT

Important recent commits from this work included:
- `318c37d` — OMEGA 0.36 multibook capture work
- `5444dbc` — multibook diagnostic
- `bd1ae55` — 0.36.2 route probe tooling
- `5877102` — OMEGA 0.37 movement ledger
- `e9c6098` — fixed 0.37 phase1b environment path
- `ca8fcd9` — latest automation-side processing hardening in this thread

The exact current HEAD in the next thread should be checked with:
```bash
git log -1 --oneline
```

---

## 18. STARTING INSTRUCTION FOR THE NEXT CHAT

When this file is uploaded into a new chat, continue from here:

> We have a frozen Week 2 NFL OMEGA T+A model, an immutable PropsMadness reference capture/import pipeline, a working 0.37 reference-market movement ledger, and a fully automated 0.37.1 capture → import → comparison → movement workflow. Three snapshots have already been captured automatically/manually with 438 observations, 292 transitions, and no actual market movement yet. Do not refit or mutate the frozen model. Wait for the first genuine movement event, validate it exactly, then build OMEGA 0.38 Meaningful Movement Radar.


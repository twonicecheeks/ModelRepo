# MODEL 2.9.0 NFL — Phase 1B Historical Snapshot and Coverage Audit

Status: **RESEARCH DATA PLUMBING ONLY**. MLB production remains MODEL 2.8.3 / service 2.3.6. No NFL market runtime is wired and no OddsPapi request is used by this phase.

## Purpose

Phase 1B turns the Phase 1 nflverse contract into an immutable, reproducible local research dataset before any NFL coefficients are fit.

The default research coverage window is **2016–2025**, with **2015 as history seed only** so 2016 Week 1 can receive a prior-season team profile. This is an audit window, **not a frozen training window**. The 2025 season remains the untouched holdout and 2026 remains prospective-only.

## Source assets

An explicit snapshot build acquires:

- nflverse schedules (`games.csv`)
- nflverse players (`players.parquet`)
- weekly rosters for 2015–2025
- play-by-play for 2015–2025

The source plan follows the provider URLs already defined in `NFLVERSE_DATA_CONTRACT.json`.

## Raw snapshot integrity

Raw files are not copied repeatedly into timestamp folders. They are stored in a SHA256 content-addressed blob store:

`data/raw/nfl/nflverse/blobs/<sha-prefix>/<sha256>`

Each build creates an immutable manifest:

`data/raw/nfl/nflverse/snapshots/<snapshot-id>/SOURCE_MANIFEST.json`

The manifest records URL, SHA256, byte count, fetch timestamp, response metadata, research seasons, seed seasons, and explicitly records `oddsPapiRequests: 0`.

`CURRENT_RAW_SNAPSHOT` is only a pointer to the most recently completed source snapshot.

## Team identity and relocation continuity

The raw nflverse `game_id` is preserved exactly and remains canonical game identity.

Historical team performance needs franchise continuity across relocations. That normalization occurs only inside the nflverse provider layer. Examples include:

- OAK → LV
- SD → LAC
- STL/LAR → LA
- WSH → WAS

The raw source team abbreviations remain available in normalized game identity rows. Display names are never used as join keys.

## Normalized outputs

Each successful source snapshot produces an immutable normalized directory:

`data/normalized/nfl/phase1/<snapshot-id>/`

Core outputs:

- `game_identity.csv` — identity and pregame-stable context only
- `game_targets.csv` — outcomes only, physically separate from feature data
- `player_identity.csv` — `gsis_id` primary player identity
- `qb_roster_weekly.csv` — QB roster identity scaffold, not a starter-QB model
- `team_game_metrics.csv` — interpretable PBP-derived team metrics
- `pregame_features.csv` / `.jsonl` — strictly prior-only pregame features
- `NFLVERSE_COVERAGE_AUDIT.json` / `.md`
- `NORMALIZATION_MANIFEST.json`

`CURRENT_PHASE1_SNAPSHOT` points to the most recent completed normalized snapshot.

## Leakage protection

Schedule sportsbook fields may exist in the raw nflverse schedule source, but they are not copied into the independent model feature artifact.

Current-game scores are written only to `game_targets.csv`. They are not written to `pregame_features.csv`.

Same-season team metrics use only weeks strictly less than the target week. 2015 is used only to provide 2016 prior-season history. 2025 feature rows are tagged `HOLDOUT_NEVER_FIT`.

## Python dependency and TLS boundary

Parquet normalization uses `pyarrow==25.0.1` and HTTPS acquisition uses `certifi==2026.7.22` inside the isolated virtual environment at:

`~/Library/Application Support/MODEL/nfl-python/phase1b`

The explicit certifi CA bundle is required because some macOS Python/OpenSSL installations do not inherit the macOS Keychain trust store for `urllib`, even when `pip` and `curl` work normally. MODEL constructs a certificate-validating `ssl.create_default_context(cafile=certifi.where())` for nflverse downloads. It does **not** disable hostname or certificate verification and does not modify the user's global certificate configuration.

The project does not install these dependencies into the user's global Python environment.

## User commands

Repository-only audit, with no downloads:

```bash
cd /Users/abbeyfelix/Developer/MODEL
zsh scripts/nfl/audit_phase1b_snapshot.command
```

Show the planned nflverse asset list without downloading:

```bash
python3 scripts/nfl/build_phase1_snapshot.py --root /Users/abbeyfelix/Developer/MODEL --plan
```

Build the actual source snapshot and normalized coverage tables:

```bash
zsh scripts/nfl/build_phase1_snapshot.command
```

That command may download substantial historical nflverse data and may install the pinned parquet dependency into the isolated MODEL NFL environment. It makes **zero OddsPapi requests**.

## Gate before modeling

Do not fit NFL coefficients immediately after the snapshot build. Review the generated coverage audit first, including:

- game/label coverage by season
- two-team PBP coverage
- feature missingness
- Week 1 prior coverage
- QB roster `gsis_id` resolution
- relocation continuity
- market-field isolation

Only after this audit is accepted should the chronological training window and model baselines be frozen.

### Phase 1B.2 dependency-version normalization hotfix

The pinned dependency remains `certifi==2026.7.22`. On the user's Python 3.14 environment, the installed certifi runtime identifies itself as `2026.07.22`. These are the same calendar version; the former Phase 1B.1 bootstrap compared the presentation strings literally and therefore failed after a correct installation.

Phase 1B.2 centralizes dependency validation in `scripts/nfl/check_phase1b_dependencies.py` and compares numeric version components. It still validates both distribution metadata and runtime versions, keeps the exact requirements pin, and continues to require `ssl.CERT_REQUIRED` plus hostname verification. No TLS bypass, data-contract change, model coefficient change, market wiring, or MLB runtime mutation is introduced.

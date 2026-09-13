# MODEL NFL 2.9.0 — Phase 1B.3 PBP Schema Compatibility

Live real-data normalization exposed nflverse schema drift: at least one downloaded play-by-play parquet did not export a standalone `no_play` column even though the normalizer required it.

The normalized football definition is unchanged. Nullified plays and QB kneels remain excluded. The adapter now resolves those semantics as follows:

- `no_play`: native `no_play` when present; otherwise `play_type == "no_play"`.
- `qb_kneel`: native `qb_kneel` when present; otherwise `play_type == "qb_kneel"`.
- If neither a native flag nor `play_type` can represent an exclusion, normalization fails closed.

This is provider-schema compatibility only. It changes no model coefficients, no training split, no market policy, and no MLB production runtime. 2025 remains `HOLDOUT_NEVER_FIT`.

A resume command reuses the immutable raw snapshot that already downloaded successfully, avoiding another 24-source acquisition pass:

`zsh scripts/nfl/resume_phase1_normalization.command`

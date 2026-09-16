#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
BOOT="$ROOT/scripts/nfl/bootstrap_phase1_python.command"

cd "$ROOT"

if [[ ! -x "$PY" ]]; then
  zsh "$BOOT" >/dev/null
fi
[[ -x "$PY" ]] || { echo "FAIL pinned NFL Python unavailable: $PY" >&2; exit 1; }
"$PY" "$ROOT/scripts/nfl/check_phase1b_dependencies.py"
"$PY" -m py_compile \
  "$ROOT/scripts/nfl/refresh_nflverse_2026_results_0250.py" \
  "$ROOT/scripts/nfl/refresh_omega_2026_snap_counts_0290.py" \
  "$ROOT/scripts/nfl/capture_omega_tackle_016_2026_pregame.py" \
  "$ROOT/scripts/nfl/freeze_omega_week2_dual_track_0330.py"

echo
echo "===== OMEGA 0.33 REFRESH ISOLATED 2026 RESULTS ====="
"$PY" "$ROOT/scripts/nfl/refresh_nflverse_2026_results_0250.py" --root "$ROOT"

echo
echo "===== OMEGA 0.33 REFRESH 2026 SNAP COUNTS ====="
# The target game argument is only a capture diagnostic; the immutable parquet contains
# the full 2026 snap-count release and 0.33 materializes Week 1 rows only.
"$PY" "$ROOT/scripts/nfl/refresh_omega_2026_snap_counts_0290.py" --root "$ROOT" --game-id 2026_01_DEN_KC

echo
echo "===== OMEGA 0.33 CAPTURE FRESH WEEK 2 PREGAME ROLE/ROSTER STATE ====="
"$PY" "$ROOT/scripts/nfl/capture_omega_tackle_016_2026_pregame.py" --root "$ROOT" --week 2

echo
echo "===== OMEGA 0.33 FREEZE WEEK 2 CONTROL + ROLE-POINT CHALLENGER ====="
"$PY" "$ROOT/scripts/nfl/freeze_omega_week2_dual_track_0330.py" --root "$ROOT" --week 2

echo
echo "OMEGA 0.33 WEEK 2 DUAL-TRACK PIPELINE PASS"
echo "PASS Week 1 admitted as prior state only · Week 2 outcomes 0 · refits 0 · market fields 0"

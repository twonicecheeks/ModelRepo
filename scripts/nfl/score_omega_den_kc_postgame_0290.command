#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
GAME_ID="2026_01_DEN_KC"
FREEZE_ID="20260915T001242Z_62e5b31c"
cd "$ROOT"

if [[ ! -x "$PY" ]]; then
  zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
fi
"$PY" scripts/nfl/check_phase1b_dependencies.py
"$PY" -m py_compile scripts/nfl/refresh_omega_2026_snap_counts_0290.py scripts/nfl/score_omega_current_role_snap_0290.py

echo
echo "===== REFRESH ISOLATED 2026 NFLVERSE RESULTS ====="
"$PY" scripts/nfl/refresh_nflverse_2026_results_0250.py --root "$ROOT"
RESULT_PTR="$ROOT/data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST"
RESULT_REL="$(cat "$RESULT_PTR")"
if [[ "$RESULT_REL" == /* ]]; then RESULT_MANIFEST="$RESULT_REL"; else RESULT_MANIFEST="$ROOT/$RESULT_REL"; fi
"$PY" scripts/nfl/check_omega_game_results_ready_0250.py --root "$ROOT" --game-id "$GAME_ID" --source-manifest "$RESULT_MANIFEST"

echo
echo "===== REFRESH ISOLATED 2026 SNAP COUNTS ====="
"$PY" scripts/nfl/refresh_omega_2026_snap_counts_0290.py --root "$ROOT" --game-id "$GAME_ID"

echo
echo "===== SCORE FROZEN OMEGA 0.2.8 DEN-KC ====="
"$PY" scripts/nfl/score_omega_current_role_snap_0290.py --root "$ROOT" --freeze-id "$FREEZE_ID" --source-manifest "$RESULT_MANIFEST"

echo
echo "OMEGA 0.29 DEN-KC POSTGAME PIPELINE PASS"
echo "PASS frozen forecasts unchanged · refits 0 · market fields read 0"

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
  "$ROOT/scripts/nfl/check_omega_week2_universe_0330.py" \
  "$ROOT/scripts/nfl/freeze_omega_week2_dual_track_0330.py" \
  "$ROOT/scripts/nfl/freeze_omega_week2_dual_track_0332.py"

echo
echo "===== OMEGA 0.33.2 RESUME — VERIFY EXISTING FULL WEEK 2 UNIVERSE ====="
"$PY" "$ROOT/scripts/nfl/check_omega_week2_universe_0330.py" --root "$ROOT"

echo
echo "===== OMEGA 0.33.2 RESUME — FREEZE FROM EXISTING HASHED SOURCES ====="
"$PY" "$ROOT/scripts/nfl/freeze_omega_week2_dual_track_0332.py" --root "$ROOT" --week 2

echo
echo "OMEGA 0.33.2 RESUME PASS"
echo "PASS no source refresh · existing immutable results/snap/pregame pointers consumed · os-shadow packaging bug fixed only · model logic unchanged"

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
  "$ROOT/scripts/nfl/compare_omega_tackle_market_0180.py" \
  "$ROOT/scripts/nfl/compare_omega_week2_dual_track_market_0340.py"

echo
echo "===== OMEGA 0.34 WEEK 2 DUAL-TRACK MARKET COMPARISON ====="
"$PY" "$ROOT/scripts/nfl/compare_omega_week2_dual_track_market_0340.py" --root "$ROOT"

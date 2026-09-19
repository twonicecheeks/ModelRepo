#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
cd "$ROOT"

if [[ ! -x "$PY" ]]; then
  zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
fi
"$PY" scripts/nfl/check_phase1b_dependencies.py
"$PY" tests/nfl/test_omega_market_calibration_0350.py

GAME_ID="${1:-${MODEL_OMEGA_CALIBRATION_GAME_ID:-}}"
[[ -n "$GAME_ID" ]] || { echo "usage: $0 GAME_ID" >&2; exit 2; }

RESULT_PTR="$ROOT/data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST"
[[ -s "$RESULT_PTR" ]] || { echo "FAIL dedicated 2026 results manifest pointer missing; run refresh_nflverse_2026_results_0250.py first" >&2; exit 3; }
RESULT_REL="$(cat "$RESULT_PTR")"
if [[ "$RESULT_REL" == /* ]]; then
  RESULT_MANIFEST="$RESULT_REL"
else
  RESULT_MANIFEST="$ROOT/$RESULT_REL"
fi
[[ -f "$RESULT_MANIFEST" ]] || { echo "FAIL dedicated results manifest target missing: $RESULT_MANIFEST" >&2; exit 3; }

echo "PASS pinned results manifest: $RESULT_MANIFEST"
"$PY" scripts/nfl/check_omega_game_results_ready_0250.py \
  --root "$ROOT" \
  --game-id "$GAME_ID" \
  --source-manifest "$RESULT_MANIFEST"

exec "$PY" scripts/nfl/score_omega_market_calibration_0350.py \
  --root "$ROOT" \
  --game-id "$GAME_ID" \
  --source-manifest "$RESULT_MANIFEST"

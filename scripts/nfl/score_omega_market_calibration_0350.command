#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
python3 tests/nfl/test_omega_market_calibration_0350.py
GAME_ID="${1:-${MODEL_OMEGA_CALIBRATION_GAME_ID:-}}"
[[ -n "$GAME_ID" ]] || { echo "usage: $0 GAME_ID" >&2; exit 2; }
python3 scripts/nfl/check_omega_game_results_ready_0250.py --root "$ROOT" --game-id "$GAME_ID"
exec python3 scripts/nfl/score_omega_market_calibration_0350.py --root "$ROOT" --game-id "$GAME_ID"

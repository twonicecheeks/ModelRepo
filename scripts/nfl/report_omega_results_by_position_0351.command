#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
SEASON="${1:-2026}"
cd "$ROOT"

python3 tests/nfl/test_omega_results_by_position_0351.py
python3 scripts/nfl/rebuild_omega_season_eval_index_0230.py --root "$ROOT" --season "$SEASON"
exec python3 scripts/nfl/report_omega_results_by_position_0351.py --root "$ROOT" --season "$SEASON"

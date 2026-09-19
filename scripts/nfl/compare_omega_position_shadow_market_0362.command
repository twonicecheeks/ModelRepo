#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
python3 tests/nfl/test_omega_position_shadow_market_0362.py
exec python3 scripts/nfl/compare_omega_position_shadow_market_0362.py --root "$ROOT" "$@"

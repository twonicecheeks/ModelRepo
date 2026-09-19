#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
exec python3 scripts/nfl/compare_omega_position_shadow_market_0362.py --root "$ROOT" "$@"

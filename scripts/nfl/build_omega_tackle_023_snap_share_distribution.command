#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"

python3 -m py_compile \
  packages/models/nfl/omega/snap_share_distribution_challenger.py \
  scripts/nfl/build_omega_tackle_023_snap_share_distribution.py \
  tests/models/nfl/omega/test_snap_share_distribution_challenger.py

python3 tests/models/nfl/omega/test_snap_share_distribution_challenger.py
python3 scripts/nfl/build_omega_tackle_023_snap_share_distribution.py --root "$ROOT"

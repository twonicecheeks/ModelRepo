#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
cd "$ROOT"
python3 scripts/nfl/inspect_omega_depth_chart_history_0260.py "$@"

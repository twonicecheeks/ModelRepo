#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="${0:A:h}"
CODE_ROOT="${MODEL_ROOT_OVERRIDE:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
JS="$CODE_ROOT/packages/providers/propsmadness/qb/nfl_qb_passing_yards_direct_capture_0243.js"
[[ -f "$JS" ]] || { echo "FAIL QB capture adapter missing: $JS" >&2; exit 1; }
pbcopy < "$JS"
echo "QB capture script copied."
echo "1. Open https://propsmadness.com/nfl in your signed-in Chrome tab."
echo "2. Open DevTools > Console, paste the script, and press Enter."
echo "3. Wait for NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_*.json to download."
echo "4. From this NFL worktree run: zsh scripts/nfl/run_nfl_week3_remaining_0380.command"

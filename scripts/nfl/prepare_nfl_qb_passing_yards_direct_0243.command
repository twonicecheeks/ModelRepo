#!/bin/zsh
set -euo pipefail
CODE_ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL-NFL-039}"
JS="$CODE_ROOT/packages/providers/propsmadness/qb/nfl_qb_passing_yards_direct_capture_0243.js"
[[ -f "$JS" ]] || { echo "FAIL missing QB passing-yards capture script: $JS" >&2; exit 1; }
pbcopy < "$JS"
echo
echo "NFL QB 0.2.4.3 — PASSING-YARDS DIRECT CAPTURE PREPARED"
echo "PASS capture JavaScript copied to clipboard"
echo "1) Open https://propsmadness.com/nfl"
echo "2) Open DevTools -> Console, paste, press Enter."
echo "3) Browser downloads NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_*.json"
echo "4) Run:"
echo "   zsh $CODE_ROOT/scripts/nfl/build_nfl_qb_week2_verified_starters_0243.command"

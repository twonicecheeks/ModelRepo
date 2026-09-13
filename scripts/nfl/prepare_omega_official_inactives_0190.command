#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
JS="$ROOT/packages/providers/nfl-official/omega-availability/omega_nfl_official_inactives_capture_0190.js"
[[ -f "$JS" ]] || { echo "FAIL missing capture script: $JS"; exit 1; }
pbcopy < "$JS"
echo
echo "OMEGA 0.19.0 — OFFICIAL NFL GAMEDAY AVAILABILITY CAPTURE PREPARED"
echo
echo "PASS capture JavaScript copied to clipboard"
echo "PASS this Terminal command made 0 network requests"
echo
echo "USE ONLY WHEN AN OFFICIAL NFL INACTIVE REPORT FOR THE TARGET GAME(S) IS PUBLISHED:"
echo "1) Open https://www.nfl.com/inactives/ or the official NFL.com inactives article."
echo "2) Confirm the target teams' inactive lists are visibly present."
echo "3) Open DevTools -> Console, paste, press Enter."
echo "4) Chrome downloads OMEGA_0190_NFL_OFFICIAL_INACTIVES_*.json."
echo "5) Run:"
echo "   zsh scripts/nfl/import_omega_official_inactives_0190.command"

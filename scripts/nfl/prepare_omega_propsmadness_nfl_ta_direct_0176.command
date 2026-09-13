#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
PROBE="$ROOT/packages/providers/propsmadness/omega-nfl/omega_propsmadness_nfl_ta_direct_capture_0176.js"
[[ -f "$PROBE" ]] || { echo "FAIL missing direct adapter capture script: $PROBE"; exit 1; }
pbcopy < "$PROBE"
echo
echo "OMEGA 0.17.6 — PROPSMADNESS NFL T+A DIRECT ADAPTER PREPARED"
echo
echo "PASS direct endpoint: /api/offer/nfl/explore/player-tackles-assists"
echo "PASS matches endpoint: /api/offer/nfl/matches"
echo "PASS JavaScript copied to clipboard"
echo "PASS network requests from this Terminal command: 0"
echo
echo "NEXT:"
echo "1) Open https://propsmadness.com/nfl in Chrome and let it fully load."
echo "2) Open DevTools -> Console. If Chrome requires it, type: allow pasting"
echo "3) Paste and press Enter. You do NOT need to click Tckl+Ast."
echo "4) Chrome will download OMEGA_0176_PROPSMADNESS_NFL_TA_DIRECT_CAPTURE_*.json."
echo "5) Return to Terminal and run:"
echo "   zsh scripts/nfl/import_omega_propsmadness_nfl_ta_direct_0176.command"

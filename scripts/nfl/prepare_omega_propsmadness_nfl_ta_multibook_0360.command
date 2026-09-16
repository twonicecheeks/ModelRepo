#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
PROBE="$ROOT/packages/providers/propsmadness/omega-nfl/omega_propsmadness_nfl_ta_multibook_capture_0360.js"
[[ -f "$PROBE" ]] || { echo "FAIL missing OMEGA 0.36 multibook capture script: $PROBE"; exit 1; }
pbcopy < "$PROBE"
echo
echo "OMEGA 0.36 — PROPSMADNESS NFL T+A MULTIBOOK CAPTURE PREPARED"
echo
echo "PASS discovery endpoint: /api/offer/nfl/explore/player-tackles-assists"
echo "PASS per-player endpoint: /api/players/{playerId}/match/{matchId}/bet-offers/player-tackles-assists"
echo "PASS main lines only · alternate ladders NOT requested"
echo "PASS concurrency 4 · JavaScript copied to clipboard"
echo "PASS network requests from this Terminal command: 0"
echo
echo "NEXT:"
echo "1) Open https://propsmadness.com/nfl in Chrome and let it fully load."
echo "2) Open DevTools -> Console. If Chrome requires it, type: allow pasting"
echo "3) Paste and press Enter. Leave the tab open until capture completes."
echo "4) Chrome will download OMEGA_0360_PROPSMADNESS_NFL_TA_MULTIBOOK_*.json."
echo "5) Return to Terminal and run:"
echo "   zsh scripts/nfl/import_omega_propsmadness_nfl_ta_multibook_0360.command"

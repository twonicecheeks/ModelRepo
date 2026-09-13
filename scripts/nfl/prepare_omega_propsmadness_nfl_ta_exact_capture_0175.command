#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
PROBE="$ROOT/packages/providers/propsmadness/omega-probe/omega_propsmadness_nfl_ta_exact_capture_0175.js"
if [[ ! -f "$PROBE" ]]; then
  echo "FAIL missing probe: $PROBE"; exit 1
fi
pbcopy < "$PROBE"
echo
echo "OMEGA 0.17.5 — EXACT T+A CONTROL CAPTURE PREPARED"
echo
echo "PASS probe JavaScript copied to clipboard"
echo "PASS network requests from this command: 0"
echo
echo "NEXT:"
echo "1) In Chrome, open https://propsmadness.com/nfl and let the app fully load."
echo "2) Confirm you can visibly see the market control Tckl+Ast."
echo "3) Open DevTools -> Console. If required, type: allow pasting"
echo "4) Paste and press Enter. DO NOT click Tackles manually."
echo "5) Wait ~12 seconds. Chrome will download OMEGA_0175_PROPSMADNESS_NFL_TA_EXACT_CAPTURE_*.json."
echo "6) Return to Terminal and run:"
echo "   zsh scripts/nfl/import_omega_propsmadness_nfl_ta_exact_capture_0175.command"

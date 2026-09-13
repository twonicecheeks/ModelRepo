#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
JS="$ROOT/packages/providers/propsmadness/nfl-tackle-probe/omega_propsmadness_nfl_ta_probe_0173.js"
[[ -f "$JS" ]] || { echo "FAIL probe script missing: $JS"; exit 1; }
command -v pbcopy >/dev/null || { echo "FAIL pbcopy unavailable"; exit 1; }
pbcopy < "$JS"
echo "OMEGA 0.17.3 — NFL T+A FILE-HANDOFF PROBE PREPARED"
echo
echo "PASS probe JavaScript copied to clipboard"
echo "PASS network requests from this command: 0"
echo
echo "NEXT:"
echo "1) In Chrome, open https://propsmadness.com/nfl"
echo "2) Open DevTools -> Console. If Chrome requires it, type: allow pasting"
echo "3) Paste the clipboard contents and press Enter."
echo "4) Wait ~9 seconds while it switches Tackles -> Tckl+Ast."
echo "5) Chrome should download OMEGA_0173_PROPSMADNESS_NFL_TA_CAPTURE_*.json."
echo "6) If not, click the orange 'Download OMEGA T+A capture' button on the page."
echo "7) Return to Terminal and run:"
echo "   zsh scripts/nfl/import_omega_propsmadness_nfl_ta_probe_0173.command"

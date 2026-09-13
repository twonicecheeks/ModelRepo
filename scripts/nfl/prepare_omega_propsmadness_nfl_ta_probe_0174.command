#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
JS="$ROOT/packages/providers/propsmadness/nfl-tackle-probe/omega_propsmadness_nfl_ta_probe_0174.js"
[[ -f "$JS" ]] || { echo "FAIL probe script missing: $JS"; exit 1; }
command -v pbcopy >/dev/null || { echo "FAIL pbcopy unavailable"; exit 1; }
pbcopy < "$JS"
echo "OMEGA 0.17.4 — BROAD NFL T+A DISCOVERY PROBE PREPARED"
echo
echo "PASS probe JavaScript copied to clipboard"
echo "PASS network requests from this command: 0"
echo
echo "NEXT:"
echo "1) In Chrome, open https://propsmadness.com/nfl and leave the page fully loaded."
echo "2) Open DevTools -> Console; type 'allow pasting' first if Chrome requires it."
echo "3) Paste the clipboard contents and press Enter."
echo "4) Wait ~15 seconds. The probe captures broad same-origin API traffic plus preloaded DOM/React state."
echo "5) Chrome should download OMEGA_0174_PROPSMADNESS_NFL_TA_DISCOVERY_*.json."
echo "6) If automatic download is blocked, click the blue 'Download OMEGA broad discovery' button."
echo "7) Return to Terminal and run:"
echo "   zsh scripts/nfl/import_omega_propsmadness_nfl_ta_probe_0174.command"

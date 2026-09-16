#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
PROBE="$ROOT/packages/providers/propsmadness/omega-nfl/omega_propsmadness_nfl_ta_route_probe_0362.js"
[[ -f "$PROBE" ]] || { echo "FAIL missing route probe script: $PROBE"; exit 1; }
pbcopy < "$PROBE"
echo
echo "OMEGA 0.36.2 — PROPSMADNESS NFL T+A ROUTE PROBE PREPARED"
echo
echo "PASS probes generic per-player bet-offers + alt T+A route"
echo "PASS samples up to 2 populated-reference players per match"
echo "PASS JavaScript copied to clipboard"
echo "PASS no model reads/writes · no OddsPapi requests"
echo
echo "NEXT:"
echo "1) Open https://propsmadness.com/nfl in Chrome."
echo "2) Open DevTools -> Console. If required, type: allow pasting"
echo "3) Paste once and press Enter."
echo "4) Wait for OMEGA 0.36.2 route probe complete."
echo "5) Chrome downloads OMEGA_0362_PROPSMADNESS_NFL_TA_ROUTE_PROBE_*.json."
echo "6) Then run:"
echo "   zsh scripts/nfl/diagnose_omega_propsmadness_nfl_ta_route_probe_0362.command"

#!/bin/zsh
set -euo pipefail
OMEGA_APP_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
OMEGA_EXISTING_PYTHON="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
if [[ -n "${OMEGA_PYTHON:-}" ]]; then
  OMEGA_BIN="$OMEGA_PYTHON"
elif [[ -x "$OMEGA_EXISTING_PYTHON" ]]; then
  OMEGA_BIN="$OMEGA_EXISTING_PYTHON"
else
  OMEGA_BIN="$(command -v python3)"
fi
cd "$OMEGA_APP_DIR"
"$OMEGA_BIN" -m unittest discover -s tests -v
if command -v node >/dev/null 2>&1; then
  node --check web/app.js
  OMEGA_PYTHON="$OMEGA_BIN" node tests/check_ui.cjs
  "$OMEGA_BIN" tools/verify_mlb_release.py
  "$OMEGA_BIN" tools/verify_delta_release.py
else
  print 'MLB inference and reproduction require Node 18 or newer.'
  exit 1
fi

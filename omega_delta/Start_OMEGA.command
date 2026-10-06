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
"$OMEGA_BIN" -c 'import sys; assert sys.version_info >= (3,10), "OMEGA Next needs Python 3.10 or newer"'
exec "$OMEGA_BIN" "$OMEGA_APP_DIR/server.py" "$@"

#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
PY="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}/bin/python"
BOOT="$ROOT/scripts/nfl/bootstrap_phase1_python.command"
cd "$ROOT"

if [[ ! -x "$PY" ]]; then
  zsh "$BOOT" >/dev/null
fi
[[ -x "$PY" ]] || { echo "FAIL pinned NFL Python unavailable: $PY" >&2; exit 1; }

"$PY" -m py_compile scripts/nfl/freeze_omega_tackle_028_2026_current_role_snap_distribution.py

echo "OMEGA 0.2.8 — refreshing pregame role/depth state for DEN@KC..."
zsh scripts/nfl/capture_omega_tackle_016_2026_pregame.command --week 1

echo
echo "OMEGA 0.2.8 — freezing current-role snap-share distribution before market comparison..."
exec "$PY" scripts/nfl/freeze_omega_tackle_028_2026_current_role_snap_distribution.py \
  --root "$ROOT" \
  --game-id 2026_01_DEN_KC

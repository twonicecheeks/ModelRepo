#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT:-/Users/abbeyfelix/Developer/MODEL}"
PY="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}/bin/python"
BOOT="$ROOT/scripts/nfl/bootstrap_phase1_python.command"
CHECK="$ROOT/scripts/nfl/check_phase1b_dependencies.py"

if [[ ! -x "$PY" ]]; then
  echo "OMEGA 0.16.2 — pinned NFL runtime not found; bootstrapping canonical Phase 1B environment"
  [[ -x "$BOOT" || -f "$BOOT" ]] || { echo "FAIL canonical NFL bootstrap missing: $BOOT" >&2; exit 1; }
  zsh "$BOOT" >/dev/null
fi

[[ -x "$PY" ]] || { echo "FAIL pinned NFL Python unavailable after bootstrap: $PY" >&2; exit 1; }
[[ -f "$CHECK" ]] || { echo "FAIL dependency validator missing: $CHECK" >&2; exit 1; }

if ! "$PY" "$CHECK" --quiet; then
  echo "FAIL pinned NFL runtime dependency validation failed." >&2
  echo "Run: zsh \"$BOOT\"" >&2
  exit 1
fi

echo "OMEGA 0.16.2 — using pinned NFL runtime: $PY"
exec "$PY" "$ROOT/scripts/nfl/build_omega_tackle_016_2026_week1.py" --root "$ROOT" "$@"

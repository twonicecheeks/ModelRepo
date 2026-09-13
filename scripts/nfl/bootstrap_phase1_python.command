#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
REQ="$ROOT/requirements/nfl-phase1b.txt"
CHECK="$ROOT/scripts/nfl/check_phase1b_dependencies.py"

[[ -d "$ROOT" ]] || { echo "ERROR MODEL root not found: $ROOT" >&2; exit 1; }
[[ -f "$REQ" ]] || { echo "ERROR requirements missing: $REQ" >&2; exit 1; }
[[ -f "$CHECK" ]] || { echo "ERROR dependency validator missing: $CHECK" >&2; exit 1; }

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f"MODEL NFL Phase 1B requires Python >=3.10; found {sys.version.split()[0]}")
print(f"PASS Python {sys.version.split()[0]}")
PY

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating isolated NFL Python environment..."
  mkdir -p "$(dirname "$VENV")"
  python3 -m venv "$VENV"
fi

if ! "$VENV/bin/python" "$CHECK" --quiet; then
  echo "Installing pinned NFL research dependencies into isolated environment..."
  "$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade pip
  "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$REQ"
fi

"$VENV/bin/python" "$CHECK"
echo "$VENV/bin/python"

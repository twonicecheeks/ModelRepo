#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
if [[ ! -x "$VENV/bin/python" ]]; then
  zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command"
fi
cd "$ROOT"
"$VENV/bin/python" tests/nfl/test_nfl_qb_starter_resolver_013.py
exec "$VENV/bin/python" scripts/nfl/audit_nfl_qb_starter_resolver_013.py \
  --root "$ROOT" \
  --seasons "${MODEL_NFL_QB_STARTER_RESOLVER_SEASONS:-2016-2024}"

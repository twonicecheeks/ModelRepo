#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"

zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command" >/tmp/model_nfl_phase1b_bootstrap.$$
cat /tmp/model_nfl_phase1b_bootstrap.$$
rm -f /tmp/model_nfl_phase1b_bootstrap.$$

exec "$VENV/bin/python" "$ROOT/scripts/nfl/build_phase1_snapshot.py" \
  --root "$ROOT" \
  --analysis-seasons "${MODEL_NFL_ANALYSIS_SEASONS:-2016-2025}"

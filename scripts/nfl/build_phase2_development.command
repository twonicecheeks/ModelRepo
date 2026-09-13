#!/bin/zsh
set -euo pipefail
ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
cd "$ROOT"
# Reuse the isolated Phase 1B Python environment only to keep interpreter/runtime
# provenance consistent. Phase 2A model fitting itself uses the Python stdlib only.
zsh scripts/nfl/bootstrap_phase1_python.command >/dev/null
PY="$HOME/Library/Application Support/MODEL/nfl-python/phase1b/bin/python"
exec "$PY" scripts/nfl/build_phase2_development.py --root "$ROOT" "$@"

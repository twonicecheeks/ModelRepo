#!/bin/zsh
set -euo pipefail
OMEGA_PROJECT_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
exec zsh "$OMEGA_PROJECT_ROOT/omega_delta/Start_OMEGA.command" "$@"

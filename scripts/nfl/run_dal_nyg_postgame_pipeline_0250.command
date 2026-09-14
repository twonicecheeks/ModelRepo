#!/bin/zsh
set -u
setopt pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
GAME_ID="2026_01_DAL_NYG"
CHALLENGER_ID="20260914T013816Z_c4c00033"
EVAL_425_ID="20260913T220855Z_e81f4298"
MAX_ATTEMPTS="${OMEGA_POSTGAME_MAX_ATTEMPTS:-16}"
SLEEP_SECONDS="${OMEGA_POSTGAME_RETRY_SECONDS:-1800}"
LABEL="com.model.omega.dalnyg-postgame-20260914"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$ROOT/data/results/nfl/omega/automation_logs_0250"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/DAL_NYG_POSTGAME_${STAMP}.log"
exec > >(tee -a "$LOG") 2>&1

finish() {
  local rc="$1"
  echo
  echo "POSTGAME PIPELINE EXIT $rc · $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "LOG: $LOG"
  # The LaunchAgent is intentionally one-date-only. Remove its plist after execution
  # so there is no persistent annual schedule. The loaded job disappears at logout/
  # reboot even if launchd keeps the in-memory definition for the current session.
  rm -f "$PLIST" 2>/dev/null || true
  return "$rc"
}

TODAY="$(date +%Y-%m-%d)"
if [[ "$TODAY" != "2026-09-14" ]]; then
  echo "REFUSE: this one-shot runner is date-locked to 2026-09-14; local date is $TODAY"
  finish 64
  exit 64
fi

cd "$ROOT" || { finish 2; exit 2; }
echo "OMEGA 0.25 — AUTOMATED DAL@NYG POSTGAME PIPELINE"
echo "Started: $(date)"
echo "Game: $GAME_ID"
echo "Challenger: $CHALLENGER_ID"
echo "4:25 evaluation: $EVAL_425_ID"
echo "Retry policy: $MAX_ATTEMPTS attempts · $SLEEP_SECONDS seconds between attempts"
echo "Policy: immutable results snapshots · no fitting · no model mutation · no git pull"
echo

if [[ ! -x "$PY" ]]; then
  echo "NFL isolated Python environment missing; bootstrapping pinned dependencies..."
  if ! zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command"; then
    echo "FAIL bootstrap"
    finish 2
    exit 2
  fi
fi
if ! "$PY" "$ROOT/scripts/nfl/check_phase1b_dependencies.py"; then
  echo "FAIL pinned NFL dependency validation"
  finish 2
  exit 2
fi

ready=0
attempt=1
while (( attempt <= MAX_ATTEMPTS )); do
  echo
  echo "===== NFLVERSE ATTEMPT $attempt/$MAX_ATTEMPTS · $(date) ====="
  if "$PY" "$ROOT/scripts/nfl/refresh_nflverse_2026_results_0250.py" --root "$ROOT"; then
    if "$PY" "$ROOT/scripts/nfl/check_omega_game_results_ready_0250.py" --root "$ROOT" --game-id "$GAME_ID"; then
      ready=1
      break
    else
      check_rc=$?
      echo "Readiness gate returned $check_rc; nflverse is not ready yet."
    fi
  else
    refresh_rc=$?
    echo "Snapshot refresh returned $refresh_rc; will retry."
  fi

  if (( attempt < MAX_ATTEMPTS )); then
    echo "Sleeping $SLEEP_SECONDS seconds before retry..."
    sleep "$SLEEP_SECONDS"
  fi
  (( attempt++ ))
done

if (( ready != 1 )); then
  echo "FAIL nflverse did not become DAL@NYG-ready within retry window."
  echo "No score was written."
  finish 75
  exit 75
fi

echo
echo "===== SCORE ROLE-ADJUSTED CHALLENGER ====="
ROLE_PTR="$ROOT/data/results/nfl/omega/CURRENT_OMEGA_ROLE_ADJUSTED_SCORE"
role_done=0
if [[ -f "$ROLE_PTR" ]]; then
  role_value="$(cat "$ROLE_PTR" 2>/dev/null || true)"
  if [[ "$role_value" == "$CHALLENGER_ID/"* ]]; then
    role_done=1
    echo "PASS challenger already scored: $role_value · skipping duplicate score run"
  fi
fi
if (( role_done == 0 )); then
  if ! "$PY" "$ROOT/scripts/nfl/score_omega_role_adjusted_challenger_0240.py" \
      --root "$ROOT" --challenger-id "$CHALLENGER_ID"; then
    echo "FAIL role-adjusted challenger scoring"
    finish 3
    exit 3
  fi
fi

echo
echo "===== SCORE FROZEN 4:25 EVALUATION ====="
if "$PY" - "$ROOT" "$EVAL_425_ID" <<'PY'
from pathlib import Path
import json, sys
root=Path(sys.argv[1]); eid=sys.argv[2]
base=root/'data/results/nfl/omega/evaluation_0230'/eid
for rp in sorted(base.glob('*/OMEGA_0.23_SCORE_REPORT.json'), reverse=True) if base.exists() else []:
    try:
        d=json.loads(rp.read_text(encoding='utf-8'))
    except Exception:
        continue
    if d.get('status')=='COMPLETE':
        print(f"PASS 4:25 evaluation already has COMPLETE score: {rp.parent.name}")
        raise SystemExit(0)
raise SystemExit(1)
PY
then
  echo "Skipping duplicate 4:25 score run."
else
  if ! "$PY" "$ROOT/scripts/nfl/score_omega_prospective_eval_0230.py" \
      --root "$ROOT" --evaluation-id "$EVAL_425_ID"; then
    echo "FAIL frozen 4:25 evaluation scoring"
    finish 4
    exit 4
  fi
fi

echo
echo "===== REBUILD 2026 SEASON EVALUATION INDEX ====="
if ! "$PY" "$ROOT/scripts/nfl/rebuild_omega_season_eval_index_0230.py" --root "$ROOT" --season 2026; then
  echo "FAIL season index rebuild"
  finish 5
  exit 5
fi

DONE="$LOG_DIR/DAL_NYG_POSTGAME_COMPLETE.txt"
{
  echo "status=PASS"
  echo "completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "game_id=$GAME_ID"
  echo "challenger_id=$CHALLENGER_ID"
  echo "evaluation_425_id=$EVAL_425_ID"
  echo "current_raw_snapshot=$(cat "$ROOT/data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT" 2>/dev/null || true)"
  echo "role_score=$(cat "$ROOT/data/results/nfl/omega/CURRENT_OMEGA_ROLE_ADJUSTED_SCORE" 2>/dev/null || true)"
  echo "season_index=$(cat "$ROOT/data/results/nfl/omega/CURRENT_OMEGA_SEASON_INDEX" 2>/dev/null || true)"
  echo "log=$LOG"
} > "$DONE"

echo
echo "AUTOMATION PASS — DAL@NYG results captured and OMEGA evaluation scored"
echo "MARKER: $DONE"
/usr/bin/osascript -e 'display notification "DAL-NYG OMEGA scoring completed successfully." with title "MODEL NFL"' >/dev/null 2>&1 || true
finish 0
exit 0

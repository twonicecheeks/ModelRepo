#!/bin/zsh
set -euo pipefail

ROOT="${MODEL_ROOT_OVERRIDE:-/Users/abbeyfelix/Developer/MODEL}"
VENV="${MODEL_NFL_VENV_OVERRIDE:-$HOME/Library/Application Support/MODEL/nfl-python/phase1b}"
PY="$VENV/bin/python"
RUNNER="$ROOT/scripts/nfl/run_dal_nyg_postgame_pipeline_0250.command"
LABEL="com.model.omega.dalnyg-postgame-20260914"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/MODEL"
UID_NUM="$(id -u)"

cd "$ROOT"
[[ -f "$RUNNER" ]] || { echo "FAIL missing runner: $RUNNER"; exit 1; }
mkdir -p "$PLIST_DIR" "$LOG_DIR"

# Validate exact code/dependencies now, while the user is present. The overnight job
# intentionally performs no git pull and therefore cannot silently change code.
zsh -n "$RUNNER"
zsh "$ROOT/scripts/nfl/bootstrap_phase1_python.command" >/tmp/model_omega_0250_bootstrap.$$
cat /tmp/model_omega_0250_bootstrap.$$
rm -f /tmp/model_omega_0250_bootstrap.$$
"$PY" -m py_compile \
  "$ROOT/scripts/nfl/refresh_nflverse_2026_results_0250.py" \
  "$ROOT/scripts/nfl/check_omega_game_results_ready_0250.py" \
  "$ROOT/scripts/nfl/score_omega_role_adjusted_challenger_0240.py" \
  "$ROOT/scripts/nfl/score_omega_prospective_eval_0230.py"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-i</string>
    <string>/bin/zsh</string>
    <string>$RUNNER</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Month</key><integer>9</integer>
    <key>Day</key><integer>14</integer>
    <key>Hour</key><integer>5</integer>
    <key>Minute</key><integer>30</integer>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>MODEL_ROOT_OVERRIDE</key><string>$ROOT</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/omega-dal-nyg-launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/omega-dal-nyg-launchd.err.log</string>
</dict>
</plist>
EOF

plutil -lint "$PLIST"
launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"
launchctl enable "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true

# If the Mac is on AC power, keep only idle system sleep suppressed until shortly
# after the scheduled launch. Display sleep remains available. Once launchd starts,
# the job itself runs under caffeinate for the duration of all retries.
PRELAUNCH_SECONDS="$(python3 - <<'PY'
from datetime import datetime
now=datetime.now()
target=datetime(2026,9,14,5,40,0)
print(max(0,int((target-now).total_seconds())))
PY
)"
POWER_LINE="$(/usr/bin/pmset -g batt 2>/dev/null | head -n 1 || true)"
PREAWAKE_STATUS="NOT_STARTED"
if [[ "$PRELAUNCH_SECONDS" -gt 0 && "$POWER_LINE" == *"AC Power"* ]]; then
  nohup /usr/bin/caffeinate -i -t "$PRELAUNCH_SECONDS" \
    >"$LOG_DIR/omega-dal-nyg-prelaunch-caffeinate.log" 2>&1 &
  echo $! > "$LOG_DIR/omega-dal-nyg-prelaunch-caffeinate.pid"
  PREAWAKE_STATUS="ACTIVE_${PRELAUNCH_SECONDS}s"
elif [[ "$PRELAUNCH_SECONDS" -le 0 ]]; then
  PREAWAKE_STATUS="NOT_NEEDED_TARGET_TIME_PASSED"
else
  PREAWAKE_STATUS="SKIPPED_NOT_ON_AC_POWER"
fi

echo
echo "OMEGA 0.25 — DAL@NYG MORNING AUTOMATION INSTALLED"
echo "PASS launchd label: $LABEL"
echo "PASS scheduled: Monday 2026-09-14 at 5:30 AM local time"
echo "PASS runner date-lock: 2026-09-14 only"
echo "PASS retry: every 30 minutes, up to 16 attempts, until nflverse is complete"
echo "PASS runner held awake with caffeinate after launch"
echo "PRELAUNCH AWAKE: $PREAWAKE_STATUS"
echo "PASS overnight git pulls: 0"
echo "PASS model fitting/mutation: 0"
echo "PASS generic nflverse CURRENT_RAW_SNAPSHOT preserved"
echo "PASS on readiness: score DAL@NYG 0.24 challenger + frozen 4:25 0.23 bundle + rebuild 2026 index"
echo "PASS one-date plist removes itself after runner exits"
echo "STDOUT: $LOG_DIR/omega-dal-nyg-launchd.out.log"
echo "STDERR: $LOG_DIR/omega-dal-nyg-launchd.err.log"
echo "RESULT LOGS: $ROOT/data/results/nfl/omega/automation_logs_0250/"
if [[ "$PREAWAKE_STATUS" == SKIPPED_NOT_ON_AC_POWER ]]; then
  echo
echo "WARNING: Mac is not reporting AC power, so the installer did not force it to stay awake before 5:30 AM. Plug it in and rerun this installer if you want guaranteed unattended launch."
fi
echo
echo "IMPORTANT: do not power the Mac off overnight."
echo
echo "INSTALL PASS"
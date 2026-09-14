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

echo
echo "OMEGA 0.25 — DAL@NYG MORNING AUTOMATION INSTALLED"
echo "PASS launchd label: $LABEL"
echo "PASS scheduled: Monday 2026-09-14 at 5:30 AM local time"
echo "PASS runner date-lock: 2026-09-14 only"
echo "PASS retry: every 30 minutes, up to 16 attempts, until nflverse is complete"
echo "PASS overnight git pulls: 0"
echo "PASS model fitting/mutation: 0"
echo "PASS on readiness: score DAL@NYG 0.24 challenger + frozen 4:25 0.23 bundle + rebuild 2026 index"
echo "PASS one-date plist removes itself after runner exits"
echo "STDOUT: $LOG_DIR/omega-dal-nyg-launchd.out.log"
echo "STDERR: $LOG_DIR/omega-dal-nyg-launchd.err.log"
echo "RESULT LOGS: $ROOT/data/results/nfl/omega/automation_logs_0250/"
echo
echo "IMPORTANT: the Mac must not be powered off. A sleeping logged-in Mac normally receives a missed StartCalendarInterval job when it wakes; for execution at exactly 5:30 AM, leave it awake."
echo
echo "INSTALL PASS"

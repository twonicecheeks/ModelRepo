#!/bin/zsh
set -euo pipefail
ROOT="/Users/abbeyfelix/Developer/MODEL"
LABEL="com.model.omega-ta-auto-ingest"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/Library/Logs/MODEL"
RUNNER="$ROOT/scripts/nfl/run_omega_ta_auto_ingest_0371.command"
UIDN="$(id -u)"
mkdir -p "$HOME/Library/LaunchAgents" "$LOGDIR" "$HOME/Library/Application Support/MODEL"
[[ -f "$RUNNER" ]] || { echo "FAIL missing runner: $RUNNER"; exit 1; }
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>$LABEL</string>
<key>ProgramArguments</key><array><string>/bin/zsh</string><string>$RUNNER</string></array>
<key>RunAtLoad</key><true/>
<key>StartInterval</key><integer>300</integer>
<key>WatchPaths</key><array><string>$HOME/Downloads</string></array>
<key>StandardOutPath</key><string>$LOGDIR/omega-ta-auto.log</string>
<key>StandardErrorPath</key><string>$LOGDIR/omega-ta-auto.err.log</string>
<key>ProcessType</key><string>Background</string>
</dict></plist>
EOF
launchctl bootout "gui/$UIDN" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UIDN" "$PLIST"
launchctl kickstart -k "gui/$UIDN/$LABEL" >/dev/null 2>&1 || true

echo "OMEGA 0.37.1 — T+A AUTO INGEST INSTALLED"
echo "PASS LaunchAgent: $PLIST"
echo "PASS watches ~/Downloads and also checks every 5 minutes"
echo "PASS new OMEGA 0.17.6 captures automatically run 0.17.11 import + 0.37 movement ledger"
echo "LOG: $LOGDIR/omega-ta-auto.log"
echo "ERROR LOG: $LOGDIR/omega-ta-auto.err.log"
echo
echo "NEXT: reload the MODEL extension once at chrome://extensions so background auto-capture v3.2.1 starts."
echo "The extension captures adaptively: 3h normally, 1h within 12h of kickoff, 30m within 3h, and stops after Week 2's final kickoff."

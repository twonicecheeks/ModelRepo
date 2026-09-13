# OMEGA 0.17.3 — PropsMadness NFL T+A File-Handoff Probe Hotfix

Purpose: remove Chrome clipboard-write permission as a failure point from the one-time NFL T+A endpoint discovery step.

Changes from 0.17.2:
- browser capture is downloaded as a JSON file;
- an on-page orange manual download button is installed as fallback;
- terminal importer reads the newest matching JSON in `~/Downloads`, or an explicit `--file` path;
- clipboard is used only to paste the probe code into DevTools, not to export captured data.

No market normalization is performed. No OMEGA-I artifact is read or written. No credentials, cookies, authorization headers, or request headers are captured.

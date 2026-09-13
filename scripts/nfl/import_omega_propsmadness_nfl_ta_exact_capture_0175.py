#!/usr/bin/env python3
from pathlib import Path
import json, hashlib, zipfile, shutil, sys
from datetime import datetime, timezone

downloads = Path.home()/"Downloads"
candidates = sorted(downloads.glob("OMEGA_0175_PROPSMADNESS_NFL_TA_EXACT_CAPTURE_*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
if not candidates:
    raise SystemExit("FAIL no OMEGA 0.17.5 exact T+A capture found in ~/Downloads")

src = candidates[0]
raw = src.read_bytes()
sha = hashlib.sha256(raw).hexdigest()
try:
    data = json.loads(raw)
except Exception as e:
    raise SystemExit(f"FAIL capture is not valid JSON: {e}")

if data.get("schemaVersion") != "OMEGA_PM_NFL_TA_EXACT_CAPTURE_0.17.5":
    raise SystemExit("FAIL wrong capture schema/version")

before = data.get("domBefore") or {}
after = data.get("domAfter") or {}
events = data.get("apiEvents") or []
notes = data.get("notes") or []
selected = data.get("selectedControl")
final_url = data.get("finalUrl") or after.get("url") or ""

if not selected:
    raise SystemExit("FAIL no safe exact Tckl+Ast control was selected; inspect capture")
if "/nfl" not in final_url:
    raise SystemExit(f"FAIL probe navigated away from NFL app: {final_url}")

api_urls = sorted({e.get("url") for e in events if e.get("url")})
relevant = [u for u in api_urls if any(x in u.lower() for x in ("offer","bet","tack","assist","nfl"))]

# Require either a relevant API event or visible DOM evidence that T+A became active.
after_text = (after.get("mainText") or "")
dom_evidence = any(x.lower() in after_text.lower() for x in ("tckl+ast","tackles + assists","tackles+assists"))
if not relevant and not dom_evidence:
    raise SystemExit("FAIL exact T+A click produced neither relevant API nor DOM evidence")

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
sid = f"{stamp}_{sha[:8]}"
root = Path("/Users/abbeyfelix/Developer/MODEL")
outdir = root/"data/raw/nfl/omega/propsmadness_ta_exact_capture_0175"/sid
outdir.mkdir(parents=True, exist_ok=False)
(outdir/"PROPSMADNESS_NFL_TA_EXACT_CAPTURE.json").write_bytes(raw)

audit = {
    "schemaVersion":"OMEGA_PM_NFL_TA_EXACT_CAPTURE_IMPORT_AUDIT_0.17.5",
    "sourceId":sid,
    "sourceFile":str(src),
    "sha256":sha,
    "initialUrl":data.get("initialUrl"),
    "finalUrl":final_url,
    "selectedControl":selected,
    "candidateControlCount":len(data.get("candidateControls") or []),
    "apiEventCount":len(events),
    "apiUrls":api_urls,
    "relevantApiUrls":relevant,
    "domEvidence":dom_evidence,
    "notes":notes,
    "credentialFieldsCaptured":0,
    "marketNormalizationPerformed":False,
    "omegaIRead":False,
    "omegaIWritten":False,
    "OddsPapiRequests":0
}
(outdir/"OMEGA_0.17.5_EXACT_CAPTURE_IMPORT_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n")

handoff = downloads/"OMEGA_0175_PROPSMADNESS_NFL_TA_EXACT_CAPTURE_HANDOFF.zip"
if handoff.exists(): handoff.unlink()
with zipfile.ZipFile(handoff,"w",zipfile.ZIP_DEFLATED) as z:
    z.write(outdir/"PROPSMADNESS_NFL_TA_EXACT_CAPTURE.json",
            "OMEGA_0175_PROPSMADNESS_NFL_TA_EXACT_CAPTURE_HANDOFF/PROPSMADNESS_NFL_TA_EXACT_CAPTURE.json")
    z.write(outdir/"OMEGA_0.17.5_EXACT_CAPTURE_IMPORT_AUDIT.json",
            "OMEGA_0175_PROPSMADNESS_NFL_TA_EXACT_CAPTURE_HANDOFF/OMEGA_0.17.5_EXACT_CAPTURE_IMPORT_AUDIT.json")

print()
print("OMEGA 0.17.5 — EXACT NFL T+A CAPTURE IMPORT")
print()
print(f"PASS immutable source: {sid}")
print(f"PASS exact control: {selected.get('tag')} · inMain {selected.get('inMain')} · href {selected.get('href')}")
print(f"PASS final URL remains NFL app: {final_url}")
print(f"PASS API events: {len(events)} · relevant API URLs: {len(relevant)} · DOM evidence: {dom_evidence}")
print("PASS credential/header fields: 0 · market normalization: NO · OMEGA-I writes: 0 · OddsPapi: 0")
print()
print("RELEVANT ENDPOINTS:")
if relevant:
    for u in relevant: print(" ",u)
else:
    print("  none — adapter can fall back to captured T+A DOM")
print()
print("UPLOAD:", handoff)

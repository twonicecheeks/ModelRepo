from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, shutil, zipfile
from pathlib import Path

SCHEMA='OMEGA_PM_NFL_TA_PROBE_0.17.3'
PREFIX='OMEGA_0173_PROPSMADNESS_NFL_TA_CAPTURE_'
FORBIDDEN=re.compile(r'(authorization|cookie|set-cookie|api[_-]?key|access[_-]?token|refresh[_-]?token)',re.I)

def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def iso(): return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def sid_from(raw): return dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+sha256_bytes(raw)[:8]

def newest_capture(downloads: Path) -> Path | None:
    files=[p for p in downloads.glob(PREFIX+'*.json') if p.is_file()]
    return max(files,key=lambda p:p.stat().st_mtime) if files else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--file',default=None,help='Explicit downloaded probe JSON path')
    a=ap.parse_args()
    root=Path(a.root)
    src=Path(a.file).expanduser() if a.file else newest_capture(Path.home()/'Downloads')
    if src is None: raise SystemExit('FAIL no OMEGA 0.17.3 capture JSON found in ~/Downloads; rerun the browser probe and use the orange download button if needed')
    if not src.exists(): raise SystemExit(f'FAIL capture file not found: {src}')
    raw=src.read_bytes()
    if not raw.strip(): raise SystemExit(f'FAIL capture file is empty: {src}')
    try: d=json.loads(raw)
    except Exception as e: raise SystemExit(f'FAIL capture file is not valid JSON ({src}): {e}')
    if d.get('schemaVersion')!=SCHEMA: raise SystemExit(f"FAIL wrong schema in {src.name}: {d.get('schemaVersion')!r}")
    if FORBIDDEN.search(raw.decode('utf-8','ignore')): raise SystemExit('FAIL capture contains a forbidden credential/header field')
    ev=d.get('events') or []
    full=[x for x in ev if x.get('responseData') is not None or x.get('responseTextFallback') is not None]
    if not ev: raise SystemExit('FAIL no relevant API events captured; rerun probe on PropsMadness NFL page')
    if not full: raise SystemExit('FAIL no full NFL/T+A payload captured; rerun probe and ensure Tckl+Ast loads')
    urls=sorted({str(x.get('url') or '') for x in ev})
    sid=sid_from(raw)
    base=root/'data/raw/nfl/omega/propsmadness_ta_probe'/sid
    if base.exists(): raise SystemExit(f'FAIL immutable capture already exists: {base}')
    tmp=base.with_name(base.name+'.staging'); tmp.mkdir(parents=True,exist_ok=False)
    try:
        (tmp/'PROPSMADNESS_NFL_TA_PROBE.json').write_bytes(raw)
        audit={
          'schemaVersion':'OMEGA_PM_NFL_TA_PROBE_IMPORT_AUDIT_0.17.3','capturedAt':iso(),'sourceId':sid,
          'sourceFile':str(src),'probeSha256':sha256_bytes(raw),'eventCount':len(ev),'fullPayloadCount':len(full),'urls':urls,
          'credentialFieldsCaptured':0,'marketNormalizationPerformed':False,'omegaIRead':False,'omegaIWritten':False,
          'OddsPapiRequests':0
        }
        (tmp/'OMEGA_0.17.3_PROBE_IMPORT_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
        os.replace(tmp,base)
    except Exception:
        shutil.rmtree(tmp,ignore_errors=True); raise
    hand=Path.home()/'Downloads'/'OMEGA_0173_PROPSMADNESS_NFL_TA_CAPTURE_HANDOFF.zip'
    if hand.exists(): hand.unlink()
    with zipfile.ZipFile(hand,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(base/'PROPSMADNESS_NFL_TA_PROBE.json','OMEGA_0173_PROPSMADNESS_NFL_TA_CAPTURE_HANDOFF/PROPSMADNESS_NFL_TA_PROBE.json')
        z.write(base/'OMEGA_0.17.3_PROBE_IMPORT_AUDIT.json','OMEGA_0173_PROPSMADNESS_NFL_TA_CAPTURE_HANDOFF/OMEGA_0.17.3_PROBE_IMPORT_AUDIT.json')
    print('OMEGA 0.17.3 — PROPSMADNESS NFL T+A FILE-HANDOFF IMPORT')
    print(f'PASS source file: {src}')
    print(f'PASS immutable probe snapshot: {sid}')
    print(f'PASS API events: {len(ev)} · full payloads: {len(full)}')
    print('PASS credential/header fields: 0 · market normalization: NO · OMEGA-I writes: 0 · OddsPapi: 0')
    print('ENDPOINTS:')
    for u in urls: print('  '+u)
    print(f'UPLOAD: {hand}')
if __name__=='__main__': main()

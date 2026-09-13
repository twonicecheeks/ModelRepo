from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, re, shutil, zipfile
from pathlib import Path
SCHEMA='OMEGA_PM_NFL_TA_DISCOVERY_0.17.4'
PREFIX='OMEGA_0174_PROPSMADNESS_NFL_TA_DISCOVERY_'
FORBIDDEN=re.compile(r'("|\b)(authorization|cookie|set-cookie|api[_-]?key|access[_-]?token|refresh[_-]?token|password)("|\b)\s*:',re.I)
def sha(b): return hashlib.sha256(b).hexdigest()
def now(): return dt.datetime.now(dt.timezone.utc)
def newest(d):
    fs=[p for p in d.glob(PREFIX+'*.json') if p.is_file()]
    return max(fs,key=lambda p:p.stat().st_mtime) if fs else None
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL'); ap.add_argument('--file'); a=ap.parse_args()
    root=Path(a.root); src=Path(a.file).expanduser() if a.file else newest(Path.home()/'Downloads')
    if src is None or not src.exists(): raise SystemExit('FAIL no OMEGA 0.17.4 discovery JSON found in ~/Downloads')
    raw=src.read_bytes()
    try: d=json.loads(raw)
    except Exception as e: raise SystemExit(f'FAIL invalid discovery JSON: {e}')
    if d.get('schemaVersion')!=SCHEMA: raise SystemExit(f"FAIL wrong schema: {d.get('schemaVersion')!r}")
    txt=raw.decode('utf-8','ignore')
    if FORBIDDEN.search(txt): raise SystemExit('FAIL capture contains forbidden credential/header field')
    api=d.get('apiEvents') or []; perf=d.get('performanceResources') or []; dom=d.get('domSnapshots') or []; js=d.get('jsonState') or []
    perf_n=sum(len(x.get('resources') or []) for x in perf); dom_n=sum(len(x.get('relevantBlocks') or []) for x in dom); js_n=sum(len(x.get('items') or []) for x in js)
    if not (api or perf_n or dom_n or js_n): raise SystemExit('FAIL discovery capture is empty across API/performance/DOM/JSON-state channels')
    urls=sorted({str(x.get('url') or '') for x in api if x.get('url')})
    perf_urls=sorted({str(r.get('name') or '') for x in perf for r in (x.get('resources') or []) if r.get('name')})
    stamp=now().strftime('%Y%m%dT%H%M%SZ'); sid=f'{stamp}_{sha(raw)[:8]}'
    base=root/'data/raw/nfl/omega/propsmadness_ta_discovery'/sid; tmp=base.with_name(base.name+'.staging')
    if base.exists(): raise SystemExit(f'FAIL immutable discovery already exists: {base}')
    tmp.mkdir(parents=True)
    try:
        (tmp/'PROPSMADNESS_NFL_TA_DISCOVERY.json').write_bytes(raw)
        audit={'schemaVersion':'OMEGA_PM_NFL_TA_DISCOVERY_IMPORT_AUDIT_0.17.4','sourceId':sid,'sourceFile':str(src),'sha256':sha(raw),
               'apiEventCount':len(api),'performanceResourceCount':perf_n,'relevantDomBlockCount':dom_n,'jsonStateItemCount':js_n,
               'apiUrls':urls,'performanceUrls':perf_urls,'credentialFieldsCaptured':0,'marketNormalizationPerformed':False,
               'omegaIRead':False,'omegaIWritten':False,'OddsPapiRequests':0}
        (tmp/'OMEGA_0.17.4_DISCOVERY_IMPORT_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
        os.replace(tmp,base)
    except Exception:
        shutil.rmtree(tmp,ignore_errors=True); raise
    hand=Path.home()/'Downloads'/'OMEGA_0174_PROPSMADNESS_NFL_TA_DISCOVERY_HANDOFF.zip'
    if hand.exists(): hand.unlink()
    with zipfile.ZipFile(hand,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(base/'PROPSMADNESS_NFL_TA_DISCOVERY.json','OMEGA_0174_PROPSMADNESS_NFL_TA_DISCOVERY_HANDOFF/PROPSMADNESS_NFL_TA_DISCOVERY.json')
        z.write(base/'OMEGA_0.17.4_DISCOVERY_IMPORT_AUDIT.json','OMEGA_0174_PROPSMADNESS_NFL_TA_DISCOVERY_HANDOFF/OMEGA_0.17.4_DISCOVERY_IMPORT_AUDIT.json')
    print('OMEGA 0.17.4 — PROPSMADNESS BROAD NFL T+A DISCOVERY IMPORT')
    print(f'PASS source file: {src}')
    print(f'PASS immutable discovery snapshot: {sid}')
    print(f'PASS API events {len(api)} · performance resources {perf_n} · relevant DOM blocks {dom_n} · JSON-state items {js_n}')
    print('PASS credential/header fields 0 · market normalization NO · OMEGA-I writes 0 · OddsPapi 0')
    if urls:
        print('API ENDPOINTS:'); [print('  '+u) for u in urls]
    else: print('API ENDPOINTS: none captured (preloaded/performance/DOM channels retained)')
    print(f'UPLOAD: {hand}')
if __name__=='__main__': main()

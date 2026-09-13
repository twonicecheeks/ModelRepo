#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, zipfile

EXPECTED_LEDGER_SHA = 'fe4991a743a1c02994b59d473a1bec9a1ccafa61a60548df43f2f5292e4ca08a'
EXPECTED_PROVIDER_FILES = [
    'packages/providers/propsmadness/table-probe/propsmadness_table_probe_main.js',
    'packages/providers/propsmadness/table-probe/propsmadness_table_probe.js',
    'packages/providers/propsmadness/src/table_core.js',
    'packages/providers/propsmadness/src/table_main.js',
]
KEYWORDS = ('nfl','tackle','assist','player','book','odds','price','line','market','table','sport','grade','pinnacle','fanduel','circa','event','game')
SECRET_RE = re.compile(r'(?i)(api[_-]?key|authorization|bearer|password|passwd|secret|token)\s*[:=]\s*[\"\']([^\"\']+)[\"\']')
URL_RE = re.compile(r'https?://[^\"\'\s)]+')
REQUIRE_RE = re.compile(r'(?:require\s*\(\s*[\"\']([^\"\']+)[\"\']\s*\)|from\s+[\"\']([^\"\']+)[\"\'])')
OBJKEY_RE = re.compile(r'(?<![\w$])([A-Za-z_$][\w$]{1,48})\s*:')
STRINGKEY_RE = re.compile(r'[\"\']([A-Za-z0-9_.$-]{2,50})[\"\']\s*:')

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def sha(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def read_text(path: Path):
    return path.read_text(encoding='utf-8', errors='replace')

def sanitize_source(text: str):
    # Fail closed on likely embedded credentials. We don't silently redact provider behavior.
    hits=[]
    for m in SECRET_RE.finditer(text):
        val=m.group(2).strip()
        if val and len(val) >= 8 and not any(x in val.lower() for x in ('process.env','keychain','placeholder','example','your_','${')):
            hits.append(m.group(1))
    return sorted(set(hits))

def line_clues(text: str, max_lines=120):
    out=[]
    for i,line in enumerate(text.splitlines(),1):
        lo=line.lower()
        if any(k in lo for k in KEYWORDS):
            clipped=line.strip()
            if len(clipped)>260: clipped=clipped[:257]+'...'
            out.append({'line':i,'text':clipped})
            if len(out)>=max_lines: break
    return out

def analyze_js(path: Path, root: Path):
    text=read_text(path)
    urls=sorted(set(URL_RE.findall(text)))[:50]
    deps=[]
    for a,b in REQUIRE_RE.findall(text):
        deps.append(a or b)
    keys=sorted(set(OBJKEY_RE.findall(text)) | set(STRINGKEY_RE.findall(text)))
    likely=[k for k in keys if any(x in k.lower() for x in KEYWORDS)]
    exports=[]
    for pat in (r'module\.exports\s*=\s*\{([^}]{0,2000})\}', r'exports\.([A-Za-z_$][\w$]*)\s*=', r'export\s+(?:async\s+)?(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)'):
        for m in re.finditer(pat,text,re.S):
            exports.append(m.group(1).strip()[:1000])
    return {
        'path': str(path.relative_to(root)),
        'bytes': path.stat().st_size,
        'sha256': sha(path),
        'embeddedCredentialIndicators': sanitize_source(text),
        'urls': urls,
        'dependencies': sorted(set(deps)),
        'likelyObjectKeys': likely[:200],
        'exportsClues': exports[:30],
        'keywordLineClues': line_clues(text),
    }

def node_check(path: Path):
    node=shutil.which('node')
    if not node:
        return {'available':False,'status':'NOT_RUN','detail':'node not found'}
    p=subprocess.run([node,'--check',str(path)],capture_output=True,text=True)
    return {'available':True,'status':'PASS' if p.returncode==0 else 'FAIL','detail':(p.stderr or p.stdout).strip()[:2000]}

def repo_refs(root: Path):
    hits=[]
    ignore_parts={'.git','node_modules','__pycache__','.venv','venv','data'}
    exts={'.js','.mjs','.cjs','.ts','.py','.command','.sh','.json','.md'}
    for base in (root/'scripts',root/'packages',root/'docs'):
        if not base.exists(): continue
        for p in base.rglob('*'):
            if not p.is_file() or p.suffix.lower() not in exts: continue
            if any(part in ignore_parts for part in p.parts): continue
            try:
                if p.stat().st_size>2_000_000: continue
                text=read_text(p)
            except Exception: continue
            if 'propsmadness' not in text.lower() and 'propsmadness' not in p.name.lower(): continue
            for i,line in enumerate(text.splitlines(),1):
                lo=line.lower()
                if 'propsmadness' in lo or 'table-probe' in lo or 'table_core' in lo or 'table_main' in lo:
                    s=line.strip()
                    if len(s)>320:s=s[:317]+'...'
                    hits.append({'path':str(p.relative_to(root)),'line':i,'text':s})
                    if len(hits)>=300:return hits
    return hits

def verify_ledger(root: Path):
    ptr=root/'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER'
    if not ptr.exists(): raise SystemExit('FAIL current OMEGA probability-ledger pointer missing')
    sid=ptr.read_text().strip()
    hp=root/'data/prospective/nfl/omega/tackle_probability_016'/sid/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.sha256'
    if not hp.exists(): raise SystemExit('FAIL current OMEGA probability-ledger hash missing')
    digest=hp.read_text().strip()
    if digest!=EXPECTED_LEDGER_SHA:
        raise SystemExit(f'FAIL unexpected OMEGA-I ledger hash {digest}; expected {EXPECTED_LEDGER_SHA}')
    return sid,digest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--output',default=str(Path.home()/'Downloads'/'OMEGA_0171_PROPSMADNESS_PROVIDER_HANDOFF.zip'))
    a=ap.parse_args(); root=Path(a.root).resolve(); out=Path(a.output).expanduser().resolve()
    sid,digest=verify_ledger(root)
    missing=[rel for rel in EXPECTED_PROVIDER_FILES if not (root/rel).exists()]
    if missing: raise SystemExit('FAIL expected PropsMadness provider files missing:\n  '+'\n  '.join(missing))
    analyses=[]
    credential_files=[]
    for rel in EXPECTED_PROVIDER_FILES:
        info=analyze_js(root/rel,root); info['nodeCheck']=node_check(root/rel); analyses.append(info)
        if info['embeddedCredentialIndicators']: credential_files.append((rel,info['embeddedCredentialIndicators']))
    if credential_files:
        details='; '.join(f'{p}: {x}' for p,x in credential_files)
        raise SystemExit('FAIL possible embedded credential(s) detected; handoff not created: '+details)
    refs=repo_refs(root)
    tmp=Path(tempfile.mkdtemp(prefix='omega0171_'))
    bundle=tmp/'OMEGA_0171_PROPSMADNESS_PROVIDER_HANDOFF'; bundle.mkdir()
    try:
        src=bundle/'provider_source'
        for rel in EXPECTED_PROVIDER_FILES:
            dest=src/rel; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(root/rel,dest)
        report={
            'schemaVersion':'OMEGA_PROPSMADNESS_ADAPTER_DISCOVERY_0.17.1',
            'generatedAt':now_iso(),
            'networkRequests':0,
            'omegaLedgerId':sid,
            'omegaLedgerSha256':digest,
            'providerFiles':analyses,
            'repoCallsiteClues':refs,
            'purpose':'Code-only handoff to design a canonical NFL tackles+assists adapter against the installed PropsMadness provider contract. No market data or model outputs are captured here.',
        }
        (bundle/'OMEGA_0.17.1_PROPSMADNESS_PROVIDER_DISCOVERY.json').write_text(json.dumps(report,indent=2)+'\n')
        md=[
            '# OMEGA 0.17.1 — PropsMadness Adapter Discovery', '',
            f'Generated: {report["generatedAt"]}', '',
            f'OMEGA-I ledger SHA256: `{digest}`', '',
            'Network requests: **0**', '',
            'This bundle contains only the existing PropsMadness provider source and static call-site/schema clues. It does not capture sportsbook data, run a browser, call OddsPapi, or modify OMEGA-I.', '',
            '## Provider files',
        ]
        for x in analyses:
            md += [f'- `{x["path"]}` — {x["bytes"]} bytes — `{x["sha256"]}` — node syntax {x["nodeCheck"]["status"]}']
        md += ['',f'Call-site clues found: **{len(refs)}**','', 'Next step: build an adapter that emits only the OMEGA 0.17 raw market schema, then capture a timestamped T+A snapshot and run the downstream comparison.', '']
        (bundle/'README.md').write_text('\n'.join(md))
        if out.exists(): out.unlink()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for p in bundle.rglob('*'):
                if p.is_file(): z.write(p,p.relative_to(tmp))
    finally:
        shutil.rmtree(tmp,ignore_errors=True)
    print('OMEGA 0.17.1 — PROPSMADNESS ADAPTER DISCOVERY')
    print(f'PASS pinned OMEGA-I ledger: {digest}')
    print(f'PASS provider files captured: {len(analyses)}')
    print(f'PASS repo PropsMadness call-site clues: {len(refs)}')
    print('PASS embedded credential indicators: 0')
    print('PASS network requests: 0 · OddsPapi requests: 0 · market rows captured: 0')
    print(f'UPLOAD: {out}')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

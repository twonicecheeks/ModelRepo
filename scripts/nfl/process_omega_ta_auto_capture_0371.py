#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, subprocess, sys

ROOT=Path('/Users/abbeyfelix/Developer/MODEL')
DOWNLOADS=Path.home()/'Downloads'
APP=Path.home()/'Library'/'Application Support'/'MODEL'
STATE=APP/'omega_ta_auto_state.json'
LOCK=APP/'omega_ta_auto_ingest.lock'
PATTERN='OMEGA_0176_PROPSMADNESS_NFL_TA_DIRECT_CAPTURE_*.json'


def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sha(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def load_state():
    try:return json.loads(STATE.read_text())
    except Exception:return {}
def save_state(x):
    APP.mkdir(parents=True,exist_ok=True)
    tmp=STATE.with_suffix('.tmp'); tmp.write_text(json.dumps(x,indent=2)+'\n'); os.replace(tmp,STATE)

def main():
    APP.mkdir(parents=True,exist_ok=True)
    try: LOCK.mkdir()
    except FileExistsError:
        print('NOOP auto-ingest already running'); return 0
    try:
        files=sorted(DOWNLOADS.glob(PATTERN),key=lambda p:p.stat().st_mtime,reverse=True)
        if not files:
            print('NOOP no automated/manual OMEGA 0.17.6 capture in Downloads'); return 0
        src=files[0]; digest=sha(src); state=load_state()
        if state.get('lastSuccessfulSha256')==digest:
            print(f'NOOP latest capture already processed · {src.name}'); return 0
        print(f'OMEGA 0.37.1 AUTO INGEST · processing {src.name} · sha {digest[:12]}')
        env=dict(os.environ); env['OMEGA_TA_AUTO_CAPTURE_FILE']=str(src)
        cmds=[
            ['zsh',str(ROOT/'scripts/nfl/import_omega_propsmadness_nfl_ta_direct_01711.command')],
            ['zsh',str(ROOT/'scripts/nfl/build_omega_ta_reference_market_movement_0370.command')],
        ]
        for cmd in cmds:
            r=subprocess.run(cmd,cwd=ROOT,env=env,text=True)
            if r.returncode!=0:
                state.update({'lastAttemptAt':now(),'lastAttemptFile':str(src),'lastAttemptSha256':digest,'lastStatus':'FAIL','failedCommand':' '.join(cmd)})
                save_state(state); return r.returncode
        state.update({'lastAttemptAt':now(),'lastSuccessfulAt':now(),'lastSuccessfulFile':str(src),'lastSuccessfulSha256':digest,'lastStatus':'PASS'})
        save_state(state)
        print('PASS automated capture imported and OMEGA 0.37 movement ledger rebuilt')
        return 0
    finally:
        try: LOCK.rmdir()
        except Exception: pass

if __name__=='__main__': raise SystemExit(main())

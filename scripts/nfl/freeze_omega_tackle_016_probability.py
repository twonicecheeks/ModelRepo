#!/usr/bin/env python3
"""Freeze the OMEGA 0.15 NB_ROLE distribution for prospective 2026 use."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,shutil

SCHEMA='OMEGA_TACKLE_PROBABILITY_FROZEN_0.16'
EXPECTED_MEAN_SHA='c2ca80b6a144c3aa86bc41bdb82f6f5618ffa279a38f4c6d358025ed7fbd69fb'
ROLE_TIERS=('LOW','ROTATIONAL','STARTER','EVERY_DOWN')

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def validate(spec,audit):
 if spec.get('frozenMeanSpecSha256')!=EXPECTED_MEAN_SHA: raise ValueError('frozen mean hash drift')
 if spec.get('selectedArchitecture')!='NB_ROLE': raise ValueError('0.15 selected architecture is not NB_ROLE')
 integ=audit.get('integrity',{})
 if int(integ.get('omega2025OutcomeRowsRead',-1))!=0: raise ValueError('2025 outcome rows were used')
 if int(integ.get('marketFieldsRead',-1))!=0 or int(integ.get('oddsPapiRequests',-1))!=0: raise ValueError('market contamination')
 c=audit.get('confirmation2024',{})
 if c.get('label')!='CONFIRMATION_BOTH_IMPROVE': raise ValueError('2024 confirmation did not improve both metrics')
 if float(c.get('selectedVsPoissonCountNLLImprovement',0))<=0 or float(c.get('selectedVsPoissonThresholdBrierImprovement',0))<=0: raise ValueError('confirmation deltas not both positive')
 params=spec.get('distribution',{}).get('productionResearchParamsFitThrough2024') or {}
 for k in ('globalSize',)+tuple('size_'+x for x in ROLE_TIERS):
  if k not in params or float(params[k])<=0: raise ValueError(f'missing/invalid distribution parameter {k}')
 return params

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL'); a=ap.parse_args(); root=Path(a.root).resolve()
 ptr=root/'data/models/nfl/CURRENT_OMEGA_TACKLE_DISTRIBUTION'
 if not ptr.exists(): raise SystemExit('FAIL OMEGA 0.15 distribution pointer missing')
 sid=ptr.read_text().strip(); d=root/'data/models/nfl/omega_tackle_015_distribution'/sid
 sp=d/'OMEGA_0.15_DISTRIBUTION_SPEC.json'; au=d/'OMEGA_0.15_DISTRIBUTION_AUDIT.json'
 if not sp.exists() or not au.exists(): raise SystemExit('FAIL OMEGA 0.15 spec/audit missing')
 spec=json.loads(sp.read_text()); audit=json.loads(au.read_text())
 try: params=validate(spec,audit)
 except Exception as e: raise SystemExit(f'FAIL OMEGA 0.15 freeze validation: {e}')
 outbase=root/'data/models/nfl/omega_tackle_016_probability_frozen'; out=outbase/sid
 if out.exists():
  fp=out/'OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json'; hp=out/'OMEGA_0.16_PROBABILITY_FROZEN_SPEC.sha256'
  if fp.exists() and hp.exists() and hp.read_text().strip()==sha(fp):
   (root/'data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN').write_text(sid+'\n'); print(f'PASS existing immutable OMEGA 0.16 probability freeze verified: {out}'); return 0
  raise SystemExit(f'FAIL incomplete/corrupt existing OMEGA 0.16 freeze: {out}')
 st=outbase/('.'+sid+'.staging'); st.mkdir(parents=True,exist_ok=False)
 obj={
  'schemaVersion':SCHEMA,'frozenAt':now(),'sourceSnapshotId':sid,
  'status':'FROZEN_FOR_2026_PROSPECTIVE_RESEARCH_ONLY','independentMeanSpecSha256':EXPECTED_MEAN_SHA,
  'source015SpecSha256':sha(sp),'source015AuditSha256':sha(au),'distributionFamily':'NB_ROLE',
  'parameterization':'NB2 variance=mean+mean^2/size','distributionParamsFitThrough2024':params,
  'roleTierDefinition':{'LOW':'<0.35','ROTATIONAL':'0.35-<0.65','STARTER':'0.65-<0.85','EVERY_DOWN':'>=0.85'},
  'roleTierInput':'H012 predicted snap share only','halfPointLines':[x+0.5 for x in range(15)],
  'selectionEvidence':{'cv2021to2023':audit.get('chronologicalSelectionSummary'),'confirmation2024':audit.get('confirmation2024',{}).get('label')},
  'permanentBoundaries':[
   'H008+H012 mean architecture and coefficients remain frozen; no 2025 retuning.',
   '2025 may be used only as strictly-prior realized football state for 2026 prospective predictions, never for parameter tuning.',
   'Sportsbook prices never enter the independent OMEGA-I prediction/distribution path.',
   'NFLverse-only availability/depth state is secondary-source research context and cannot establish VERIFIED game-day availability.',
   '2026 predictions must be timestamped and immutable before their target games kick off.'
  ]
 }
 fp=st/'OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json'; fp.write_text(json.dumps(obj,indent=2)+'\n'); digest=sha(fp); (st/'OMEGA_0.16_PROBABILITY_FROZEN_SPEC.sha256').write_text(digest+'\n')
 os.replace(st,out); (root/'data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN').write_text(sid+'\n')
 print('OMEGA 0.16 — PROBABILITY FREEZE')
 print('PASS selected distribution NB_ROLE frozen for 2026 prospective research')
 print(f'PASS source 0.15 spec SHA256: {sha(sp)}')
 print(f'PASS frozen probability spec SHA256: {digest}')
 print('PASS 2025 tuning rows 0 · market fields 0 · OddsPapi 0 · network 0')
 print(f'SPEC: {out/"OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json"}')
 return 0
if __name__=='__main__': raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import uuid


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def canonical_bytes(obj: dict) -> bytes:
    return (json.dumps(obj,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name('.'+path.name+'.tmp')
    tmp.write_text(text.rstrip()+'\n',encoding='utf-8')
    os.replace(tmp,path)


def main() -> int:
    ap=argparse.ArgumentParser(description='Promote frozen QB passing-yards model to 2026 prospective shadow after confirmatory 2025 pass')
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    args=ap.parse_args(); root=Path(args.root).expanduser().resolve()
    model_dir=root/'packages/models/nfl/game'; provider_dir=root/'packages/providers/nflverse/src'
    sys.path.insert(0,str(model_dir)); sys.path.insert(0,str(provider_dir))
    import qb_passing_yards_promotion_023 as q23
    import contract

    freeze_ptr=root/'data/models/nfl/CURRENT_QB_MODEL_021'
    holdout_ptr=root/'data/models/nfl/CURRENT_QB_MODEL_0221'
    if not freeze_ptr.exists() or not holdout_ptr.exists():
        raise FileNotFoundError('required frozen model / completed holdout pointers missing')

    freeze_dir=root/freeze_ptr.read_text(encoding='utf-8').strip()
    holdout_dir=root/holdout_ptr.read_text(encoding='utf-8').strip()
    freeze_path=freeze_dir/'NFL_QB_PASSING_YARDS_FROZEN_SPEC.json'
    freeze_sha_path=freeze_dir/'NFL_QB_PASSING_YARDS_FROZEN_SPEC.sha256'
    holdout_path=holdout_dir/'NFL_QB_PASSING_YARDS_2025_HOLDOUT_AUDIT.json'
    pred_path=holdout_dir/'NFL_QB_PASSING_YARDS_2025_HOLDOUT_PREDICTIONS.jsonl'
    for p in (freeze_path,freeze_sha_path,holdout_path,pred_path):
        if not p.exists(): raise FileNotFoundError(f'promotion source missing: {p}')

    freeze=json.loads(freeze_path.read_text(encoding='utf-8'))
    holdout=json.loads(holdout_path.read_text(encoding='utf-8'))
    expected_sha=freeze_sha_path.read_text(encoding='utf-8').strip().split()[0]
    actual_sha=hashlib.sha256(canonical_bytes(freeze)).hexdigest()
    if expected_sha!=actual_sha or holdout.get('frozenSpecSha256')!=actual_sha:
        raise ValueError('0.2.3 frozen-spec hash drift')

    holdout_role=contract.season_role(2025)
    q23.assert_promotable(holdout,freeze,holdout_role)
    status=q23.promotion_status()

    metrics=holdout['metrics']; boot=holdout['candidateVsBaselineMae']; coverage=holdout['frozenResidualIntervalCoverage']
    spec={
        'version':q23.VERSION,'lineage':q23.LINEAGE,
        'status':status['status'],'frozenCandidate':q23.FROZEN_CANDIDATE,
        'sourceFreezeDirectory':str(freeze_dir.relative_to(root)),
        'sourceHoldoutDirectory':str(holdout_dir.relative_to(root)),
        'frozenSpecSha256':actual_sha,'model':freeze['model'],
        'featureNames':freeze['featureNames'],'fixedL2':freeze['fixedL2'],
        'residualCalibration':freeze['residualCalibration'],
        'target':'official_passing_yards','identityMode':freeze['identityMode'],
        'developmentTrainingSeasons':freeze['trainingSeasons'],
        'holdoutSeason':2025,'holdoutDisposition':holdout['holdoutDisposition'],
        'holdoutFitPolicy':holdout_role,'holdoutUsedForCoefficientFit':False,
        'holdoutMayBeLaggedFeatureHistoryFor2026':True,
        'prospectiveSeason':2026,'prospectiveOutcomeRead':False,
        'marketDependency':False,'marketFieldsAllowed':False,'oddsPapiRequests':0,
        'frozenOmegaMutationAllowed':False,'marketExecutionEligible':False,
        'requiresVerifiedTargetQbIdentity':True,'requiresAsOfPregameFeatureSnapshot':True,
        'postHoldoutRefitPerformed':False,'postHoldoutReselectionPerformed':False,
        'nextGate':'BUILD_2026_ASOF_QB_PASSING_YARDS_SCORER_WITH_VERIFIED_IDENTITY',
    }
    spec_sha=hashlib.sha256(canonical_bytes(spec)).hexdigest()
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    out_dir=root/'data/models/nfl/qb_model_023'/run_id; out_dir.mkdir(parents=True,exist_ok=False)
    spec_path=out_dir/'NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.json'; spec_path.write_bytes(canonical_bytes(spec))
    (out_dir/'NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.sha256').write_text(spec_sha+'  NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.json\n',encoding='utf-8')
    manifest={
        'version':q23.VERSION,'lineage':q23.LINEAGE,'createdAt':datetime.now(timezone.utc).isoformat(),'runId':run_id,
        'promotionSpecSha256':spec_sha,'frozenSpecSha256':actual_sha,
        'sourceHashes':{'freezeSpec':sha256_file(freeze_path),'holdoutAudit':sha256_file(holdout_path),'holdoutPredictions':sha256_file(pred_path)},
        'holdoutDisposition':holdout['holdoutDisposition'],'holdoutRows':holdout['holdoutLabelsAdmitted'],
        'holdoutMetrics':metrics,'candidateVsBaselineMae':boot,'holdoutIntervalCoverage':coverage,
        'repository2025SeasonRole':holdout_role,'postHoldoutRefitPerformed':False,'postHoldoutReselectionPerformed':False,
        'prospectiveOutcomeRead':False,'marketDependency':False,'oddsPapiRequests':0,'frozenOmegaMutation':False,
        'marketExecutionEligible':False,'nextGate':spec['nextGate'],
    }
    manifest_path=out_dir/'NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_MANIFEST.json'
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    atomic_pointer(root/'data/models/nfl/CURRENT_QB_MODEL_023',str(out_dir.relative_to(root)))

    base=metrics['baseline_last4']; cand=metrics['MODEL_A_DIRECT']
    print('\nNFL QB MODEL 0.2.3 — PROSPECTIVE SHADOW PROMOTION')
    print(f'Frozen candidate: {q23.FROZEN_CANDIDATE} · coefficients unchanged from 0.2.1')
    print(f'2025 confirmatory holdout: {holdout["holdoutDisposition"]} · n={holdout["holdoutLabelsAdmitted"]:,}')
    print(f"  baseline MAE {base['mae']:.3f} · frozen model MAE {cand['mae']:.3f}")
    print(f"  MAE delta {boot['deltaMae']:+.3f} yd · 95% CI [{boot['ci95'][0]:+.3f}, {boot['ci95'][1]:+.3f}]")
    print(f"  frozen residual coverage: central80 {coverage['central80']['coveragePct']:.2f}% · central90 {coverage['central90']['coveragePct']:.2f}%")
    print(f'2025 repository role: {holdout_role} · coefficient refit NO')
    print('2025 may be used only as lagged feature history for 2026 scoring on this track')
    print('2026 outcomes: NOT READ')
    print('Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO')
    print('Market execution eligible: NO · verified QB identity + as-of scorer still required')
    print(f'Promotion SHA256: {spec_sha}')
    print(f'Spec: {spec_path}')
    print(f'Manifest: {manifest_path}')
    print('NEXT GATE: BUILD_2026_ASOF_QB_PASSING_YARDS_SCORER_WITH_VERIFIED_IDENTITY')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

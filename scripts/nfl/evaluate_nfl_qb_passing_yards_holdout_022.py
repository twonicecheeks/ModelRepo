#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import ssl
import tempfile
import urllib.request
import uuid

try:
    import pyarrow.parquet as pq
except Exception as exc:
    raise SystemExit(f"pyarrow required; run scripts/nfl/bootstrap_phase1_python.command: {exc}")


def load_jsonl(path: Path) -> list[dict]:
    out=[]
    with path.open('r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if line: out.append(json.loads(line))
    return out


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


def asset_index(manifest: dict) -> dict[tuple[str,int|None],dict]:
    return {(str(a.get('source') or ''),a.get('season')):a for a in manifest.get('assets',[])}


def tls_context() -> ssl.SSLContext:
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


def download(url: str, target: Path) -> dict:
    req=urllib.request.Request(url,headers={'User-Agent':'MODEL-NFL/QB-0.2.2-2025-holdout','Accept':'*/*'})
    with urllib.request.urlopen(req,timeout=180,context=tls_context()) as resp,target.open('wb') as out:
        shutil.copyfileobj(resp,out,length=1024*1024)
        return {'etag':resp.headers.get('ETag'),'lastModified':resp.headers.get('Last-Modified'),'finalUrl':resp.geturl()}


def main() -> int:
    ap=argparse.ArgumentParser(description='Run the single frozen 2025 QB passing-yards holdout')
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    args=ap.parse_args()
    root=Path(args.root).expanduser().resolve()
    model_dir=root/'packages/models/nfl/game'; provider_dir=root/'packages/providers/nflverse/src'
    import sys
    sys.path.insert(0,str(model_dir)); sys.path.insert(0,str(provider_dir))
    import qb_passing_yards_bakeoff_020 as q20
    import qb_passing_yards_freeze_021 as q21
    import qb_passing_yards_holdout_022 as q22
    import qb_target_semantics_015 as q15
    import qb_official_target_authority_019 as q19
    import qb_official_stats_adapter_019 as official_adapter
    import contract

    freeze_ptr=root/'data/models/nfl/CURRENT_QB_MODEL_021'
    dev_target_ptr=root/'data/normalized/nfl/CURRENT_NFL_QB_OFFICIAL_TARGETS_019'
    raw_ptr=root/'data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT'
    if not freeze_ptr.exists() or not dev_target_ptr.exists() or not raw_ptr.exists():
        raise FileNotFoundError('required frozen model/development target/raw pointers missing')

    freeze_dir=root/freeze_ptr.read_text(encoding='utf-8').strip()
    freeze_path=freeze_dir/'NFL_QB_PASSING_YARDS_FROZEN_SPEC.json'
    freeze_sha_path=freeze_dir/'NFL_QB_PASSING_YARDS_FROZEN_SPEC.sha256'
    freeze_manifest_path=freeze_dir/'NFL_QB_PASSING_YARDS_FREEZE_MANIFEST.json'
    dev_target_dir=root/dev_target_ptr.read_text(encoding='utf-8').strip()
    dev_targets_path=dev_target_dir/'NFL_QB_OFFICIAL_TARGETS.jsonl'
    raw_sid=raw_ptr.read_text(encoding='utf-8').strip()
    raw_manifest_path=root/'data/raw/nfl/nflverse/snapshots'/raw_sid/'SOURCE_MANIFEST.json'
    for p in (freeze_path,freeze_sha_path,freeze_manifest_path,dev_targets_path,raw_manifest_path):
        if not p.exists(): raise FileNotFoundError(f'required holdout source missing: {p}')

    freeze=json.loads(freeze_path.read_text(encoding='utf-8'))
    manifest=json.loads(freeze_manifest_path.read_text(encoding='utf-8'))
    q22.assert_freeze_ready(freeze,manifest)
    expected_sha=freeze_sha_path.read_text(encoding='utf-8').strip().split()[0]
    actual_sha=hashlib.sha256(canonical_bytes(freeze)).hexdigest()
    if expected_sha!=actual_sha or manifest.get('freezeSpecSha256')!=actual_sha:
        raise ValueError('frozen 0.2.1 SHA drift')
    if freeze.get('sourcePbpSnapshotId')!=raw_sid:
        raise ValueError('frozen model/raw snapshot drift')

    # Re-verify frozen source hashes that remain addressable.
    source_hashes=manifest.get('sourceHashes') or {}
    checks={
        'qb019TargetsJsonlSha256':dev_targets_path,
        'qb020CodeSha256':model_dir/'qb_passing_yards_bakeoff_020.py',
        'qb021FreezeCodeSha256':model_dir/'qb_passing_yards_freeze_021.py',
    }
    for key,path in checks.items():
        exp=source_hashes.get(key)
        if exp and sha256_file(path)!=exp: raise ValueError(f'frozen source hash drift: {key}')

    raw_manifest=json.loads(raw_manifest_path.read_text(encoding='utf-8'))
    assets=asset_index(raw_manifest)
    pbp_asset=assets.get(('play_by_play',2025))
    if not pbp_asset:
        raise ValueError('current immutable raw snapshot has no 2025 play_by_play asset; holdout not evaluated')
    pbp_path=root/pbp_asset['blobPath']
    if not pbp_path.exists(): raise FileNotFoundError(f'2025 PBP blob missing: {pbp_path}')

    # Open holdout PBP exactly once and build observed-start mechanism rows.
    pf=pq.ParquetFile(pbp_path); names=set(pf.schema_arrow.names)
    missing=[c for c in q15.REQUIRED_PBP_FIELDS if c not in names]
    if missing: raise ValueError('2025 PBP missing holdout fields: '+', '.join(missing))
    cols=list(q15.REQUIRED_PBP_FIELDS)+[c for c in q15.OPTIONAL_PBP_FIELDS if c in names]
    grouped=defaultdict(list)
    for r in pf.read(columns=cols).to_pylist():
        if int(r.get('season') or 0)!=2025: continue
        gid=str(r.get('game_id') or '')
        team_raw=str(r.get('posteam') or '').strip().upper()
        if not gid or not team_raw: continue
        rr=dict(r); rr['posteam']=contract.normalize_team_abbr(team_raw)
        grouped[(gid,rr['posteam'])].append(rr)
    holdout_mechanism=[]
    for _,grows in grouped.items():
        x=q15.aggregate_team_game(grows)
        if x is not None: holdout_mechanism.append(x)
    holdout_mechanism.sort(key=lambda r:(int(r['week']),r['game_id'],r['team']))
    q22.assert_holdout_rows(holdout_mechanism)
    if not holdout_mechanism: raise ValueError('no 2025 holdout team-game targets built')

    target_ids={str(r['observed_start_qb_gsis_id']) for r in holdout_mechanism}

    # Download 2025 official weekly stats into a dedicated immutable holdout snapshot.
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    holdout_raw_stage=root/'data/raw/nfl/nflverse/qb_holdout_022'/('.'+run_id+'.staging')
    holdout_raw_final=root/'data/raw/nfl/nflverse/qb_holdout_022'/run_id
    holdout_raw_stage.mkdir(parents=True,exist_ok=False)
    try:
        url=official_adapter.PARQUET_URL.format(season=2025)
        print('DOWNLOAD official weekly player stats 2025 — HOLDOUT SEAL OPENED')
        fd,tmpname=tempfile.mkstemp(prefix='stats_player_week_2025_',suffix='.parquet',dir=str(holdout_raw_stage)); os.close(fd)
        temp=Path(tmpname); meta=download(url,temp); digest=sha256_file(temp)
        blob=root/'data/raw/nfl/nflverse/blobs'/digest[:2]/digest; blob.parent.mkdir(parents=True,exist_ok=True)
        if blob.exists():
            if sha256_file(blob)!=digest: raise ValueError('content-addressed 2025 official-stat blob mismatch')
            temp.unlink()
        else: os.replace(temp,blob)
        opf=pq.ParquetFile(blob); onames=set(opf.schema_arrow.names)
        req=set(official_adapter.REQUIRED_FIELDS)
        if not req.issubset(onames): raise ValueError(f'2025 weekly stats missing fields: {sorted(req-onames)}')
        selected=list(official_adapter.REQUIRED_FIELDS)+[c for c in official_adapter.OPTIONAL_FIELDS if c in onames]
        official=[]
        for raw in opf.read(columns=selected).to_pylist():
            if str(raw.get('season_type') or '').upper()!='REG': continue
            if str(raw.get('player_id') or '').strip() not in target_ids: continue
            row=official_adapter.normalize_row(raw); row['source_sha256']=digest; row['source_url']=url; official.append(row)
        official.sort(key=lambda r:(r.get('week') or 0,r.get('game_id') or '',r.get('player_id') or ''))
        (holdout_raw_stage/'QB_2025_HOLDOUT_SOURCE_MANIFEST.json').write_text(json.dumps({
            'version':q22.VERSION,'runId':run_id,'createdAt':datetime.now(timezone.utc).isoformat(),
            'holdoutSeason':2025,'holdoutOpened':True,'prospectiveSeason':2026,'prospectiveRead':False,
            'pbpSourceSnapshotId':raw_sid,'pbpBlobPath':str(pbp_path.relative_to(root)),'pbpSha256':sha256_file(pbp_path),
            'officialStatsUrl':url,'officialStatsSha256':digest,'officialStatsBlobPath':str(blob.relative_to(root)),
            'officialStatsSelectedFields':selected,'marketDependency':False,'oddsPapiRequests':0,'frozenOmegaMutation':False,**meta,
        },indent=2)+'\n',encoding='utf-8')
        os.replace(holdout_raw_stage,holdout_raw_final)
    except Exception:
        shutil.rmtree(holdout_raw_stage,ignore_errors=True)
        raise

    by_official=defaultdict(list)
    for r in official: by_official[q19.official_key(r)].append(r)
    canonical=[]; missing_keys=[]; duplicate_keys=[]; team_mismatch=[]
    for target in holdout_mechanism:
        key=q19.target_key(target); matches=by_official.get(key,[])
        if not matches: missing_keys.append(key); continue
        if len(matches)!=1: duplicate_keys.append(key); continue
        off=matches[0]
        if str(off.get('team') or '').upper()!=str(target.get('team') or '').upper(): team_mismatch.append(key); continue
        row=q19.attach_official_target(target,off)
        gid=str(row.get('game_id') or ''); parsed=contract.parse_game_id(gid)
        away=contract.normalize_team_abbr(parsed['away_team']); home=contract.normalize_team_abbr(parsed['home_team']); team=str(row.get('team') or '').upper()
        if team==away: row['_opponent']=home; row['_home']=0
        elif team==home: row['_opponent']=away; row['_home']=1
        else: raise ValueError(f'2025 target team/game identity mismatch: {gid} {team}')
        canonical.append(row)
    if missing_keys or duplicate_keys or team_mismatch:
        raise ValueError(f'2025 official target join failed missing={len(missing_keys)} duplicate={len(duplicate_keys)} teamMismatch={len(team_mismatch)}')
    required=('official_attempts','official_completions','official_passing_yards','official_sacks_suffered')
    bad_required=[r for r in canonical if any(r.get(f) is None for f in required)]
    if bad_required: raise ValueError(f'2025 official required-value missing rows: {len(bad_required)}')
    canonical.sort(key=lambda r:(int(r['week']),r['game_id'],r['team']))

    dev=load_jsonl(dev_targets_path)
    for row in dev:
        gid=str(row.get('game_id') or ''); parsed=contract.parse_game_id(gid)
        away=contract.normalize_team_abbr(parsed['away_team']); home=contract.normalize_team_abbr(parsed['home_team']); team=str(row.get('team') or '').upper()
        if team==away: row['_opponent']=home; row['_home']=0
        elif team==home: row['_opponent']=away; row['_home']=1
        else: raise ValueError(f'development target identity mismatch: {gid} {team}')

    examples=q22.build_holdout_examples(dev,canonical,q20)
    if len(examples)!=len(canonical): raise ValueError('2025 holdout feature coverage drift')
    model=freeze['model']; feature_names=list(freeze.get('featureNames') or [])
    if feature_names!=list(q20.FEATURE_NAMES) or model.get('featureNames')!=feature_names:
        raise ValueError('frozen holdout feature contract drift')

    preds=[]
    for e in examples:
        pred=q21.predict_serialized_ridge(model,e.x)
        preds.append({'season':2025,'week':e.week,'game_id':e.game_id,'team':e.team,'opponent':e.opponent,'qb_gsis_id':e.qb_gsis_id,
                      'actual_passing_yards':e.actual_passing_yards,'baseline_last4':e.baseline_last4,'MODEL_A_DIRECT':float(pred)})
    ys=[float(r['actual_passing_yards']) for r in preds]
    base=q20.metric_summary(ys,[float(r['baseline_last4']) for r in preds])
    cand=q20.metric_summary(ys,[float(r['MODEL_A_DIRECT']) for r in preds])
    boot=q20.cluster_bootstrap_mae_delta(preds,'MODEL_A_DIRECT','baseline_last4',reps=int(q21.HOLDOUT_BOOTSTRAP_REPS),seed=int(q21.HOLDOUT_BOOTSTRAP_SEED))
    disposition=q21.holdout_disposition(float(boot['deltaMae']),boot['ci95'])
    coverage=q22.interval_coverage(preds,freeze['residualCalibration'])

    # Immutable result. After this write the holdout is considered consumed.
    out_dir=root/'data/models/nfl/qb_model_022'/run_id
    out_dir.mkdir(parents=True,exist_ok=False)
    pred_path=out_dir/'NFL_QB_PASSING_YARDS_2025_HOLDOUT_PREDICTIONS.jsonl'
    with pred_path.open('w',encoding='utf-8') as f:
        for r in preds: f.write(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n')
    canonical_path=out_dir/'NFL_QB_2025_OFFICIAL_TARGETS.jsonl'
    with canonical_path.open('w',encoding='utf-8') as f:
        for r in canonical: f.write(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n')
    report={
        'version':q22.VERSION,'lineage':q22.LINEAGE,'createdAt':datetime.now(timezone.utc).isoformat(),'runId':run_id,
        'frozenSpecSha256':actual_sha,'frozenCandidate':'MODEL_A_DIRECT','holdoutSeason':2025,'holdoutOpened':True,
        'holdoutLabelsAdmitted':len(preds),'prospectiveSeason':2026,'prospectiveRead':False,'marketDependency':False,
        'marketFieldsAdmitted':0,'oddsPapiRequests':0,'frozenOmegaMutation':False,'modelRefitPerformed':False,'candidateReselectionPerformed':False,
        'targetRows':len(canonical),'predictionRows':len(preds),'officialJoinCoveragePct':100.0,
        'metrics':{'baseline_last4':base,'MODEL_A_DIRECT':cand},'candidateVsBaselineMae':boot,'frozenResidualIntervalCoverage':coverage,
        'holdoutDisposition':disposition,'preregisteredPolicy':freeze['holdoutEvaluationPolicy'],
        'nextGate':'REVIEW_HOLDOUT_DISPOSITION_BEFORE_ANY_POST_HOLDOUT_REFIT_OR_PROSPECTIVE_PROMOTION',
        'productionEligible':False,
        'sourceHoldoutManifest':str((holdout_raw_final/'QB_2025_HOLDOUT_SOURCE_MANIFEST.json').relative_to(root)),
    }
    report_path=out_dir/'NFL_QB_PASSING_YARDS_2025_HOLDOUT_AUDIT.json'; report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    atomic_pointer(root/'data/models/nfl/CURRENT_QB_MODEL_022',str(out_dir.relative_to(root)))

    print('\nNFL QB MODEL 0.2.2 — SINGLE 2025 CONFIRMATORY HOLDOUT')
    print(f'Frozen spec SHA256: {actual_sha}')
    print('Frozen candidate: MODEL_A_DIRECT · NO REFIT · NO RESELECTION')
    print(f'2025 holdout rows: {len(preds):,} · official join 100.00%')
    print('2026 prospective: NOT READ')
    print('Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO')
    print('\nHOLDOUT METRICS')
    print(f"  baseline_last4: MAE {base['mae']:.3f} · RMSE {base['rmse']:.3f} · bias {base['bias']:+.3f} · median AE {base['medianAbsoluteError']:.3f}")
    print(f"  MODEL_A_DIRECT: MAE {cand['mae']:.3f} · RMSE {cand['rmse']:.3f} · bias {cand['bias']:+.3f} · median AE {cand['medianAbsoluteError']:.3f}")
    print(f"  MAE delta A-minus-baseline {boot['deltaMae']:+.3f} yd · 95% CI [{boot['ci95'][0]:+.3f}, {boot['ci95'][1]:+.3f}]")
    print('\nFROZEN OOF INTERVAL COVERAGE')
    print(f"  central80: {coverage['central80']['coveragePct']:.2f}% · central90: {coverage['central90']['coveragePct']:.2f}%")
    print(f'\nHOLDOUT DISPOSITION: {disposition}')
    print('Post-holdout refit/reselection: NOT PERFORMED')
    print(f'Predictions: {pred_path}')
    print(f'Audit: {report_path}')
    print('NEXT GATE: REVIEW_HOLDOUT_DISPOSITION_BEFORE_ANY_POST_HOLDOUT_REFIT_OR_PROSPECTIVE_PROMOTION')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

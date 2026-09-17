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


def main() -> int:
    ap=argparse.ArgumentParser(description='Evaluate a multi-book QB passing-yards shadow board against frozen OOF residual probabilities')
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--game-id',required=True)
    ap.add_argument('--qb-gsis-id',required=True)
    ap.add_argument('--market-source',required=True,choices=['USER_ENTERED_DIRECT_SPORTSBOOK','DIRECT_SPORTSBOOK_CAPTURE','PROPSMADNESS_REFERENCE'])
    ap.add_argument('--captured-at',default='')
    ap.add_argument('--quote',action='append',required=True,help='repeat BOOK|LINE|OVER|UNDER; use NA for missing price')
    args=ap.parse_args()

    root=Path(args.root).expanduser().resolve()
    model_dir=root/'packages/models/nfl/game'; sys.path.insert(0,str(model_dir))
    import qb_passing_yards_market_025 as q25
    import qb_passing_yards_board_026 as q26

    score_ptr=root/'data/prospective/nfl/CURRENT_QB_PASSING_YARDS_024'
    promotion_ptr=root/'data/models/nfl/CURRENT_QB_MODEL_023'
    freeze_ptr=root/'data/models/nfl/CURRENT_QB_MODEL_021'
    for p in (score_ptr,promotion_ptr,freeze_ptr):
        if not p.exists(): raise FileNotFoundError(f'QB 0.2.6 prerequisite pointer missing: {p}')

    score_dir=root/score_ptr.read_text(encoding='utf-8').strip()
    score_path=score_dir/'NFL_QB_PASSING_YARDS_ASOF_SCORE.json'
    score=json.loads(score_path.read_text(encoding='utf-8'))
    q25.assert_score_ready(score)
    target=score.get('target') or {}
    if str(target.get('game_id') or '')!=str(args.game_id).strip():
        raise ValueError('board target game does not match current 0.2.4 score')
    if str(target.get('qb_gsis_id') or '')!=str(args.qb_gsis_id).strip():
        raise ValueError('board target QB does not match current 0.2.4 score')

    promotion_dir=root/promotion_ptr.read_text(encoding='utf-8').strip()
    promotion_path=promotion_dir/'NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.json'
    promotion_sha_path=promotion_dir/'NFL_QB_PASSING_YARDS_PROSPECTIVE_SHADOW_SPEC.sha256'
    promotion=json.loads(promotion_path.read_text(encoding='utf-8'))
    promotion_sha=hashlib.sha256(canonical_bytes(promotion)).hexdigest()
    if promotion_sha!=promotion_sha_path.read_text(encoding='utf-8').strip().split()[0] or score.get('promotionSpecSha256')!=promotion_sha:
        raise ValueError('QB 0.2.6 promotion lineage drift')

    freeze_dir=root/freeze_ptr.read_text(encoding='utf-8').strip()
    freeze_path=freeze_dir/'NFL_QB_PASSING_YARDS_FROZEN_SPEC.json'
    freeze_manifest_path=freeze_dir/'NFL_QB_PASSING_YARDS_FREEZE_MANIFEST.json'
    freeze=json.loads(freeze_path.read_text(encoding='utf-8'))
    freeze_manifest=json.loads(freeze_manifest_path.read_text(encoding='utf-8'))
    freeze_sha=hashlib.sha256(canonical_bytes(freeze)).hexdigest()
    if freeze_sha!=score.get('frozenSpecSha256') or freeze_sha!=promotion.get('frozenSpecSha256'):
        raise ValueError('QB 0.2.6 frozen-model lineage drift')

    source_model_dir=root/str(freeze.get('sourceModelRunDirectory') or '')
    oof_path=source_model_dir/'NFL_QB_PASSING_YARDS_OOF.jsonl'
    expected_oof_sha=(freeze_manifest.get('sourceHashes') or {}).get('qb020OofJsonlSha256')
    actual_oof_sha=sha256_file(oof_path)
    if not expected_oof_sha or actual_oof_sha!=expected_oof_sha:
        raise ValueError('QB 0.2.6 frozen OOF residual hash drift')
    residuals=q25.residual_rows(load_jsonl(oof_path))
    if len(residuals)!=int((freeze.get('residualCalibration') or {}).get('n') or 0):
        raise ValueError('QB 0.2.6 frozen residual count drift')

    quotes=[q26.parse_quote(x,q25) for x in args.quote]
    keys=[(q['book'].lower(),q['line']) for q in quotes]
    if len(set(keys))!=len(keys):
        raise ValueError('duplicate book/line quote on board')

    point=float(score['projectionPassingYards'])
    cache={}
    for line in sorted({float(q['line']) for q in quotes}):
        probs=q25.empirical_market_probability(residuals,point,line)
        boot=q25.cluster_bootstrap_probability(residuals,point,line)
        if abs(float(probs['overProbability'])-float(boot['overProbability']))>1e-12:
            raise ValueError('QB 0.2.6 empirical/bootstrap probability mismatch')
        cache[line]=(probs,boot)

    rows=[]
    for quote in quotes:
        line=float(quote['line']); over_price=quote['overAmerican']; under_price=quote['underAmerican']
        probs,boot=cache[line]
        nv=q25.no_vig_two_way(over_price,under_price) if over_price is not None and under_price is not None else None
        over=q25.market_side_summary(probs['overProbability'],over_price,None if nv is None else nv['overNoVig'])
        under=q25.market_side_summary(probs['underProbability'],under_price,None if nv is None else nv['underNoVig'])
        over=q26.add_probability_ci(over,boot['overCi95'],over_price,q25)
        under=q26.add_probability_ci(under,boot['underCi95'],under_price,q25)
        over['shadowDisposition']=q26.shadow_disposition(over)
        under['shadowDisposition']=q26.shadow_disposition(under)
        rows.append({
            'book':quote['book'],'line':line,'overAmerican':over_price,'underAmerican':under_price,
            'twoWayNoVig':nv,'probabilityModel':probs,'probabilityBootstrap':boot,
            'sides':{'OVER':over,'UNDER':under},
        })

    rows.sort(key=lambda r:(r['line'],r['book'].lower()))
    best=q26.best_priced_side(rows)
    now=datetime.now(timezone.utc)
    captured_at=str(args.captured_at).strip() or now.isoformat()
    quote_time_mode='USER_PROVIDED' if str(args.captured_at).strip() else 'RUN_TIME_ASSUMED_CAPTURE'
    reference_only=str(args.market_source)=='PROPSMADNESS_REFERENCE'
    run_id=now.strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    out_dir=root/'data/prospective/nfl/qb_passing_yards_board_026'/run_id; out_dir.mkdir(parents=True,exist_ok=False)
    report={
        'version':q26.VERSION,'lineage':q26.LINEAGE,'createdAt':now.isoformat(),'runId':run_id,
        'status':'PROSPECTIVE_SHADOW_MULTIBOOK_BOARD','target':target,'projectionPassingYards':point,
        'marketSource':str(args.market_source),'capturedAt':captured_at,'quoteTimeMode':quote_time_mode,
        'referenceOnly':reference_only,'quoteRows':len(rows),'uniqueLines':len(cache),'board':rows,'bestDisplayedPointEvSide':best,
        'frozenOofResidualRows':len(residuals),'frozenOofResidualSourceSha256':actual_oof_sha,
        'sourceScorePath':str(score_path.relative_to(root)),'sourceScoreSha256':sha256_file(score_path),
        'promotionSpecSha256':promotion_sha,'frozenSpecSha256':freeze_sha,
        'coefficientRefitPerformed':False,'candidateReselectionPerformed':False,'marketFieldsUsedAsModelFeatures':False,
        'targetOrLater2026OutcomeRowsAdmitted':0,'oddsPapiRequests':0,'frozenOmegaMutation':False,'marketExecutionEligible':False,
        'nextGate':'VALIDATE_DIRECT_MARKET_CAPTURE_FRESHNESS_AND_PROSPECTIVE_CLV_BEFORE_EXECUTION_PROMOTION',
    }
    report_path=out_dir/'NFL_QB_PASSING_YARDS_MULTIBOOK_BOARD.json'
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    atomic_pointer(root/'data/prospective/nfl/CURRENT_QB_PASSING_YARDS_BOARD_026',str(out_dir.relative_to(root)))

    print('\nNFL QB MODEL 0.2.6 — MULTI-BOOK SHADOW BOARD')
    print(f"Target: {target.get('game_id')} · {target.get('team')} vs {target.get('opponent')} · {target.get('qb_name') or target.get('qb_gsis_id')}")
    print(f'Projection: {point:.1f} yd · quotes {len(rows)} · unique lines {len(cache)} · source {args.market_source}')
    print(f'Quote timestamp: {captured_at} · mode {quote_time_mode}')
    print(f'Frozen residuals: n={len(residuals):,} · SHA verified · no refit')
    print('\nBOOK                         LINE    OVER      O-EV      UNDER     U-EV')
    for r in rows:
        o=r['sides']['OVER']; u=r['sides']['UNDER']
        op='NA' if r['overAmerican'] is None else f"{r['overAmerican']:+d}"
        up='NA' if r['underAmerican'] is None else f"{r['underAmerican']:+d}"
        oe='NA' if o['expectedRoiPct'] is None else f"{o['expectedRoiPct']:+.2f}%"
        ue='NA' if u['expectedRoiPct'] is None else f"{u['expectedRoiPct']:+.2f}%"
        print(f"{r['book'][:28]:28s} {r['line']:6.1f}  {op:>6s}  {oe:>9s}   {up:>6s}  {ue:>9s}")
    if best is not None:
        ci=best.get('expectedRoiPctCi95')
        ci_txt='' if ci is None else f" · CI [{ci[0]:+.2f}%, {ci[1]:+.2f}%]"
        print(f"\nBest displayed point-EV side: {best['book']} {best['side']} {best['line']:.1f} {best['offeredAmerican']:+d} · EV {best['expectedRoiPct']:+.2f}%{ci_txt} · {best['shadowDisposition']}")
    print(f'Reference-only board: {"YES" if reference_only else "NO"}')
    print('Market fields used as model features: NO')
    print('Market execution eligible: NO · direct quote freshness + prospective CLV validation still required')
    print(f'Board: {report_path}')
    print('NEXT GATE: VALIDATE_DIRECT_MARKET_CAPTURE_FRESHNESS_AND_PROSPECTIVE_CLV_BEFORE_EXECUTION_PROMOTION')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

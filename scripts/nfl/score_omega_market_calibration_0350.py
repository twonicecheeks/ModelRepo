#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import uuid


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str,str]]:
    with path.open(newline='',encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields or ['status'],extrasaction='ignore',lineterminator='\n')
        w.writeheader();w.writerows(rows)


def load_score_lib(root: Path):
    p=root/'scripts/nfl/score_omega_prospective_eval_0230.py'
    spec=importlib.util.spec_from_file_location('omega_score023_0350',p)
    if spec is None or spec.loader is None:raise SystemExit(f'FAIL cannot load OMEGA 0.23 scorer: {p}')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def resolve_overlay(root: Path, game_id: str, arg: str) -> Path:
    if arg:
        p=Path(arg).expanduser().resolve()
        if not p.exists():raise FileNotFoundError(p)
        return p
    ptr=root/f'data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_GAMEDAY_OVERLAY_0342_{game_id}'
    if not ptr.exists():
        ptr=root/'data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_GAMEDAY_OVERLAY_0342'
    if not ptr.exists():raise FileNotFoundError('no OMEGA 0.34.2 game-day overlay pointer')
    d=root/ptr.read_text(encoding='utf-8').strip()
    p=d/'OMEGA_0.34.2_GAMEDAY_MARKET_COMPARISON.csv'
    if not p.exists():raise FileNotFoundError(p)
    return p


def resolve_results_manifest(root: Path, arg: str) -> str:
    if arg:return str(Path(arg).expanduser().resolve())
    ptr=root/'data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST'
    if not ptr.exists():raise FileNotFoundError('no dedicated 2026 results manifest; refresh results first')
    v=ptr.read_text(encoding='utf-8').strip()
    return v if v.startswith('/') else str(root/v)


def fmt_pct(v):return 'NA' if v is None else f'{100*float(v):.2f}%'
def fmt_num(v,d=4):return 'NA' if v is None else f'{float(v):.{d}f}'


def main() -> int:
    ap=argparse.ArgumentParser(description='OMEGA 0.35 postgame market calibration audit')
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--game-id',required=True)
    ap.add_argument('--overlay-path',default='')
    ap.add_argument('--source-manifest',default='')
    args=ap.parse_args()
    root=Path(args.root).expanduser().resolve();gid=args.game_id.strip()
    sys.path.insert(0,str(root/'packages/models/nfl/game'))
    import omega_market_calibration_0350 as cal

    overlay=resolve_overlay(root,gid,args.overlay_path)
    source_rows=[r for r in read_csv(overlay) if str(r.get('game_id') or '')==gid]
    if not source_rows:raise ValueError(f'overlay contains no rows for {gid}')

    lib=load_score_lib(root)
    source_arg=resolve_results_manifest(root,args.source_manifest)
    _manifest,meta,pbp_asset,pbp_path,sched_path=lib.locate_source(root,source_arg)
    if gid not in lib.completed_games_from_schedule(sched_path,{gid}):
        raise SystemExit(f'FAIL {gid} not complete in results schedules')
    actual,seen,pbp_audit=lib.reconstruct_actuals(root,pbp_path,{gid})
    if gid not in seen:raise SystemExit(f'FAIL {gid} absent from results PBP')

    graded=[]
    for r in source_rows:
        pid=str(r.get('player_id') or '').strip()
        if not pid:raise ValueError(f"overlay row missing player_id: {r.get('player_name')}")
        y=float(actual.get((gid,pid),0))
        graded.append(cal.grade_row(r,y))
    summary=cal.summarize(graded)

    now=datetime.now(timezone.utc)
    run_id=now.strftime('%Y%m%dT%H%M%SZ')+'_'+str(pbp_asset.get('sha256') or '')[:8]+'_'+uuid.uuid4().hex[:4]
    base=root/'data/results/nfl/omega_market_calibration_0350'/gid
    final=base/run_id;staging=base/('.'+run_id+'.staging')
    base.mkdir(parents=True,exist_ok=True)
    if final.exists() or staging.exists():raise FileExistsError(f'duplicate calibration run {run_id}')
    staging.mkdir(parents=True,exist_ok=False)
    try:
        scored_path=staging/'OMEGA_0.35_MARKET_CALIBRATION_SCORED.csv';write_csv(scored_path,graded)
        report={
          'version':cal.VERSION,'lineage':cal.LINEAGE,'createdAt':now.isoformat(),'runId':run_id,'gameId':gid,
          'status':'POSTGAME_DIAGNOSTIC_ONLY','sourceOverlay':str(overlay.relative_to(root) if overlay.is_relative_to(root) else overlay),
          'sourceOverlaySha256':sha256_file(overlay),'sourceResultsSnapshotId':meta.get('snapshotId'),'sourcePbpSha256':pbp_asset.get('sha256'),
          'sourcePbpAudit':pbp_audit,'forecastRows':len(source_rows),'gradedRows':len(graded),'summary':summary,
          'integrity':{'modelRefitPerformed':False,'frozenOmegaMutation':False,'marketFieldsUsedAsForecastFeatures':False,'oddsPapiRequests':0},
          'nextGate':'ACCUMULATE_PROSPECTIVE_GAMES_BEFORE_ANY_EV_CALIBRATION_OR_ROLE_FILTER_PROMOTION',
        }
        report_path=staging/'OMEGA_0.35_MARKET_CALIBRATION_REPORT.json';report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        hashes={scored_path.name:sha256_file(scored_path),report_path.name:sha256_file(report_path)}
        (staging/'OMEGA_0.35_SCORE_HASHES.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
        os.replace(staging,final)
        ptr=root/'data/results/nfl/omega/CURRENT_OMEGA_MARKET_CALIBRATION_0350';ptr.parent.mkdir(parents=True,exist_ok=True)
        tmp=ptr.with_name('.'+ptr.name+'.tmp');tmp.write_text(f'{gid}/{run_id}\n',encoding='utf-8');os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True);raise

    s=summary['all'];clean=summary['cleanRoleExecutableNotQuarantined'];flt=summary['filteredOutOrRoleConflict'];ext=summary['extremeEv35Plus']
    print('OMEGA 0.35 — POSTGAME MARKET CALIBRATION')
    print(f'PASS {gid} · rows {len(graded)} · results snapshot {meta.get("snapshotId")}')
    print(f'ALL: hit {fmt_pct(s["controlHitRate"])} · Brier {fmt_num(s["controlBrier"])} · logloss {fmt_num(s["controlLogLoss"])} · flat-unit ROI {fmt_pct(s["realizedFlatUnitRoi"])}')
    print(f'CLEAN ROLE/EXECUTABLE: n {clean["rows"]} · hit {fmt_pct(clean["controlHitRate"])} · ROI {fmt_pct(clean["realizedFlatUnitRoi"])}')
    print(f'FILTERED/CONFLICT: n {flt["rows"]} · hit {fmt_pct(flt["controlHitRate"])} · ROI {fmt_pct(flt["realizedFlatUnitRoi"])}')
    print(f'EV >=35%: n {ext["gradedSelectedSides"]} · hit {fmt_pct(ext["controlHitRate"])} · mean p {fmt_pct(ext["controlMeanSelectedProbability"])} · {ext["calibrationStatus"]}')
    print('PASS automatic probability compression NO · refit 0 · frozen OMEGA mutation NO')
    print(f'REPORT: {final/"OMEGA_0.35_MARKET_CALIBRATION_REPORT.json"}')
    print(f'SCORED: {final/"OMEGA_0.35_MARKET_CALIBRATION_SCORED.csv"}')
    return 0

if __name__=='__main__':raise SystemExit(main())

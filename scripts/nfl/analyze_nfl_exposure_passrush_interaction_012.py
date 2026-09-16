#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import importlib.util
import json
import os
import uuid


def parse_seasons(text: str) -> list[int]:
    text=text.strip()
    if '-' in text:
        a,b=(int(x) for x in text.split('-',1))
        if a>b: raise ValueError('season range must be ascending')
        return list(range(a,b+1))
    return [int(x.strip()) for x in text.split(',') if x.strip()]


def load_module(root: Path):
    p=root/'packages/models/nfl/game/state_exposure_interaction_research.py'
    spec=importlib.util.spec_from_file_location('nfl_state_exposure_012',p)
    m=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(m)
    return m


def load_jsonl(path: Path) -> list[dict]:
    out=[]
    with path.open('r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if line: out.append(json.loads(line))
    return out


def pct(v): return 'NA' if v is None else f'{100*v:.2f}%'
def pp(v): return 'NA' if v is None else f'{100*v:+.2f} pp'


def main() -> int:
    ap=argparse.ArgumentParser(description='Development-only M05/M06 exposure x lagged pass-rush interaction audit')
    ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--seasons',default='2016-2024')
    ap.add_argument('--min-prior-dropbacks',type=int,default=20)
    ap.add_argument('--bootstrap-reps',type=int,default=1000)
    args=ap.parse_args()

    root=Path(args.root).expanduser().resolve()
    model=load_module(root)
    seasons=list(model.assert_development_only(parse_seasons(args.seasons)))

    pointer=root/'data/normalized/nfl/CURRENT_NFL_STATE_INTELLIGENCE'
    if not pointer.exists(): raise FileNotFoundError('CURRENT_NFL_STATE_INTELLIGENCE missing')
    state_dir=root/pointer.read_text(encoding='utf-8').strip()
    audit_path=state_dir/'NFL_STATE_INTELLIGENCE_AUDIT.json'
    audit=json.loads(audit_path.read_text(encoding='utf-8'))
    if audit.get('marketDependency') is not False or audit.get('frozenOmegaMutation') is not False:
        raise ValueError('state-intelligence audit boundary drift')
    if audit.get('trainingOrRefitPerformed') is not False:
        raise ValueError('unexpected training/refit in source state snapshot')

    audits={int(x['season']):x for x in audit.get('seasons',[])}
    for season in seasons:
        if season not in audits: raise ValueError(f'missing state season {season}')
        available=set(audits[season].get('optionalColumnsAvailable',[]))
        if 'first_down' not in available:
            raise ValueError(f'season {season} missing first_down required for conversion diagnostic')

    rows=[]
    for season in seasons:
        p=state_dir/f'NFL_STATE_INTELLIGENCE_SNAPS_{season}.jsonl'
        if not p.exists(): raise FileNotFoundError(p)
        season_rows=load_jsonl(p)
        rows.extend(season_rows)
        print(f'PASS {season} · snaps {len(season_rows):,}')

    records=model.build_exposure_records(rows,min_prior_dropbacks=args.min_prior_dropbacks)
    if not records: raise ValueError('no eligible lagged pass-rush exposure records')
    summary=model.summarize_exposure_records(records)
    boot=model.cluster_bootstrap_interaction(records,reps=args.bootstrap_reps)

    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    out_dir=root/'data/models/nfl/state_intelligence_012'/run_id
    out_dir.mkdir(parents=True,exist_ok=False)
    result={
        'version':model.VERSION,'lineage':model.LINEAGE,'runId':run_id,
        'sourceSnapshotId':audit.get('sourceSnapshotId'),
        'sourceStateDirectory':str(state_dir.relative_to(root)),
        'developmentSeasons':seasons,'sealedHoldoutSeason':2025,'prospectiveSeason':2026,
        'holdoutOpened':False,'marketDependency':False,'oddsPapiRequests':0,
        'frozenOmegaMutation':False,'trainingOrRefitPerformed':False,
        'mechanism':'M05/M06/M07/M19 structural third-down exposure x strictly lagged opponent sack propensity',
        'minPriorDefDropbacks':args.min_prior_dropbacks,
        'eligibleThirdDownDropbacks':len(records),
        'summary':summary,'clusterBootstrap':boot,
    }
    json_path=out_dir/'NFL_STATE_M05_M06_EXPOSURE_PASSRUSH_AUDIT.json'
    json_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')

    grid=summary['grid']; inter=summary['interaction']; b=boot['metrics']
    lines=[
        'NFL STATE INTELLIGENCE 0.1.2 — EXPOSURE × LAGGED PASS-RUSH AUDIT','',
        f"Source snapshot: {audit.get('sourceSnapshotId')}",
        f'Development seasons: {seasons[0]}-{seasons[-1]}',
        '2025 holdout: SEALED / NOT READ','2026 prospective: NOT READ',
        f'Eligible third-down dropbacks: {len(records):,}',
        f'Minimum prior defensive dropbacks for tiering: {args.min_prior_dropbacks}',
        f'Game-cluster bootstrap reps: {args.bootstrap_reps:,}','',
        'Sack rates by pregame lagged pass-rush tier × structural exposure',
    ]
    for tier in model.PRESSURE_TIERS:
        lines.append(f"  {tier}: base {pct(grid[tier]['BASE']['sack_rate'])} (n={grid[tier]['BASE']['dropbacks']:,}) · elevated+ {pct(grid[tier]['ELEVATED_PLUS']['sack_rate'])} (n={grid[tier]['ELEVATED_PLUS']['dropbacks']:,})")
    lines += ['', 'Interaction diagnostics',
        f"  HIGH minus LOW sack rate in BASE states: {pp(inter['base_high_minus_low_sack_rate'])}",
        f"  HIGH minus LOW sack rate in ELEVATED+ states: {pp(inter['exposed_high_minus_low_sack_rate'])}",
        f"  Difference-in-differences amplification: {pp(inter['difference_in_differences'])}",
        f"  HIGH-tier exposed minus base: {pp(inter['high_tier_exposed_minus_base_sack_rate'])}",
        f"  LOW-tier exposed minus base: {pp(inter['low_tier_exposed_minus_base_sack_rate'])}",'',
        'Game-cluster 95% CI',
    ]
    for key,vals in b.items():
        lines.append(f"  {key}: {pp(vals['observed'])} [{pp(vals['ci95_low'])}, {pp(vals['ci95_high'])}]")
    season_vals=summary.get('by_season_interaction',{})
    available=[v.get('difference_in_differences') for v in season_vals.values() if v.get('difference_in_differences') is not None]
    positive=sum(1 for x in available if x>0)
    lines += ['',f'Season direction: positive amplification in {positive}/{len(available)} development seasons' if available else 'Season direction: unavailable',
        '', 'Interpretation guard: pressure tier is built only from prior same-season weeks; same-week games are excluded from the prior.',
        'This remains descriptive mechanism research. No production feature or coefficient is promoted by this run.',
        '',f'JSON: {json_path}']
    txt_path=out_dir/'NFL_STATE_M05_M06_EXPOSURE_PASSRUSH_AUDIT.txt'
    txt_path.write_text('\n'.join(lines)+'\n',encoding='utf-8')

    current=root/'data/models/nfl/CURRENT_STATE_INTELLIGENCE_012'
    current.parent.mkdir(parents=True,exist_ok=True)
    tmp=current.with_name('.'+current.name+'.tmp'); tmp.write_text(str(out_dir.relative_to(root))+'\n',encoding='utf-8'); os.replace(tmp,current)
    print(); print(txt_path.read_text(encoding='utf-8'))
    print('PASS development-only M05/M06 interaction audit · 2025 holdout sealed · frozen OMEGA untouched')
    return 0

if __name__=='__main__': raise SystemExit(main())

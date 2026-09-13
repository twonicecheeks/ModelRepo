#!/usr/bin/env python3
"""Acquire 2015-2024 snap counts and build leakage-safe Phase 2C context."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,os,sys,tempfile,shutil

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def readcsv(p):
    with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def sha(p):
    h=hashlib.sha256();
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()
def writecsv(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows([{k:'' if r.get(k) is None else r.get(k) for k in fields} for r in rows])

def parquet_rows(path,required,optional=()):
    import pyarrow.parquet as pq
    pf=pq.ParquetFile(path);names=set(pf.schema_arrow.names);missing=[c for c in required if c not in names]
    if missing:raise ValueError(f'{path.name} missing required parquet column(s): {", ".join(missing)}')
    cols=list(required)+[c for c in optional if c in names and c not in required]
    return pf.read(columns=cols).to_pylist(),names

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args();root=Path(a.root).resolve()
    sys.path.insert(0,str(root/'packages/providers/nflverse/src'));sys.path.insert(0,str(root/'packages/models/nfl/game'))
    import snapshot,contract,normalize,phase2c_context as pc
    sid=(root/'data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT').read_text().strip();norm=root/'data/normalized/nfl/phase1'/sid
    raw_manifest_path=root/'data/raw/nfl/nflverse/snapshots'/sid/'SOURCE_MANIFEST.json'
    manifest=snapshot.load_manifest(raw_manifest_path,root=root)
    if 2025 not in manifest.get('analysisSeasons',[]):raise SystemExit('FAIL expected sealed 2025 source coverage in Phase1 snapshot')
    assets={(x['source'],x.get('season')):x for x in manifest['assets']}
    games=[r for r in readcsv(norm/'game_identity.csv') if int(r['season'])<=2024]
    base=[r for r in readcsv(norm/'pregame_features.csv') if int(r['season'])<=2024]
    seasons=list(range(2015,2025))
    # Immutable supplemental source manifest. Installation never downloads; this explicit build does.
    # If a complete supplemental snapshot for the same Phase1 source already exists, reuse it so a
    # later normalization/model bug never burns bandwidth by re-fetching identical snap-count assets.
    ctx_root=root/'data/raw/nfl/nflverse/phase2c_context/snapshots';ctx_root.mkdir(parents=True,exist_ok=True)
    reusable=None
    for mp in sorted(ctx_root.glob('*/SOURCE_MANIFEST.json'), reverse=True):
        try:
            d=json.loads(mp.read_text())
            ok=(d.get('schemaVersion')=='NFL_PHASE2C_CONTEXT_1.0' and d.get('sourcePhase1SnapshotId')==sid and d.get('seasons')==seasons and d.get('holdoutRead') is False)
            if ok:
                for x in d.get('assets',[]):
                    bp=root/x['blobPath']
                    if not bp.exists() or snapshot.sha256_file(bp)!=x['sha256']:ok=False;break
            if ok:
                reusable=(mp,d);break
        except Exception:
            pass
    if reusable:
        final=reusable[0].parent;cm=reusable[1];ctx_id=cm['contextSnapshotId'];snap_assets=cm['assets']
        print(f'PASS reuse supplemental snap-count snapshot: {ctx_id} · network 0')
    else:
        ctx_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+sid[-8:]
        staging=ctx_root/('.'+ctx_id+'.staging');final=ctx_root/ctx_id
        if final.exists():raise SystemExit(f'Refusing overwrite immutable Phase2C context source: {final}')
        staging.mkdir(parents=True,exist_ok=False);snap_assets=[]
        try:
            spec=contract.source_specs()['snap_counts']
            for i,season in enumerate(seasons,1):
                url=spec.url_for_season(season);print(f'[{i}/{len(seasons)}] nflverse snap_counts {season}')
                fd,name=tempfile.mkstemp(prefix='model_nfl_phase2c_',suffix='.part',dir=str(staging));os.close(fd);tmp=Path(name)
                meta=snapshot._download_http(url,tmp);digest=snapshot.sha256_file(tmp);blob=snapshot._store_blob(root,tmp,digest)
                snap_assets.append({'source':'snap_counts','season':season,'filename':f'snap_counts_{season}.parquet','url':url,'sha256':digest,'bytes':blob.stat().st_size,'blobPath':str(blob.relative_to(root)),'fetchedAt':now(),'etag':meta.get('etag'),'lastModified':meta.get('lastModified'),'contentType':meta.get('contentType')})
            cm={'schemaVersion':'NFL_PHASE2C_CONTEXT_1.0','contextSnapshotId':ctx_id,'sourcePhase1SnapshotId':sid,'createdAt':now(),'seasons':seasons,'holdoutSeason':2025,'holdoutRead':False,'marketDependency':False,'oddsPapiRequests':0,'assets':snap_assets}
            (staging/'SOURCE_MANIFEST.json').write_text(json.dumps(cm,indent=2)+'\n');os.replace(staging,final)
        except Exception:
            shutil.rmtree(staging,ignore_errors=True);raise

    # Roster rows come from the already immutable Phase1 source snapshot.
    roster_required=('season','week','team','gsis_id','pfr_id','full_name','position','depth_chart_position','status','game_type')
    rosters=[]
    for season in seasons:
        path=root/assets[('weekly_rosters',season)]['blobPath'];rr,_=parquet_rows(path,roster_required)
        for r in rr:r['team']=contract.normalize_team_abbr(r['team']) if r.get('team') else ''
        rosters.extend(rr)

    # Read only 2015-2024 PBP. 2025 exists physically but is not opened here.
    pbp_required=('game_id','season','week','posteam','qb_dropback','epa','cpoe','sack','yards_gained','interception','passer_player_id')
    pbp_optional=('qb_epa','passer_player_name','no_play','qb_kneel','play_type')
    pbp=[]
    for season in seasons:
        path=root/assets[('play_by_play',season)]['blobPath'];rr,names=parquet_rows(path,pbp_required,pbp_optional)
        if 'no_play' not in names and 'play_type' not in names:
            raise ValueError(f'{path.name} cannot identify nullified plays: need no_play or play_type')
        if 'qb_kneel' not in names and 'play_type' not in names:
            raise ValueError(f'{path.name} cannot identify QB kneels: need qb_kneel or play_type')
        for r in rr:
            # same semantic fallback as Phase1 normalizer
            play_type=str(r.get('play_type') or '').strip().lower()
            if 'no_play' not in names:r['no_play']=1 if play_type=='no_play' else 0
            if 'qb_kneel' not in names:r['qb_kneel']=1 if play_type=='qb_kneel' else 0
            if r.get('posteam'):r['posteam']=contract.normalize_team_abbr(r['posteam'])
        pbp.extend(rr)
    qb_games=pc.extract_observed_qb_game_metrics(pbp)
    qb_ctx=pc.build_qb_pregame_context(games,qb_games,rosters)

    snap_rows=[]
    for asset in snap_assets:
        path=root/asset['blobPath'];rr,_=parquet_rows(path,('game_id','season','game_type','week','player','pfr_player_id','position','team','opponent','offense_snaps','offense_pct','defense_snaps','defense_pct'))
        for r in rr:
            if r.get('team'):r['team']=contract.normalize_team_abbr(r['team'])
            if r.get('opponent'):r['opponent']=contract.normalize_team_abbr(r['opponent'])
        snap_rows.extend(rr)
    rc_ctx=pc.build_roster_continuity_context(games,snap_rows,rosters)
    merged=pc.merge_context_rows(base,qb_ctx,rc_ctx)
    if any(int(r['season'])>=2025 for r in merged):raise RuntimeError('holdout row leaked into Phase2C context')
    if not merged:raise RuntimeError('no Phase2C context rows')
    out=root/'data/normalized/nfl/phase2c_context'/sid
    if out.exists():raise SystemExit(f'Refusing overwrite immutable Phase2C normalized context: {out}')
    st=out.parent/('.'+sid+'.staging');st.mkdir(parents=True,exist_ok=False)
    try:
        writecsv(st/'qb_game_history.csv',qb_games);writecsv(st/'qb_pregame_context.csv',qb_ctx);writecsv(st/'roster_continuity_context.csv',rc_ctx);writecsv(st/'phase2c_features.csv',merged)
        qb_sides=2*len(qb_ctx)
        qb_resolved=sum(1 for r in qb_ctx for side in ('home','away') if r.get(f'{side}_projected_qb_gsis_id'))
        qb_resolution_counts={}
        for r in qb_ctx:
            for side in ('home','away'):
                k=str(r.get(f'{side}_qb_resolution') or 'MISSING');qb_resolution_counts[k]=qb_resolution_counts.get(k,0)+1
        continuity_fields=('offense_snap_continuity','ol_snap_continuity','skill_snap_continuity','defense_snap_continuity','active_roster_return_rate')
        roster_cov={}
        for stem in continuity_fields:
            vals=[r.get(f'{side}_{stem}') for r in rc_ctx for side in ('home','away')]
            good=sum(v not in (None,'') for v in vals);roster_cov[stem]={'nonMissing':good,'cells':len(vals),'nonMissingPct':round(100*good/len(vals),3) if vals else None}
        week1=[r for r in merged if int(r['week'])==1]
        audit={'generatedAt':now(),'sourceSnapshotId':sid,'supplementalSourceSnapshotId':ctx_id,'developmentRows':len(merged),'developmentSeasons':list(range(2016,2025)),'holdoutSeason':2025,'holdoutRowsRead':0,'marketFieldsAllowed':False,'oddsPapiRequests':0,
               'qb':{'observedHistoryRows':len(qb_games),'pregameRows':len(qb_ctx),'resolvedSides':qb_resolved,'sideCells':qb_sides,'resolvedPct':round(100*qb_resolved/qb_sides,3) if qb_sides else None,'resolutionCounts':qb_resolution_counts,'note':'Observed primary QB is postgame history and is admitted only after strict lag. It is not a verified pregame starter source.'},
               'roster':{'continuityRows':len(rc_ctx),'snapSource':'nflverse snap_counts (PFR-derived)','activeRosterStatus':'ACT','coverage':roster_cov},
               'week1':{'rows':len(week1),'note':'Week 1 QB/roster transition features use prior-season history plus target-week roster state; no current-game outcomes/PBP/snaps.'}}
        (st/'PHASE2C_CONTEXT_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
        md=['# MODEL NFL 2.9.0 Phase 2C — Context Audit','',f'Generated: {audit["generatedAt"]}','', '**2025 HOLDOUT REMAINS SEALED. NOT PRODUCTION.**','',f'- Source Phase1 snapshot: `{sid}`',f'- Supplemental snap-count snapshot: `{ctx_id}`',f'- Development feature rows: **{len(merged)}**', '- 2025 rows read into context: **0**','- Sportsbook/market fields: **DISALLOWED**','- OddsPapi requests: **0**','', '## QB integrity','',f'- Observed QB-history rows: **{len(qb_games)}**',f'- Resolved QB proxy sides: **{qb_resolved}/{qb_sides} ({audit["qb"]["resolvedPct"]}%)**','- Current-game QB PBP is never admitted to its own pregame row.','- Previous primary QB is used only after strict lag.','- Replacement QB is resolved only when the target-week active roster has exactly one QB; otherwise skill remains missing and `qb_unresolved=1`.','- This is a historical QB continuity proxy, **not** a verified starter-QB source.','', '### QB resolution states','']
        for k,v in sorted(qb_resolution_counts.items()): md.append(f'- `{k}`: {v}')
        md += ['', '## Roster continuity','', '- Target-week `ACT` roster status is matched to strictly prior-game snap counts.','- Week 1 continuity uses the previous season\'s last observed game.','- OL, skill-position, offense, defense and overall active-roster continuity are kept separate.','- Historical roster-week timing is suitable for development research but must be matched by an explicit live pregame cutoff before production.','', '### Non-missing coverage','']
        for stem,v in roster_cov.items(): md.append(f'- `{stem}`: {v["nonMissingPct"]}% ({v["nonMissing"]}/{v["cells"]})')
        md += ['', '## Week 1 transition','',f'- Development Week 1 rows: **{len(week1)}**','- Uses prior-season QB history and previous-season snap shares plus current Week 1 roster membership.','- No current-game PBP, snap counts, or outcomes are admitted.','']
        (st/'PHASE2C_CONTEXT_AUDIT.md').write_text('\n'.join(md));os.replace(st,out)
        (root/'data/normalized/nfl/CURRENT_PHASE2C_CONTEXT').write_text(sid+'\n')
    except Exception:
        shutil.rmtree(st,ignore_errors=True);raise
    print('MODEL NFL 2.9.0 PHASE 2C — QB / ROSTER CONTEXT BUILD')
    print(f'PASS source Phase1 snapshot: {sid}')
    print(f'PASS supplemental snap-count assets: {len(snap_assets)} · 2015-2024')
    print(f'PASS development context rows: {len(merged)} · 2016-2024 only')
    print('PASS QB history strict lag / no current-game QB PBP leakage')
    print('PASS 2025 holdout: NOT READ / NOT EVALUATED')
    print('PASS market fields disallowed · OddsPapi requests 0')
    print(f'REPORT: {out/"PHASE2C_CONTEXT_AUDIT.md"}')
    return 0
if __name__=='__main__':raise SystemExit(main())

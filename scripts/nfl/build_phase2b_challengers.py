#!/usr/bin/env python3
"""Build Phase 2B chronological challenger bake-off without opening 2025."""
from pathlib import Path
import argparse,csv,hashlib,json,os,sys
from datetime import datetime,timezone
from statistics import fmean

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def readcsv(p):
    with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def metric(ys,ps,rm):return rm.metric_summary(ys,ps)
def canon(o):return (json.dumps(o,sort_keys=True,separators=(',',':'))+'\n').encode()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args();root=Path(a.root).resolve()
    sys.path.insert(0,str(root/'packages/models/nfl/game'))
    import research_model as rm, challenger_models as cm, persistence as ps
    ptr=root/'data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT'
    if not ptr.exists():raise SystemExit('No Phase 1 snapshot. Run build_phase1_snapshot.command first.')
    sid=ptr.read_text().strip();snap=root/'data/normalized/nfl/phase1'/sid
    rows=readcsv(snap/'pregame_features.csv'); tg=readcsv(snap/'team_game_metrics.csv')
    dev_seasons=set(range(2016,2025)); dev_rows=[r for r in rows if int(r['season']) in dev_seasons and r.get('game_type')=='REG']
    ids={r['game_id'] for r in dev_rows}; labels={}; margins={}
    with (snap/'game_targets.csv').open(newline='',encoding='utf-8') as f:
        for r in csv.DictReader(f):
            gid=r.get('game_id','')
            if gid not in ids:continue
            if r.get('home_win') in ('0','0.0','1','1.0'):labels[gid]=int(float(r['home_win']))
            if r.get('home_margin') not in (None,''):margins[gid]=float(r['home_margin'])
    ex=rm.examples_from_rows(dev_rows,labels,allowed_seasons=dev_seasons)
    if len(ex)<1000:raise SystemExit(f'FAIL development sample too small: {len(ex)}')
    full_names=rm.expanded_feature_names(); sparse_names=cm.sparse_passing_feature_names(full_names)
    byid={e.game_id:e for e in ex}; valid=[2021,2022,2023,2024]
    team_search=rm.walk_forward_l2(ex,validation_seasons=valid); team_l2=team_search['selectedL2']
    sparse_grid=(.03,.1,.3); sparse_scores=[]
    for lam in sparse_grid:
        yy=[];pp=[]
        for s in valid:
            tr=[e for e in ex if e.season<s];te=[e for e in ex if e.season==s]
            X=[cm.select_columns(e.x,full_names,sparse_names) for e in tr]
            m=cm.fit_generic_logit(X,[e.y for e in tr],sparse_names,l2=lam)
            yy += [e.y for e in te]; pp += [m.predict(cm.select_columns(e.x,full_names,sparse_names)) for e in te]
        sparse_scores.append({'l2':lam,'metrics':metric(yy,pp,rm)})
    sparse_scores.sort(key=lambda z:(z['metrics']['logLoss'],z['metrics']['brier'])); sparse_l2=sparse_scores[0]['l2']
    ridge_grid=(.01,.03,.1,.3); ridge_scores=[]
    for lam in ridge_grid:
        yy=[];pp=[]
        for s in valid:
            tr=[e for e in ex if e.season<s and e.game_id in margins];te=[e for e in ex if e.season==s and e.game_id in margins]
            m=cm.fit_ridge_margin([e.x for e in tr],[margins[e.game_id] for e in tr],full_names,l2=lam)
            yy += [e.y for e in te]; pp += [m.win_probability(e.x) for e in te]
        ridge_scores.append({'l2':lam,'metrics':metric(yy,pp,rm)})
    ridge_scores.sort(key=lambda z:(z['metrics']['logLoss'],z['metrics']['brier'])); ridge_l2=ridge_scores[0]['l2']

    # Create chronological base OOF predictions.
    oof=[]
    elo_all=rm.elo_online_predictions(ex); elo={e.game_id:p for e,p in zip(ex,elo_all)}
    for s in valid:
        tr=[e for e in ex if e.season<s];te=[e for e in ex if e.season==s]
        team=rm.fit_logistic(tr,l2=team_l2)
        sparse=cm.fit_generic_logit([cm.select_columns(e.x,full_names,sparse_names) for e in tr],[e.y for e in tr],sparse_names,l2=sparse_l2)
        mrtr=[e for e in tr if e.game_id in margins]
        margin=cm.fit_ridge_margin([e.x for e in mrtr],[margins[e.game_id] for e in mrtr],full_names,l2=ridge_l2)
        for e in te:
            probs=[team.predict_proba(e.x), sparse.predict(cm.select_columns(e.x,full_names,sparse_names)), margin.win_probability(e.x), elo[e.game_id]]
            oof.append({'season':s,'game_id':e.game_id,'y':e.y,'probs':probs,'disagreement':cm.model_disagreement(probs)})

    base_names=['team_l2_logit','passing_core_sparse','margin_ridge','online_elo']
    base_metrics={}
    for j,n in enumerate(base_names):base_metrics[n]=metric([r['y'] for r in oof],[r['probs'][j] for r in oof],rm)

    # Nested chronological ensemble: stack weights are learned only from earlier OOF seasons.
    ens_y=[];ens_p=[];folds=[];weights=[]
    for s in [2022,2023,2024]:
        train=[r for r in oof if r['season']<s];test=[r for r in oof if r['season']==s]
        if not train or not test:continue
        pool=cm.fit_logit_pool([r['probs'] for r in train],[r['y'] for r in train])
        psx=[pool.predict(r['probs']) for r in test]; ys=[r['y'] for r in test]
        mm=metric(ys,psx,rm);folds.append({'season':s,**mm,'weights':dict(zip(base_names,pool.weights)),'intercept':pool.intercept})
        ens_y+=ys;ens_p+=psx;weights.append(pool.weights)
    ensemble_metrics=metric(ens_y,ens_p,rm)

    persist=ps.lag1_persistence(tg,rm.TEAM_METRICS,max_season=2024)
    final_pool=cm.fit_logit_pool([r['probs'] for r in oof],[r['y'] for r in oof])
    spec={'phase':'NFL_2.9.0_PHASE2B','status':'CHALLENGER_CANDIDATE_NOT_FROZEN','productionEligible':False,
          'holdoutSeason':2025,'holdoutEvaluated':False,'trainingSeasonsUsed':list(range(2016,2025)),
          'baseModels':base_names,'teamL2':team_l2,'sparseL2':sparse_l2,'marginL2':ridge_l2,
          'ensemble':{'method':'NONNEGATIVE_SIMPLEX_LOGIT_POOL','weights':dict(zip(base_names,final_pool.weights)),'intercept':final_pool.intercept},
          'qbLayer':{'status':'DATA_GATED','reason':'qb_roster_weekly is identity scaffold only; verified historical/live starter-QB resolution not yet admitted'},
          'marketFieldsAllowed':False,'oddsPapiRequests':0}
    sh=hashlib.sha256(canon(spec)).hexdigest()
    report={'generatedAt':now(),'sourceSnapshotId':sid,'integrity':{'holdoutEvaluated':False,'holdoutLabelsAdmitted':0,'marketFieldsAllowed':False,'oddsPapiRequests':0},
            'baseModelMetrics2021to2024':base_metrics,'nestedEnsembleMetrics2022to2024':ensemble_metrics,'nestedEnsembleFolds':folds,
            'selection':{'teamL2':team_l2,'sparseCandidates':sparse_scores,'marginCandidates':ridge_scores},
            'persistenceAudit':persist,'candidateSpecSha256':sh,
            'qbLayer':spec['qbLayer'],'note':'Persistence estimates are research diagnostics in Phase 2B and do not silently alter probabilities.'}
    out=root/'data/models/nfl/phase2b'/sid
    if out.exists():raise SystemExit(f'Refusing overwrite immutable Phase2B output: {out}')
    st=out.parent/('.'+sid+'.staging');st.mkdir(parents=True,exist_ok=False)
    try:
        (st/'CHALLENGER_SPEC.json').write_bytes(canon(spec));(st/'CHALLENGER_SPEC.sha256').write_text(sh+'  CHALLENGER_SPEC.json\n')
        (st/'CHALLENGER_BAKEOFF.json').write_text(json.dumps(report,indent=2)+'\n')
        md=['# NFL 2.9.0 Phase 2B — Challenger Bake-off','', '**2025 HOLDOUT REMAINS SEALED. NOT PRODUCTION.**','',
            f'Source snapshot: `{sid}`','', '## Chronological development performance','', '| Model | N | Brier | Log loss | Accuracy |','|---|---:|---:|---:|---:|']
        for n in base_names:
            m=base_metrics[n];md.append(f"| {n} | {m['n']} | {m['brier']:.5f} | {m['logLoss']:.5f} | {m['accuracy']:.3f} |")
        m=ensemble_metrics;md.append(f"| nested ensemble | {m['n']} | {m['brier']:.5f} | {m['logLoss']:.5f} | {m['accuracy']:.3f} |")
        md += ['', '## Integrity','', '- 2025 labels admitted: **0**','- sportsbook/market fields: **DISALLOWED**','- OddsPapi requests: **0**',
               '- QB layer: **DATA_GATED** until verified starter-QB history/live adapter exists','',
               '## Interpretation','', 'Do not freeze or open 2025 until this report is reviewed. The passing-core model is a sparse challenger, not a substitute for the future explicit QB-state model.']
        (st/'CHALLENGER_BAKEOFF.md').write_text('\n'.join(md)+'\n')
        os.replace(st,out);(root/'data/models/nfl').mkdir(parents=True,exist_ok=True);(root/'data/models/nfl/CURRENT_PHASE2B').write_text(sid+'\n')
    except Exception:
        import shutil;shutil.rmtree(st,ignore_errors=True);raise
    print('MODEL NFL 2.9.0 PHASE 2B — DYNAMIC CHALLENGER RESEARCH')
    print(f'PASS source snapshot: {sid}')
    print(f'PASS development examples: {len(ex)} · 2016-2024 REG')
    print('PASS 2025 holdout: NOT EVALUATED / 0 labels admitted')
    print(f'PASS challengers: {", ".join(base_names)}')
    print('PASS nested chronological ensemble: 2022-2024')
    print('PASS empirical metric persistence audit: through 2024 only')
    print('PASS QB layer: DATA_GATED (no fabricated QB weights)')
    print('PASS OddsPapi requests: 0 · market fields disallowed')
    print(f'REPORT: {out/"CHALLENGER_BAKEOFF.md"}')
    print('BUILD PASS — paste CHALLENGER_BAKEOFF.md before any 2025 holdout action')
    return 0
if __name__=='__main__':raise SystemExit(main())

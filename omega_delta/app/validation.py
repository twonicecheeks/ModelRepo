"""Chronological, reproducible challenger evaluation; no silent promotion."""
import csv
import io
import math
import random
from collections import defaultdict
from .core import TARGET, canonical, digest, metrics, now, number, stamp, truth


def period(row):
    parts = row['game_id'].split('_')
    if len(parts)!=4 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError('Chronological validation needs season_week_away_home game IDs.')
    if int(parts[1]) != int(row['week']): raise ValueError('Score week does not match its game ID.')
    return int(parts[0]), int(row['week'])


def calibrated(rows, scale):
    return [dict(r,predicted_xtc=number(r['predicted_xtc'])*scale) for r in rows]


def cluster_interval(rows, scale, seed=20260928, draws=1000):
    games=defaultdict(list)
    for r in rows:
        p,y=number(r['predicted_xtc']),number(r['omega_actual_xtc'])
        games[r['game_id']].append(abs(p-y)-abs(p*scale-y))
    groups=list(games.values())
    if len(groups)<2: return None
    rng=random.Random(seed); samples=[]
    for _ in range(draws):
        chosen=[rng.choice(groups) for _ in groups]
        samples.append(sum(map(sum,chosen))/sum(map(len,chosen)))
    samples.sort()
    return {'low':samples[int(draws*.025)],'high':samples[int(draws*.975)],'games':len(groups),'draws':draws,
            'method':'Percentile game-cluster bootstrap; exploratory, not a profitability interval.'}


def evaluate(rows):
    control=[r for r in rows if r['forecast_track']=='CONTROL' and r.get('omega_actual_xtc') not in ('',None)
             and r.get('predicted_xtc') not in ('',None)]
    control.sort(key=lambda r:(period(r),r['game_id'],r['player_id']))
    weeks=sorted({period(r) for r in control})
    folds=[]
    for test_period in weeks[1:]:
        train=[r for r in control if period(r)<test_period]
        test=[r for r in control if period(r)==test_period]
        # Gamma-prior shrinkage for a Poisson-offset count calibrator. Fixed
        # 100-credit prior is declared here, not selected using the test fold.
        scale=(sum(number(r['omega_actual_xtc']) for r in train)+100)/(sum(number(r['predicted_xtc']) for r in train)+100)
        base=metrics(test); candidate=metrics(calibrated(test,scale))
        folds.append({'test_season':test_period[0],'test_week':test_period[1],'training_periods':[list(p) for p in weeks if p<test_period],
                      'training_rows':len(train),'training_games':len({r['game_id'] for r in train}),
                      'scale':scale,'baseline':base,'challenger':candidate,'mae_improvement':base['mae']-candidate['mae'],
                      'mae_improvement_interval':cluster_interval(test,scale),
                      'matched_snap_diagnostic':{'baseline':metrics([r for r in test if truth(r['defensive_participant'])]),
                                                'challenger':metrics(calibrated([r for r in test if truth(r['defensive_participant'])],scale))}})
    matched=[r for r in control if truth(r['defensive_participant'])]
    unknown=[r for r in control if not truth(r['defensive_participant'])]
    source_ids=sorted({r.get('input_snapshot_id','EXTERNAL') for r in control})
    return {'engine':'OMEGA_V1_VALIDATION','created_at':now(),'target':TARGET,'rows':len(control),'folds':folds,
            'excluded_control_rows':sum(r.get('forecast_track')=='CONTROL' for r in rows)-len(control),
            'input_snapshot_ids':source_ids,'input_digest':digest(canonical(control)),
            'cohorts':{'all':metrics(control),'matched':metrics(matched),'unmatched':metrics(unknown),
                       'nonzero_actual_without_snap_match':sum(number(r['omega_actual_xtc'])>0 for r in unknown)},
            'candidate':'GLOBAL_OFFSET_CALIBRATION_GAMMA100','status':'RESEARCH_ONLY_NO_PROMOTION',
            'release_decision':'Retain archived OMEGA forecasts. This replay cannot establish a new production champion.',
            'limits':['Previously inspected Week 1/2 outcomes make this exploratory chronological replay, not an untouched holdout.',
                      'Week 1 contains only five frozen games. One test week cannot establish stable generalization.',
                      'All evaluable control rows are included. Postgame snap matching is diagnostic only, never a deployment filter.',
                      'This challenger changes means only; it does not claim validated probabilities, participation, or teammate dependence.',
                      'Promotion requires newly frozen future-week tests and probability/settlement validation. No automatic promotion is implemented.']}


def grade_observations(store):
    observations=store.records('outcomes')
    if not observations: raise ValueError('Import a final-outcome CSV first.')
    latest={}
    for r in observations:
        key=(r['game_id'],r['player_id'])
        if key in latest and stamp(r['observed_at']) == stamp(latest[key]['observed_at']):
            fields=('omega_actual_xtc','sportsbook_like_actual','defensive_participant')
            if any(r.get(f,'') != latest[key].get(f,'') for f in fields):
                raise ValueError('Conflicting final observations at the same time; import a later sourced correction.')
        if key not in latest or stamp(r['observed_at'])>=stamp(latest[key]['observed_at']): latest[key]=r
    scores=[]; missing=[]; forecast_ids=set()
    forecasts={(r['game_id'],r['player_id']):r for r in store.forecast_archive()}
    # Use the last stored pregame forecast for each player. Preserve the exact
    # input snapshot in every scored row and never synthesize an actual zero.
    for key,actual in latest.items():
        f=forecasts.get(key)
        if not f: missing.append({'game_id':key[0],'player_id':key[1],'reason':'NO_PREGAME_FORECAST'});continue
        if stamp(actual['observed_at'])<stamp(f['kickoff_utc']): raise ValueError('Final observation predates kickoff.')
        forecast_ids.add(f['input_snapshot_id'])
        for track,field in [('CONTROL','control_xtc'),('ROLE_SHADOW','role_point_xtc')]:
            scores.append({'week':f.get('week') or key[0].split('_')[1], 'game_id':key[0],'player_id':key[1],
                           'player_name':f['player_name'],'team':f['team'],'opponent':f.get('opponent',''),
                           'position_group':f.get('position_group','UNKNOWN'),'forecast_track':track,
                           'predicted_xtc':f[field],'omega_actual_xtc':actual['omega_actual_xtc'],
                           'sportsbook_like_actual':actual.get('sportsbook_like_actual',''),
                           'defensive_participant':actual['defensive_participant'],'role_state':f.get('role_state',''),
                           'forecast_snapshot_id':f['input_snapshot_id'],'outcome_snapshot_id':actual['input_snapshot_id'],
                           'forecast_received_at':f['forecast_received_at'],
                           'forecast_provenance':'SOURCE_REPORTED_CAPTURE_TIME',
                           'actual_source':actual['source'],'actual_observed_at':actual['observed_at']})
    if not scores: raise ValueError('No final outcomes matched a stored pregame forecast; missing results were not graded as zero.')
    buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=list(scores[0]));w.writeheader();w.writerows(scores)
    imported=store.import_file('scores','Version 1 matched final outcomes.csv',buf.getvalue())
    active=store.records('forecasts')
    missing_actuals=[{'game_id':r['game_id'],'player_id':r['player_id']} for r in active if (r['game_id'],r['player_id']) not in latest]
    return dict(imported,matched_player_games=len(scores)//2,unmatched_outcomes=missing,active_forecasts_without_outcomes=missing_actuals,
                forecast_snapshot_ids=sorted(forecast_ids),target=TARGET,official_book_settlement=False)

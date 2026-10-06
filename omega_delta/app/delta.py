"""DELTA persistence and OMEGA interface integration; separate research records."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from .core import canonical, now, stamp
from .delta_model import VERSION, FEATURES, forecast, simulate, numeric, validate_counts, probability_rows
from .mlb_model import postseason_k, usage_factor

ROOT = Path(__file__).resolve().parents[1]


def model_files():
    frozen=json.loads((ROOT/'audit/delta/FROZEN_MODEL.json').read_text())
    for name,expected in frozen.get('engine_sha256',{}).items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected: raise ValueError('DELTA engine differs from its saved freeze; reproduce and version the model before forecasting.')
    return frozen


def params_for(row, frozen):
    year = str(row.get('season') or frozen['season'])
    if year not in frozen['folds']: raise ValueError('DELTA needs a parameters artifact for this season.')
    return frozen['folds'][year]


def project_delta(row, v2, frozen, profile=None):
    result = forecast(row, v2, params_for(row, frozen), profile)
    result['parameters_sha256'] = hashlib.sha256(canonical(params_for(row, frozen)).encode()).hexdigest()
    result['profile_source'] = (profile or {}).get('source')
    if profile and profile.get('research'):
        # Research projections travel with the immutable snapshot, and never
        # overwrite the scored 0.1 hitter probabilities or workload PMF.
        result['research'] = profile['research']
    return result


def validate_profile(profile):
    if not isinstance(profile, dict): raise ValueError('Each DELTA profile must be an object.')
    for key in ['game_id', 'player_id']:
        if not re.fullmatch(r'[1-9][0-9]{0,14}', str(profile.get(key, ''))): raise ValueError(f'An exact MLB {key} is required.')
    if not str(profile.get('source', '')).strip(): raise ValueError('DELTA profile source is required.')
    observed, start = stamp(profile.get('observed_at')), stamp(profile.get('start_at'))
    if observed >= start or observed > stamp(now()): raise ValueError('DELTA features must be observed before first pitch and cannot be future-dated.')
    if start <= stamp(now()): raise ValueError('Import advanced inputs only for a future game.')
    pitcher = profile.get('pitcher', {})
    if not isinstance(pitcher, dict) or not isinstance(profile.get('hitters', {}), dict) or not isinstance(profile.get('context', {}), dict): raise ValueError('Pitcher, hitters and context must be objects.')
    if pitcher.get('hand') not in {None, 'L', 'R'}: raise ValueError('Pitcher hand must be L or R.')
    for pid, hitter in profile.get('hitters', {}).items():
        if not isinstance(hitter, dict): raise ValueError('Each hitter must be an object.')
        if not re.fullmatch(r'[1-9][0-9]{0,14}', pid): raise ValueError('Hitter keys must be exact MLBAM IDs.')
        if hitter.get('hand') not in {None, 'L', 'R', 'S'}: raise ValueError('Hitter hand must be L, R or S.')
        if hitter.get('count_probabilities'): validate_counts(hitter['count_probabilities'])
    for record in [pitcher, *profile.get('hitters', {}).values()]:
        for hand, split in record.get('splits', {}).items():
            if hand not in {'L', 'R'}: raise ValueError('Split keys must be L or R.')
            numeric(split.get('K'), 'split K percent', 0, 100); numeric(split.get('pa'), 'split PA', 0, 1e6)
    if 'bf_pmf' in profile: probability_rows(profile['bf_pmf'], 'bf')
    if profile.get('research'):
        r = profile['research']
        if r.get('status') != 'UNFITTED_RESEARCH_NO_FORECAST_EFFECT' or len(r.get('lineup', [])) != 9:
            raise ValueError('Research matchups require a full unfitted lineup and status.')
        if stamp(r.get('training_end_at')) >= observed or not r.get('source'):
            raise ValueError('Research priors require a source and earlier cutoff.')
    for key in ['feature_model', 'hook_model']:
        model = profile.get(key)
        if not model: continue
        if not model.get('source') or stamp(model.get('training_end_at')) >= start: raise ValueError('Imported models require a source and training cutoff before first pitch.')
        numeric(model.get('intercept', 0), key+' intercept', -35, 35)
        if key == 'feature_model' and set(model.get('coefficients', {}))-set(FEATURES): raise ValueError('Unknown physical/context feature.')
        for name, coef in model.get('coefficients', {}).items(): numeric(coef, name+' coefficient', -20, 20)
    return profile


class Delta:
    def __init__(self, store):
        self.store = store
        self.frozen = model_files()
        self.report = json.loads((ROOT/'audit/delta/BACKTEST_REPORT.json').read_text())
        self.counterfactual = json.loads((ROOT/'audit/delta/POSTSEASON_ESCALATOR_EXPERIMENT.json').read_text())
        inputs=(ROOT/'seed/mlb/REPRODUCTION_INPUTS.jsonl').read_text().splitlines()
        row=next(json.loads(s) for s in reversed(inputs) if json.loads(s)['replay_type']=='K')
        base=next(json.loads(s) for s in (ROOT/'seed/mlb/BASELINE_LEDGER.jsonl').read_text().splitlines()
                  if json.loads(s)['market_type']=='K' and json.loads(s)['game_id']==row['game_id'] and
                  str(json.loads(s)['k_projection']['officialMlbId'])==str(row['starter_input']['officialMlbId']))
        pairs=json.loads((ROOT/'seed/mlb/USAGE_PAIRS.json').read_text())
        v2=postseason_k(base['k_projection'],usage_factor(pairs,row['season'])['factor'])
        self.example=project_delta(row,v2,self.frozen)
        self.example.update(game_date=row['game_date'],actual_k=row['actual_k'],baseline_k=base['xk'],v2_k=v2['expected_k'],status='HISTORICAL_REPLAY')

    def state(self):
        prospective = json.loads((ROOT/'audit/delta/PROSPECTIVE_2026_FREEZE.json').read_text())
        market_path = ROOT/'audit/delta/MARKET_AUDIT_0.1.3.json'
        if market_path.is_file():
            full_market_audit = json.loads(market_path.read_text())
            market_audit = {key: full_market_audit.get(key) for key in
                            ['status','variant','edge_threshold','matched_rows','closing_nonpush_rows',
                             'push_rows','opening_quote_rows','bets','model_vs_market','roi','clv',
                             'by_season','by_book']}
        else:
            market_audit = None
        return {'model_version': VERSION, 'frozen': {k: v for k, v in self.frozen.items() if k != 'folds'},
                'report': self.report,
                'counterfactual': {k:self.counterfactual[k] for k in ['status','n','actual_bf','reference_v2','models']},
                'profile_count': len(self.store.setting('delta_profiles', {})),
                'last_simulation': self.store.setting('delta_simulation'), 'grading': self.store.setting('delta_grading', {}),
                'prospective': {k: prospective[k] for k in ['status','frozen_at','eligible_after','model_version','selection_rule']},
                'market_audit': market_audit,
                'advanced_features': list(FEATURES), 'edge_verified': False,'replay_example':self.example}

    def import_profiles(self, raw, name='delta-profiles.json'):
        try: payload = json.loads(raw)
        except (ValueError, TypeError): raise ValueError('Import a valid DELTA JSON document.') from None
        rows = payload.get('profiles') if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not 1 <= len(rows) <= 64: raise ValueError('Use {"profiles":[...]} with 1–64 pitcher-game profiles.')
        keys = set()
        for row in rows:
            validate_profile(row)
            key = f"{row['game_id']}:{row['player_id']}"
            if key in keys: raise ValueError('Duplicate DELTA pitcher-game profile.')
            keys.add(key)
        sid = self.store.snapshot('delta_profiles', name, raw)
        existing = self.store.setting('delta_profiles', {})
        for row in rows: existing[f"{row['game_id']}:{row['player_id']}"] = dict(row, snapshot_id=sid, received_at=now())
        self.store.set_setting('delta_profiles', existing)
        return {'profiles': len(rows), 'snapshot_id': sid, 'status': 'IMPORTED_UNVERIFIED', 'next_step': 'Refresh playoff inputs before first pitch to create a new saved forecast.'}

    def simulate(self, config):
        sid = str(config.get('snapshot_id', '')); pid = str(config.get('player_id', ''))
        with self.store.lock: record = self.store.db.execute("SELECT * FROM snapshots WHERE id=? AND kind='mlb_forecast'", (sid,)).fetchone()
        if not record: raise ValueError('Choose a saved MLB forecast.')
        payload = json.loads(record['raw'])
        row = next((r for r in payload['inputs'] if r['replay_type'] == 'K' and str(r['starter_input']['officialMlbId']) == pid), None)
        v2 = next((s for s in payload['game']['forecast']['starters'] if s['player_id'] == pid), None)
        if not row or not v2 or not payload['game']['forecast'].get('delta'): raise ValueError('This snapshot has no DELTA inputs for that pitcher; refresh the playoff board.')
        frozen = payload['delta_model']
        profile = payload.get('delta_profiles', {}).get(f"{row['game_id']}:{pid}")
        result = simulate(row, v2, params_for(row, frozen), profile, config.get('draws', 10000), config.get('seed', 61026))
        result.update(game_id=row['game_id'], player_id=pid, player=row['starter_input']['officialName'], input_snapshot_id=sid, created_at=now(), edge_verified=False)
        result['snapshot_id'] = self.store.snapshot('delta_simulation', pid, canonical(result))
        self.store.set_setting('delta_simulation', result)
        return result

    def grade(self, mlb):
        from tools.run_delta_backtest import scores, aggregate
        with self.store.lock: records = self.store.db.execute("SELECT id,raw,received_at FROM snapshots WHERE kind='mlb_forecast' ORDER BY rowid").fetchall()
        selected = {}
        for record in records:
            payload = json.loads(record['raw']); g = payload.get('game', {})
            if not g.get('forecast', {}).get('delta'): continue
            if stamp(g['captured_at']) >= stamp(g['start_at']) or stamp(record['received_at']) >= stamp(g['start_at']): continue
            g['snapshot_id'] = record['id']
            for d in g['forecast']['delta']:
                key = (g['game_id'], d['player_id']); previous = selected.get(key)
                if previous is None or stamp(g['captured_at']) >= stamp(previous['game']['captured_at']): selected[key] = {'game': g, 'delta': d}
        finals, pending, rows = {}, [], []
        mlb.receipts = []
        for gid in {key[0] for key in selected}:
            schedule = mlb.get('/schedule', gamePk=gid, sportId=1)
            games = [g for dt in schedule.get('dates', []) for g in dt.get('games', [])]
            if not games or games[0]['status'].get('abstractGameCode') != 'F': continue
            box = mlb.get('/game/'+gid+'/boxscore'); starters = {}
            for side in ['away', 'home']:
                for p in box.get('teams', {}).get(side, {}).get('players', {}).values():
                    stats = p.get('stats', {}).get('pitching', {})
                    if stats.get('gamesStarted') == 1 and stats.get('strikeOuts') is not None:
                        actual = numeric(stats['strikeOuts'], 'final strikeouts', 0, 100)
                        if not actual.is_integer(): raise ValueError('Final strikeouts must be integer.')
                        starters[str(p['person']['id'])] = int(actual)
            finals[gid] = starters
        for (gid, pid), record in selected.items():
            if gid not in finals or pid not in finals[gid]:
                pending.append({'game_id': gid, 'player_id': pid, 'reason': 'Not final, missing K, or pitcher did not start'}); continue
            g, d, actual = record['game'], record['delta'], finals[gid][pid]
            rows.append({'game_id': gid, 'player_id': pid, 'actual_k': actual, 'forecast_snapshot_id': g['snapshot_id'], 'parameters_sha256': d['parameters_sha256'], 'metrics': {name: scores(actual, d[name]['pmf']) for name in ['pa', 'beta_binomial']}})
        result = {'status': 'PROSPECTIVE_RESEARCH', 'graded_starts': len(rows), 'rows': rows, 'pending': pending, 'models': {name: aggregate(rows, name) for name in ['pa', 'beta_binomial']}, 'selection_rule': 'Latest locally received DELTA snapshot before first pitch, once per game/pitcher.', 'edge_verified': False, 'created_at': now()}
        self.store.snapshot('delta_grading', 'Official final DELTA counts', canonical(result)); self.store.set_setting('delta_grading', result)
        return {'graded_starts': len(rows), 'pending': len(pending), 'status': result['status']}

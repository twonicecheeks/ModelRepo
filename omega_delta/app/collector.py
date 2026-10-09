"""Paired Chrome collector. Captures and models share OMEGA's existing journal."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import math
import re
import secrets
from datetime import datetime, timezone

from .core import canonical, now, stamp


class ChromeCollector:
    def __init__(self, store, mlb):
        self.store, self.mlb = store, mlb

    def pair(self, extension_id):
        if not isinstance(extension_id, str) or not re.fullmatch(r'[a-p]{32}', extension_id):
            raise ValueError('Open OMEGA from its Chrome collector to connect the correct extension.')
        token = secrets.token_urlsafe(32)
        self.store.set_setting('chrome_collector_pair', {
            'extension_id': extension_id, 'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
            'paired_at': now()})
        return {'extension_id': extension_id, 'token': token}

    def authorized(self, origin, token):
        p = self.store.setting('chrome_collector_pair', {})
        return (isinstance(token, str) and bool(token) and
                origin == 'chrome-extension://' + p.get('extension_id', '') and
                hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), p.get('token_sha256', '')))

    def disconnect(self):
        self.store.set_setting('chrome_collector_pair', {})
        return {'disconnected': True}

    def state(self):
        p = self.store.setting('chrome_collector_pair', {})
        return {'connected': bool(p), 'extension_id': p.get('extension_id'),
                'paired_at': p.get('paired_at'), 'last': self.store.setting('chrome_collector_last'),
                'legacy_archive': self.store.setting('chrome_collector_legacy_archive'),
                'authority': 'OMEGA', 'storage': 'OMEGA SQLite journal',
                'supporting_markets': 'ARCHIVED_NOT_AUTOMATIC_WORKLOAD_INPUTS'}

    def ingest(self, capture):
        with self.store.lock:
            return self._ingest(capture)

    def _ingest(self, capture):
        if not isinstance(capture, dict):
            raise ValueError('Capture must be an object.')
        league = capture.get('leagueCode')
        if league == 'legacy':
            if capture.get('schemaVersion') != 'OMEGA_CHROME_LEGACY_ARCHIVE_V1' or not isinstance(capture.get('artifacts'), dict):
                raise ValueError('Invalid legacy Chrome archive.')
            allowed = {'model_pm_table_snapshot_current','model_mlb_official_starter_board_current',
                       'model_mlb_k_projection_board_current','model_mlb_ml_projection_board_current',
                       'model_mlb_slate_radar_current','model_mlb_lineup_transition_baselines',
                       'model_data_pipeline_audit_current','model_mlb_public_research_current',
                       'modelV2LastEdgeBoard','modelV2PreviousEdgeBoard','model_nfl_matchup_research_current',
                       'model_nfl_omega_matchup_current'}
            if not set(capture['artifacts']) <= allowed:
                raise ValueError('Archive contains a key outside the source/model allowlist.')
            sid = self.store.snapshot('chrome_legacy_archive', 'Previous Chrome research records', canonical(capture))
            result = {'snapshot_id':sid,'artifact_count':len(capture['artifacts']),
                      'received_at':now(),'status':'ARCHIVED_NOT_ACTIVATED'}
            self.store.set_setting('chrome_collector_legacy_archive', result)
            return result
        if league not in {'mlb', 'nfl'}:
            raise ValueError('Only MLB and NFL collector payloads are supported.')
        received = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        captured = capture.get('capturedAt')
        if not isinstance(captured, str) or stamp(captured) > stamp(received):
            raise ValueError('Capture needs a timezone-aware timestamp no later than receipt.')
        if league == 'mlb':
            if capture.get('status') != 'PASS' or not isinstance(capture.get('pitcherBoard'), list):
                raise ValueError('Use the validated five-market MLB collector snapshot.')
            if not isinstance(capture.get('matches', {}).get('matches'), list):
                raise ValueError('MLB match identities are missing.')
        else:
            requests = capture.get('requests', {})
            if not requests.get('market', {}).get('ok') or not requests.get('matches', {}).get('ok'):
                raise ValueError('NFL capture requests must have succeeded.')
        raw = canonical(capture)
        sid = 'chrome_capture_' + hashlib.sha256(raw.encode()).hexdigest()[:24]
        with self.store.lock:
            duplicate = self.store.db.execute('SELECT id FROM snapshots WHERE id=?', (sid,)).fetchone()
        if duplicate:
            return {'snapshot_id': sid, 'duplicate': True, 'priced_quotes': 0}
        sid = self.store.snapshot('chrome_capture', 'PropsMadness ' + league.upper(), raw)
        result = {'snapshot_id': sid, 'received_at': received, 'captured_at': captured,
                  'league': league, 'priced_quotes': 0, 'held_quotes': [],
                  'evidence': 'COLLECTED_REFERENCE_ONLY', 'model_authority': 'OMEGA'}
        if league == 'mlb':
            accepted, held = self.mlb_quotes(capture)
            if accepted:
                out = io.StringIO()
                w = csv.DictWriter(out, fieldnames=list(accepted[0]))
                w.writeheader(); w.writerows(accepted)
                priced = self.mlb.import_quotes(out.getvalue(), 'Chrome collector ' + sid)
                result['priced_quotes'] = priced['rows']
            result['held_quotes'] = held[:100]
            result['held_quote_count'] = len(held)
            result['pitchers'] = len(capture['pitcherBoard'])
        else:
            result['offers'] = len(capture['requests']['market']['data'].get('offers', []))
            result['note'] = 'NFL source captured; exact GSIS/settlement reconciliation still required.'
        self.store.set_setting('chrome_collector_last', result)
        self.store.log('CHROME_COLLECTOR', 'OK', f"{league}: saved source; {result['priced_quotes']} research quotes")
        return result

    def mlb_quotes(self, capture):
        """Join by ordered teams + start time, then exact team-scoped starter name.

        PropsMadness numeric IDs are never interpreted as MLBAM IDs. Supporting
        markets are retained, not silently inserted into the frozen model.
        """
        board = self.store.setting('mlb_board', {}).get('games', [])
        matches = {str(x['match']['id']): x['match'] for x in capture['matches']['matches']
                   if isinstance(x, dict) and isinstance(x.get('match'), dict) and 'id' in x['match']}
        accepted, held = [], []
        for p in capture['pitcherBoard']:
            market = p.get('markets', {}).get('player-strikeouts')
            if not market:
                continue
            identity = p.get('player', {})
            name = identity.get('name', '')
            try:
                m = matches[str(p['matchId'])]
                start = float(m['startDateTimestamp'])
                candidates = [g for g in board if g.get('away') == m['awayTeam']['nameAbbreviation'] and
                              g.get('home') == m['homeTeam']['nameAbbreviation'] and
                              abs(stamp(g['start_at']).timestamp() - start) < 1]
                if len(candidates) != 1:
                    raise ValueError('Official game identity unresolved; refresh the OMEGA board.')
                g = candidates[0]
                if not g.get('forecast'):
                    raise ValueError('Waiting for an OMEGA pregame forecast.')
                observed = market.get('observedAt')
                t = stamp(observed)
                if t > stamp(capture['capturedAt']):
                    raise ValueError('Market observation follows the capture timestamp.')
                if t >= stamp(g['start_at']):
                    raise ValueError('Live/postgame quote retained; not a pregame comparison.')
                if t < stamp(g['captured_at']):
                    raise ValueError('Capture predates forecast; capture prices again after the model runs.')
                team = next((m[s+'Team']['nameAbbreviation'] for s in ['away','home']
                             if str(m[s+'Team']['id']) == str(identity.get('teamId'))), None)
                starters = [s for s in g['forecast']['starters'] if s.get('team') == team and
                            s['player'].strip().casefold() == name.strip().casefold()]
                if len(starters) != 1:
                    raise ValueError('Exact team-scoped starting-pitcher identity unresolved.')
                for q in market.get('offers', []):
                    line = q.get('line'); book = q.get('sportsbook', {}).get('name')
                    if line is None or not isinstance(book, str) or not book.strip():
                        continue
                    line = float(line)
                    if not math.isfinite(line) or not 0 <= line <= 99 or line * 2 != int(line * 2):
                        continue
                    for side in ['over','under']:
                        odds = (q.get('odds') or {}).get(side)
                        if odds is None:
                            continue
                        odds = float(odds)
                        if not math.isfinite(odds) or abs(odds) < 100:
                            continue
                        accepted.append({'game_id': g['game_id'], 'market_type': 'K',
                            'player_id': starters[0]['player_id'], 'side': side.upper(), 'line': line,
                            'odds': odds, 'book': book, 'captured_at': observed,
                            'source': 'PropsMadness Chrome collector', 'settlement_definition': 'FULL_GAME'})
            except (ValueError, KeyError, TypeError, StopIteration) as e:
                held.append({'player': name, 'match_id': p.get('matchId'), 'reason': str(e)})
        if len(accepted) > 5000:
            raise ValueError('Capture exceeds the 5,000 priced-quote limit.')
        return accepted, held

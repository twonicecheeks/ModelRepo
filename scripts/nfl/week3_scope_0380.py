"""Week 3 operational contracts. No model fitting or outcome-based selection."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SEASON = 2026
WEEK = 3
PRIOR_WEEKS = (1, 2)
MAX_SOURCE_AGE_SECONDS = 7200


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    d = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError('timezone required: ' + str(value))
    return d.astimezone(timezone.utc)


def team(value):
    s = str(value or '').strip().upper()
    return {'JAC': 'JAX', 'LAR': 'LA', 'STL': 'LA', 'SD': 'LAC', 'OAK': 'LV',
            'GNB': 'GB', 'KAN': 'KC', 'LVR': 'LV', 'NWE': 'NE', 'NOR': 'NO',
            'SFO': 'SF', 'TAM': 'TB', 'WSH': 'WAS'}.get(s, s)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or list(dict.fromkeys(k for r in rows for k in r)) or ['status']
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.tmp')
    temp.write_text(text, encoding='utf-8')
    os.replace(temp, path)


def fresh(value, at=None):
    at = at or utcnow()
    age = (at - aware(value)).total_seconds()
    if age < 0 or age > MAX_SOURCE_AGE_SECONDS:
        raise ValueError(f'source timestamp outside 0–120 minute freshness window: {value}')
    return age


def kickoff(row):
    if row.get('kickoff_utc'):
        return aware(row['kickoff_utc'])
    day, clock = str(row.get('gameday') or ''), str(row.get('gametime') or '')
    if not day or not clock:
        raise ValueError('schedule missing kickoff: ' + str(row.get('game_id')))
    return datetime.fromisoformat(day + 'T' + clock).replace(
        tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)


def remaining_scope(schedule, asof):
    """The complete set still unstarted at one recorded cutoff, not a selected subset."""
    selected, excluded, seen = [], [], set()
    for r in schedule:
        if int(float(r.get('season') or 0)) != SEASON or int(float(r.get('week') or 0)) != WEEK:
            continue
        if str(r.get('game_type') or r.get('season_type') or 'REG') != 'REG':
            continue
        gid = str(r.get('game_id') or '')
        if not gid or gid in seen:
            raise ValueError('missing/duplicate target game: ' + gid)
        seen.add(gid)
        a, h = team(r.get('away_team')), team(r.get('home_team'))
        parts = gid.split('_')
        if (not a or not h or a == h or len(parts) != 4 or
                parts[:2] != [str(SEASON), f'{WEEK:02d}'] or
                team(parts[2]) != a or team(parts[3]) != h):
            raise ValueError('schedule identity mismatch: ' + gid)
        ko = kickoff(r)
        item = {'game_id': gid, 'season': SEASON, 'week': WEEK, 'away_team': a,
                'home_team': h, 'kickoff_utc': ko.isoformat()}
        (selected if ko > asof else excluded).append(item)
    if not seen or not selected:
        raise ValueError('no remaining Week 3 games in verified schedule')
    return sorted(selected, key=lambda r: (r['kickoff_utc'], r['game_id'])), sorted(excluded, key=lambda r: r['game_id'])


def before_kickoff(games, at=None):
    at = at or utcnow()
    late = [r['game_id'] for r in games if kickoff(r) <= at]
    if late:
        raise ValueError('kickoff reached; cannot publish this pregame scope: ' + ', '.join(late))


def prior_complete(schedule):
    rows = [r for r in schedule if int(float(r.get('season') or 0)) == SEASON
            and int(float(r.get('week') or 0)) in PRIOR_WEEKS
            and str(r.get('game_type') or r.get('season_type') or 'REG') == 'REG']
    if {int(float(r['week'])) for r in rows} != set(PRIOR_WEEKS):
        raise ValueError('completed Weeks 1 and 2 schedule is required')
    ids = [str(r.get('game_id') or '') for r in rows]
    if len(ids) != len(set(ids)) or any(not x for x in ids):
        raise ValueError('duplicate/missing prior game identity')
    for r in rows:
        for key in ('home_score', 'away_score'):
            value = r.get(key)
            if value in (None, '') or not math.isfinite(float(value)):
                raise ValueError('prior game has incomplete score: ' + str(r.get('game_id')))
    return rows


def read_asset_rows(path):
    path = Path(path)
    with path.open('rb') as f:
        magic = f.read(4)
    if magic == b'PAR1':
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    return read_csv(path)


def verify_pregame(source_dir, at=None):
    at = at or utcnow()
    source_dir = Path(source_dir)
    meta = json.loads((source_dir / 'PREGAME_SOURCE_MANIFEST.json').read_text())
    if meta.get('season') != SEASON or meta.get('targetWeek') != WEEK:
        raise ValueError('pregame source is not 2026 Week 3')
    fresh(meta['capturedAt'], at)
    if meta.get('marketFieldsRead') != 0 or meta.get('oddsPapiRequests') != 0:
        raise ValueError('pregame source independence contract mismatch')
    for name, m in meta.get('sources', {}).items():
        if m.get('sha256') and sha(source_dir / (name + '.csv')) != m['sha256']:
            raise ValueError('pregame source hash mismatch: ' + name)
    if sha(source_dir / 'normalized_pregame_state.csv') != meta['normalizedStateSha256']:
        raise ValueError('pregame normalized-state hash mismatch')
    schedule = read_csv(source_dir / 'schedule.csv')
    expected, excluded = remaining_scope(schedule, aware(meta['capturedAt']))
    captured = read_csv(source_dir / 'target_games.csv')
    if len(captured) != len(expected) or {r['game_id'] for r in captured} != {r['game_id'] for r in expected}:
        raise ValueError('pregame capture does not cover the entire remaining Week 3 scope')
    exp = {r['game_id']: r for r in expected}
    for r in captured:
        x = exp[r['game_id']]
        if kickoff(r) != kickoff(x) or team(r['away_team']) != x['away_team'] or team(r['home_team']) != x['home_team']:
            raise ValueError('captured schedule identity/kickoff mismatch')
    state = read_csv(source_dir / 'normalized_pregame_state.csv')
    keys = [(r['game_id'], team(r['team']), r['player_id']) for r in state]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate pregame player identity')
    for r in state:
        if r['game_id'] not in exp or int(r['week']) != WEEK:
            raise ValueError('player state outside target scope')
        if team(r['team']) not in {exp[r['game_id']]['away_team'], exp[r['game_id']]['home_team']}:
            raise ValueError('player team outside target game')
    before_kickoff(expected, at)
    return meta, expected, excluded


def resolve_pregame(data_root):
    p = Path(data_root) / 'data/raw/nfl/omega/CURRENT_OMEGA_WEEK3_PREGAME_SOURCE'
    sid = p.read_text().strip()
    if not sid or Path(sid).name != sid:
        raise ValueError('invalid pregame snapshot identity')
    return Path(data_root) / 'data/raw/nfl/omega/prospective_week3_pregame_0380' / sid

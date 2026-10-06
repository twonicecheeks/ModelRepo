"""Optional public pitch-data exports and cutoff-safe DELTA profile preparation.

No historical pitch model is fitted here. The event rows are research inputs;
the generated pregame profile contains measured splits and arsenal only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.delta import validate_profile
from app.delta_research import four_seam_trend, research_matchups

PITCH_COLUMNS = {'game_date', 'game_pk', 'pitcher', 'batter', 'at_bat_number',
                 'pitch_number', 'balls', 'strikes', 'description', 'events'}
PBP_COLUMNS = {'game_pk', 'game_date', 'isPitch', 'type', 'startTime',
               'matchup.pitcher.id', 'matchup.batter.id', 'about.atBatIndex'}
BALL = {'ball', 'blocked_ball', 'pitchout', 'intent_ball'}
CALLED = {'called_strike'}
WHIFF = {'swinging_strike', 'swinging_strike_blocked', 'missed_bunt'}
FOUL = {'foul', 'foul_pitchout'}
IN_PLAY = {'hit_into_play', 'hit_into_play_no_out', 'hit_into_play_score'}
K_EVENTS = {'strikeout', 'strikeout_double_play'}
NON_PA = {'wild_pitch', 'passed_ball', 'balk', 'pickoff_1b', 'pickoff_2b',
          'pickoff_3b', 'caught_stealing_2b', 'caught_stealing_3b',
          'caught_stealing_home', 'pickoff_caught_stealing_2b',
          'pickoff_caught_stealing_3b', 'stolen_base_2b', 'stolen_base_3b',
          'stolen_base_home'}
SWINGS = WHIFF | FOUL | IN_PLAY | {'foul_bunt', 'foul_tip'}


def iso_date(raw):
    if not re.fullmatch(r'\d{4}-\d\d-\d\d', str(raw)):
        raise ValueError('Use a YYYY-MM-DD date.')
    return date.fromisoformat(raw)


def timestamp(raw):
    value = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timestamp needs an explicit timezone.')
    return value.astimezone(timezone.utc)


def player_id(value):
    text = str(value).strip()
    if not re.fullmatch(r'[1-9][0-9]{0,14}', text):
        raise ValueError('Exact positive MLBAM IDs are required.')
    return text


def integer(raw, name, low, high):
    text = str(raw).strip()
    if not re.fullmatch(r'\d+', text) or not low <= int(text) <= high:
        raise ValueError(f'Invalid {name}: {raw!r}')
    return int(text)


def finite(raw):
    try:
        result = float(raw)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def new_output(path):
    target = Path(path).expanduser().resolve()
    if target.exists():
        raise ValueError(f'Output already exists: {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def export_statcast(args):
    """Use pybaseball's public wrapper only when the operator explicitly runs it."""
    first, last = iso_date(args.start), iso_date(args.end)
    if last < first or (last-first).days >= 32:
        raise ValueError('Choose an inclusive range of 1–32 days; run multiple batches for a season.')
    if last >= datetime.now(timezone.utc).date():
        raise ValueError('Export complete previous UTC dates only; today may still be in progress.')
    target = new_output(args.out)
    try:
        from pybaseball import statcast
    except ImportError as exc:
        raise ValueError('Install optional pybaseball and its compatible dependencies in a separate Python environment.') from exc
    with tempfile.TemporaryDirectory(prefix='.delta-statcast-', dir=target.parent) as temporary:
        stage = Path(temporary)
        manifest = {'source': 'pybaseball.statcast / Baseball Savant',
                    'retrieved_at': datetime.now(timezone.utc).isoformat(),
                    'date_start': first.isoformat(), 'date_end': last.isoformat(), 'files': []}
        current = first
        while current <= last:
            end = min(current + timedelta(days=2), last)
            # Small sequential windows avoid the documented 30,000-row response limit.
            frame = statcast(current.isoformat(), end.isoformat(), verbose=False, parallel=False)
            name = f'statcast_{current}_{end}.csv'
            filename = stage / name
            frame.to_csv(filename, index=False)
            manifest['files'].append({'name': name, 'rows': len(frame), 'sha256': sha256(filename)})
            current = end + timedelta(days=1)
        (stage/'MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n')
        os.rename(stage, target)
    return {'output': str(target), 'files': len(manifest['files']),
            'rows': sum(item['rows'] for item in manifest['files'])}


def export_players(args):
    """Fetch only the confirmed starter and the nine official lineup hitters."""
    first, last = iso_date(args.start), iso_date(args.end)
    if last < first or (last-first).days >= 32:
        raise ValueError('Choose an inclusive range of 1–32 days; run multiple batches for a season.')
    if last >= datetime.now(timezone.utc).date():
        raise ValueError('Export complete previous UTC dates only.')
    pitcher = player_id(args.pitcher_id)
    lineup = [player_id(value) for value in args.lineup.split(',')]
    if len(lineup) != 9 or len(set(lineup)) != 9:
        raise ValueError('Provide nine distinct, confirmed lineup MLBAM IDs in batting order.')
    target = new_output(args.out)
    try:
        from pybaseball import statcast_pitcher, statcast_batter
    except ImportError as exc:
        raise ValueError('Install optional pybaseball and compatible dependencies in a separate Python environment.') from exc
    manifest = {'source': 'pybaseball.statcast_pitcher/statcast_batter / Baseball Savant',
                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'date_start': first.isoformat(), 'date_end': last.isoformat(),
                'game_types': 'ALL' if args.include_postseason else 'R_ONLY',
                'pitcher_id': pitcher, 'lineup_ids': lineup, 'files': [], 'missing_players': []}
    with tempfile.TemporaryDirectory(prefix='.delta-players-', dir=target.parent) as temporary:
        stage = Path(temporary)
        for role, pid, fetch, identity in [('pitcher', pitcher, statcast_pitcher, 'pitcher')]+[
                ('batter', pid, statcast_batter, 'batter') for pid in lineup]:
            frame = fetch(first.isoformat(), last.isoformat(), player_id=int(pid))
            if frame is not None and not args.include_postseason:
                if 'game_type' not in frame.columns:
                    raise ValueError('Cannot confirm regular-season game type in pybaseball response.')
                frame = frame.loc[frame['game_type'] == 'R']
            if frame is None or len(frame) == 0:
                if role == 'pitcher':
                    raise ValueError('The selected starter has no pitch history in the requested dates.')
                manifest['missing_players'].append(pid)
                continue
            if identity not in frame.columns:
                raise ValueError(f'pybaseball {role} export lacks MLBAM identity column.')
            identities = set()
            for value in frame[identity].dropna().unique():
                number = finite(value)
                if number is None or not number.is_integer():
                    raise ValueError(f'Invalid MLBAM identity in {role} export.')
                identities.add(player_id(str(int(number))))
            if identities != {pid}:
                raise ValueError(f'pybaseball {role} export returned unexpected player identities.')
            name = f'{role}_{pid}_{first}_{last}.csv'
            filename = stage/name
            frame.to_csv(filename, index=False)
            manifest['files'].append({'role': role, 'player_id': pid, 'name': name,
                                      'rows': len(frame), 'sha256': sha256(filename)})
        (stage/'MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n')
        os.rename(stage, target)
    return {'output': str(target), 'files': len(manifest['files']),
            'rows': sum(item['rows'] for item in manifest['files']),
            'missing_players': manifest['missing_players']}


def checked_exports(directories):
    paths = []
    for raw in directories:
        directory = Path(raw).expanduser().resolve()
        try:
            manifest = json.loads((directory/'MANIFEST.json').read_text())
        except (OSError, ValueError) as exc:
            raise ValueError(f'{directory} has no valid export manifest.') from exc
        files = manifest.get('files')
        if not isinstance(files, list) or not files:
            raise ValueError(f'{directory} has no exported pitch CSVs.')
        names = set()
        for record in files:
            name = record.get('name') if isinstance(record, dict) else None
            if not isinstance(name, str) or Path(name).name != name or not name.endswith('.csv') or name in names:
                raise ValueError('Export manifest has a duplicate or unsafe CSV filename.')
            names.add(name)
            path = directory/name
            if not path.is_file() or path.resolve().parent != directory:
                raise ValueError(f'Export CSV missing or outside its directory: {name}')
            if sha256(path) != record.get('sha256'):
                raise ValueError(f'Export CSV hash differs from its receipt: {name}')
            paths.append(path)
    return paths


def outcome(description):
    if description in BALL:
        return 'ball'
    if description in CALLED:
        return 'called_strike'
    if description in WHIFF:
        return 'whiff'
    if description in FOUL:
        return 'foul'
    if description in IN_PLAY:
        return 'in_play'
    return 'unmapped'


def number_field(row, name, factor=1):
    n = finite(row.get(name))
    return round(n*factor, 6) if n is not None else None


def normalize_pitch(row):
    game_date = iso_date(row['game_date'])
    description = str(row.get('description') or '').strip().lower()
    event = str(row.get('events') or '').strip().lower()
    stand = str(row.get('stand') or '').strip()
    throwing = str(row.get('p_throws') or '').strip()
    for hand in (stand, throwing):
        if hand and hand not in {'L', 'R'}:
            raise ValueError('Statcast stand and p_throws must be L or R when present.')
    zone = finite(row.get('zone'))
    zone = int(zone) if zone is not None and zone.is_integer() and 1 <= zone <= 14 else None
    return {
        'game_date': game_date.isoformat(), 'game_pk': player_id(row['game_pk']),
        'game_type': str(row.get('game_type') or '').strip() or None,
        'pitcher': player_id(row['pitcher']), 'batter': player_id(row['batter']),
        'at_bat_number': integer(row['at_bat_number'], 'at_bat_number', 1, 1000),
        'pitch_number': integer(row['pitch_number'], 'pitch_number', 1, 100),
        'balls': integer(row['balls'], 'balls', 0, 3),
        'strikes': integer(row['strikes'], 'strikes', 0, 2),
        'description': description, 'outcome': outcome(description), 'pa_event': event,
        'stand': stand or None, 'p_throws': throwing or None,
        'pitch_type': str(row.get('pitch_type') or '').strip() or None,
        'velocity_mph': number_field(row, 'release_speed'),
        'spin_rpm': number_field(row, 'release_spin_rate') or number_field(row, 'release_spin'),
        # Savant pfx_x/pfx_z are feet; DELTA's arsenal interface expects inches.
        'horizontal_break_inches': number_field(row, 'pfx_x', 12),
        'vertical_break_inches': number_field(row, 'pfx_z', 12),
        'release_height_feet': number_field(row, 'release_pos_z'),
        'extension_feet': number_field(row, 'release_extension'),
        'zone': zone,
    }


def add_pa(counter, k, event):
    counter[k][0] += 1
    counter[k][1] += event in K_EVENTS


def measured_splits(counter, first_id):
    return {hand: {'pa': v[0], 'K': round(100*v[1]/v[0], 6)}
            for (pid, hand), v in sorted(counter.items()) if pid == first_id and v[0]}


def pitch_traits(rows, pitcher_id):
    pitch_type_count = Counter()
    fields = ('velocity_mph', 'spin_rpm', 'horizontal_break_inches',
              'vertical_break_inches', 'release_height_feet', 'extension_feet')
    totals = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r['pitcher'] != pitcher_id or not r['pitch_type']:
            continue
        pt = r['pitch_type']
        pitch_type_count[pt] += 1
        for field in fields:
            if r[field] is not None:
                totals[pt][field].append(r[field])
    n = sum(pitch_type_count.values())
    if not n:
        return []
    rename = {'velocity_mph': 'velocity', 'spin_rpm': 'spin_rate',
              'horizontal_break_inches': 'horizontal_break',
              'vertical_break_inches': 'vertical_break',
              'release_height_feet': 'release_height', 'extension_feet': 'extension'}
    result = []
    for pt, count in sorted(pitch_type_count.items()):
        item = {'pitch_type': pt, 'usage': count/n, 'sample_pitches': count}
        for raw, named in rename.items():
            values = totals[pt][raw]
            # Omit sparsely tracked fields; missing is never substituted with zero.
            if len(values) >= max(1, math.ceil(.8*count)):
                item[named] = round(sum(values)/len(values), 6)
        result.append(item)
    return result


def add_discipline(bucket, r):
    bucket['pitches'] += 1
    bucket['csw'] += r['outcome'] in {'called_strike', 'whiff'}
    bucket['swing'] += r['description'] in SWINGS
    bucket['whiff'] += r['description'] in WHIFF
    if r['zone'] is not None and r['zone'] >= 11:
        bucket['outside'] += 1
        bucket['chased'] += r['description'] in SWINGS


def discipline(bucket):
    out = {}
    if bucket['pitches']:
        out['csw_pct'] = round(100*bucket['csw']/bucket['pitches'], 6)
    if bucket['swing']:
        out['whiff_pct'] = round(100*bucket['whiff']/bucket['swing'], 6)
    if bucket['outside']:
        out['chase_pct'] = round(100*bucket['chased']/bucket['outside'], 6)
    return out


def load_statcast(paths, cutoff, stream, pitcher_id, lineup, report, starter_game_ids=None):
    seen, pa_seen = {}, {}
    p_splits, b_splits = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    p_hands = set()
    hitter_hands = defaultdict(lambda: defaultdict(Counter))
    pitcher_rows, hitter_discipline = [], defaultdict(Counter)
    pitcher_discipline = Counter()
    all_count = Counter()
    whiffs = defaultdict(Counter)
    report['statcast'] = {'input_rows': 0, 'cutoff_excluded': 0, 'duplicates': 0,
                          'eligible_pitches': 0, 'unmapped_descriptions': {},
                          'pitcher_pa': 0, 'hitter_pa': {}}
    audit = report['statcast']
    for path in paths:
        with path.open(newline='', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames or PITCH_COLUMNS - set(reader.fieldnames):
                raise ValueError(f'{path.name} lacks required Statcast columns: {sorted(PITCH_COLUMNS-set(reader.fieldnames or []))}')
            for raw in reader:
                audit['input_rows'] += 1
                if iso_date(raw['game_date']) >= cutoff:
                    audit['cutoff_excluded'] += 1
                    continue
                r = normalize_pitch(raw)
                key = (r['game_pk'], r['at_bat_number'], r['pitch_number'])
                digest = hashlib.sha256(json.dumps(r, sort_keys=True, separators=(',', ':')).encode()).digest()
                if key in seen:
                    if seen[key] != digest:
                        raise ValueError(f'Conflicting Statcast duplicate at {key}.')
                    audit['duplicates'] += 1
                    continue
                seen[key] = digest
                stream.write(json.dumps(r, separators=(',', ':'))+'\n')
                audit['eligible_pitches'] += 1
                all_count[r['outcome']] += 1
                if r['outcome'] == 'unmapped':
                    audit['unmapped_descriptions'][r['description']] = audit['unmapped_descriptions'].get(r['description'], 0)+1
                if r['pitcher'] == pitcher_id:
                    pitcher_rows.append(r)
                    add_discipline(pitcher_discipline, r)
                    if r['p_throws']:
                        p_hands.add(r['p_throws'])
                if r['batter'] in lineup:
                    if r['p_throws'] and r['stand']:
                        hitter_hands[r['batter']][r['p_throws']][r['stand']] += 1
                    if r['pitch_type']:
                        add_discipline(hitter_discipline[(r['batter'],r['pitch_type'])], r)
                if not r['pa_event'] or r['pa_event'] in NON_PA:
                    continue
                pa_key = (r['game_pk'], r['at_bat_number'])
                if pa_key in pa_seen:
                    raise ValueError(f'Multiple terminal PA events for {pa_key}.')
                pa_seen[pa_key] = r['pa_event']
                if r['pitcher'] == pitcher_id and r['stand']:
                    add_pa(p_splits, (pitcher_id,r['stand']), r['pa_event'])
                    audit['pitcher_pa'] += 1
                if r['batter'] in lineup and r['p_throws']:
                    add_pa(b_splits, (r['batter'],r['p_throws']), r['pa_event'])
                    audit['hitter_pa'][r['batter']] = audit['hitter_pa'].get(r['batter'], 0)+1
    if len(p_hands) > 1:
        raise ValueError('Conflicting pitcher throwing hands in Statcast export.')
    if audit['eligible_pitches'] == 0 or not pitcher_rows:
        raise ValueError('No eligible prior-date pitch history for the selected pitcher.')
    audit['outcomes'] = dict(sorted(all_count.items()))
    profile_pitcher = {'hand': next(iter(p_hands)) if p_hands else None,
                       'splits': measured_splits(p_splits, pitcher_id),
                       'arsenal': pitch_traits(pitcher_rows, pitcher_id),
                       'four_seam_trend': four_seam_trend(pitcher_rows, starter_game_ids),
                       **discipline(pitcher_discipline)}
    hitters = {}
    for player in lineup:
        sides = hitter_hands[player]
        hand = None
        if sides['L'] and sides['R']:
            if sides['L']['R'] and sides['R']['L'] and not sides['L']['L'] and not sides['R']['R']:
                hand = 'S'
            observed = {side for counts in sides.values() for side in counts if counts[side]}
            if hand is None and len(observed) == 1:
                hand = next(iter(observed))
        hitter = {'hand': hand, 'splits': measured_splits(b_splits, player)}
        pitch_types = {}
        for (pid, pt), counts in sorted(hitter_discipline.items()):
            if pid != player:
                continue
            item = {}
            item['swings'] = counts['swing']
            item['whiffs'] = counts['whiff']
            item['sample_pitches'] = counts['pitches']
            if counts['swing'] >= 20:
                item['whiff_pct'] = round(100*counts['whiff']/counts['swing'], 6)
            if counts['outside'] >= 20:
                item['chase_pct'] = round(100*counts['chased']/counts['outside'], 6)
            if counts['pitches']:
                pitch_types[pt] = item
        if pitch_types:
            hitter['pitch_types'] = pitch_types
        hitters[player] = hitter
    return profile_pitcher, hitters


def load_pbp(paths, cutoff, stream, report):
    seen = {}
    summary = {'input_rows': 0, 'cutoff_excluded': 0, 'duplicates': 0,
               'eligible_events': 0, 'pitch_events': 0, 'games': []}
    games = set()
    for path in paths:
        with path.open(newline='', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames or PBP_COLUMNS - set(reader.fieldnames):
                raise ValueError(f'{path.name} lacks required baseballr columns: {sorted(PBP_COLUMNS-set(reader.fieldnames or []))}')
            for raw in reader:
                summary['input_rows'] += 1
                if iso_date(raw['game_date']) >= cutoff:
                    summary['cutoff_excluded'] += 1
                    continue
                game_pk = player_id(raw['game_pk'])
                index = integer(raw['about.atBatIndex'], 'PBP atBatIndex', 0, 1000)
                order = integer(raw.get('index', '0') or '0', 'PBP index', 0, 1000)
                kind = raw['type'].strip()
                start = raw['startTime'].strip()
                event_key = (game_pk, index, order, kind, start)
                r = {'game_pk': game_pk, 'game_date': raw['game_date'],
                     'at_bat_index': index, 'event_index': order, 'type': kind,
                     'start_time': start, 'is_pitch': raw['isPitch'].strip().lower() in {'true', 't', '1'},
                     'pitcher': raw['matchup.pitcher.id'].strip() or None,
                     'batter': raw['matchup.batter.id'].strip() or None,
                     'inning': raw.get('about.inning', '').strip() or None,
                     'outs_before': raw.get('count.outs.start', '').strip() or None,
                     'balls_before': raw.get('count.balls.start', '').strip() or None,
                     'strikes_before': raw.get('count.strikes.start', '').strip() or None,
                     'home_score': raw.get('details.homeScore', '').strip() or None,
                     'away_score': raw.get('details.awayScore', '').strip() or None,
                     'on_1b': raw.get('pre_on_1b', '').strip() or None,
                     'on_2b': raw.get('pre_on_2b', '').strip() or None,
                     'on_3b': raw.get('pre_on_3b', '').strip() or None,
                     'result': raw.get('result.eventType', '').strip() or None,
                     'substitution': raw.get('isSubstitution', '').strip() or None}
                if event_key in seen:
                    if seen[event_key] != r:
                        raise ValueError(f'Conflicting baseballr event duplicate at {event_key}.')
                    summary['duplicates'] += 1
                    continue
                seen[event_key] = r
                stream.write(json.dumps(r, separators=(',', ':'))+'\n')
                games.add(game_pk)
                summary['eligible_events'] += 1
                summary['pitch_events'] += r['is_pitch']
    summary['games'] = sorted(games)
    report['baseballr'] = summary


def prepare(args):
    start = timestamp(args.start_at)
    # OMEGA stores receipt time at second precision; match that contract.
    observed = timestamp(args.observed_at) if args.observed_at else datetime.now(timezone.utc).replace(microsecond=0)
    now = datetime.now(timezone.utc)
    if not observed < start or observed > now or start <= now:
        raise ValueError('Profile requires an observed receipt by now and a future first pitch.')
    # A game dated "yesterday" may still be in progress just after midnight
    # UTC. Without a final timestamp, exclude that date as well as today.
    cutoff = min(start.date(), observed.date()-timedelta(days=1))
    game_id, pitcher_id = player_id(args.game_id), player_id(args.pitcher_id)
    lineup = [player_id(value) for value in args.lineup.split(',')]
    if len(lineup) != 9 or len(set(lineup)) != 9:
        raise ValueError('Provide exactly nine distinct official lineup MLBAM IDs in batting order.')
    pitch_paths = [Path(name).expanduser().resolve() for name in (args.statcast or [])]
    pitch_paths.extend(checked_exports(getattr(args, 'statcast_dir', []) or []))
    sources = [(path, 'statcast') for path in pitch_paths]
    sources += [(Path(name).expanduser().resolve(), 'baseballr') for name in args.pbp]
    starter_game_ids = None
    if getattr(args, 'starter_games', None):
        starts_path = Path(args.starter_games).expanduser().resolve()
        starts = json.loads(starts_path.read_text())
        if not starts.get('source') or timestamp(starts.get('observed_at')) > observed:
            raise ValueError('Confirmed starter-game IDs need a source and receipt no later than the profile.')
        starter_game_ids = {player_id(pk) for pk in starts.get('game_pks', [])}
        if not starter_game_ids:
            raise ValueError('Starter-game identity file has no game_pks.')
    if not pitch_paths:
        raise ValueError('At least one pybaseball/Baseball Savant pitch CSV is required.')
    for path, _ in sources:
        if not path.is_file():
            raise ValueError(f'Missing source CSV: {path}')
    target = new_output(args.out)
    report = {'status': 'UNFITTED_RESEARCH_INPUT',
              'game_id': game_id, 'pitcher_id': pitcher_id,
              'observed_at': observed.isoformat(), 'start_at': start.isoformat(),
              'history_date_exclusive': cutoff.isoformat(),
              'date_policy': 'Whole-game dates before first pitch and at least one full UTC date before local receipt; current and previous UTC dates excluded.',
              'sources': [{'kind': kind, 'name': path.name, 'sha256': sha256(path)} for path, kind in sources],
              'validated_pitch_count_model': False, 'validated_hook_model': False}
    if getattr(args, 'starter_games', None):
        report['starter_games_sha256'] = sha256(starts_path)
    fingerprint = hashlib.sha256(json.dumps(report['sources'],sort_keys=True).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='.delta-profile-', dir=target.parent) as temporary:
        stage = Path(temporary)
        with (stage/'PITCH_EVENTS.jsonl').open('w') as stream:
            pitcher, hitters = load_statcast([p for p,k in sources if k=='statcast'],
                                              cutoff, stream, pitcher_id, set(lineup), report,
                                              starter_game_ids)
        with (stage/'PBP_EVENTS.jsonl').open('w') as stream:
            load_pbp([p for p,k in sources if k=='baseballr'], cutoff, stream, report)
        profile = {'game_id': game_id, 'player_id': pitcher_id,
                   'source': f'pybaseball/Statcast local CSV; receipt SHA256 {fingerprint}',
                   'observed_at': observed.isoformat(), 'start_at': start.isoformat(),
                   'pitcher': pitcher, 'hitters': hitters, 'context': {}}
        if getattr(args, 'research_priors', None):
            prior_path = Path(args.research_priors).expanduser().resolve()
            priors = json.loads(prior_path.read_text())
            analysis = research_matchups(profile, priors, lineup)
            analysis['priors_sha256'] = sha256(prior_path)
            profile['research'] = analysis
            (stage/'RESEARCH_MATCHUPS.json').write_text(json.dumps(analysis, indent=2)+'\n')
            report['research_priors_sha256'] = sha256(prior_path)
            report['research_coverage'] = {'estimated': sum(r['status']=='ESTIMATED_RESEARCH' for r in analysis['lineup']),
                                           'unavailable': sum(r['status']=='UNAVAILABLE' for r in analysis['lineup'])}
        validate_profile(profile)
        (stage/'DELTA_PROFILE.json').write_text(json.dumps({'profiles': [profile]}, indent=2)+'\n')
        (stage/'COVERAGE.json').write_text(json.dumps(report, indent=2)+'\n')
        os.rename(stage, target)
    return {'output': str(target), 'pitch_rows': report['statcast']['eligible_pitches'],
            'pbp_rows': report['baseballr']['eligible_events'],
            'pitcher_pa': report['statcast']['pitcher_pa'], 'status': report['status']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    exporter = sub.add_parser('export-statcast', help='Optional pybaseball fetch of complete prior dates')
    for key in ('start', 'end', 'out'):
        exporter.add_argument('--'+key, required=True)
    exporter.set_defaults(func=export_statcast)
    players = sub.add_parser('export-players', help='Fetch a selected starter and nine hitters, once each')
    for key in ('start', 'end', 'pitcher-id', 'lineup', 'out'):
        players.add_argument('--'+key, required=True)
    players.add_argument('--include-postseason', action='store_true',
                         help='Keep prior postseason rows (default: regular-season game type R only)')
    players.set_defaults(func=export_players)
    converter = sub.add_parser('prepare', help='Build source-audited pregame profile and research rows')
    converter.add_argument('--statcast', action='append', default=[], help='Repeat for individual CSV exports')
    converter.add_argument('--statcast-dir', action='append', default=[], help='Verified pybaseball export directory; repeat for prior batches')
    converter.add_argument('--pbp', action='append', default=[], help='Optional baseballr::mlb_pbp CSV; repeat')
    for key in ('game-id','pitcher-id','lineup','start-at','out'):
        converter.add_argument('--'+key, required=True)
    converter.add_argument('--observed-at', help='Actual local receipt time; defaults to now (UTC)')
    converter.add_argument('--research-priors', help='Optional sourced, prior-date league/player rates for an unfitted matchup report')
    converter.add_argument('--starter-games', help='Sourced JSON of confirmed regular-season start game_pks for the FF trend')
    converter.set_defaults(func=prepare)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(args.func(args), indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'DELTA source error: {exc}\n')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Run frozen OMEGA and QB projections for the complete remaining Week 3 scope.

Code is read from this NFL worktree. All raw data, frozen model artifacts and
new immutable outputs stay under --data-root. No existing weekly slate is required.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import week3_scope_0380 as scope


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def run(py, path, *args):
    subprocess.run([py, str(path), *map(str, args)], check=True)


def run_id():
    return scope.utcnow().strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8]


def freeze_files(root):
    # Snapshot the fitted model payloads, never treat a previous-week forecast as a prerequisite.
    paths = []
    for name in ('CURRENT_QB_MODEL_021', 'CURRENT_QB_MODEL_023'):
        pointer = root / 'data/models/nfl' / name
        directory = root / pointer.read_text().strip()
        paths.extend([pointer, *directory.glob('*.json'), *directory.glob('*.sha256')])
    pointer = root / 'data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN'
    sid = pointer.read_text().strip()
    paths.extend([pointer,
        root / 'data/models/nfl/omega_tackle_016_probability_frozen' / sid / 'OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json',
        root / 'data/models/nfl/omega_tackle_012_blind_2025' / sid / 'OMEGA_2025_GLOBAL_MODELS.json'])
    return {str(p): scope.sha(p) for p in paths}


def refresh_results(code_root, data_root):
    sys.path.insert(0, str(code_root / 'packages/providers/nflverse/src'))
    import snapshot
    pointer = data_root / 'data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT'
    previous = pointer.read_bytes() if pointer.exists() else None
    try:
        manifest = snapshot.acquire_snapshot(data_root, analysis_seasons=(2026,), history_seed_seasons=())
    finally:
        if previous is None:
            pointer.unlink(missing_ok=True)
        else:
            pointer.parent.mkdir(parents=True, exist_ok=True)
            pointer.write_bytes(previous)
    meta = snapshot.load_manifest(manifest, root=data_root)
    for name, season in (('schedules', None), ('play_by_play', 2026), ('players', None)):
        hits = [a for a in meta['assets'] if a.get('source') == name and (season is None or a.get('season') == season)]
        if len(hits) != 1:
            raise ValueError('missing results asset: ' + name)
    scope.atomic_text(data_root / 'data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST', str(manifest.relative_to(data_root)) + '\n')


def load_capture(path):
    raw = json.loads(path.read_text())
    if raw.get('schemaVersion') != 'NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_0.2.4.3':
        raise ValueError('wrong QB capture schema')
    scope.fresh(raw.get('capturedAt'))
    slug = str(raw.get('marketSlug') or '')
    requests = raw.get('requests') or {}
    if not slug or (requests.get(slug) or {}).get('ok') is not True or (requests.get('matches') or {}).get('ok') is not True:
        raise ValueError('QB capture did not complete its passing-yards and matches requests')
    offers = (requests[slug].get('data') or {}).get('offers')
    if not isinstance(offers, list) or not offers:
        raise ValueError('QB capture has no passing-yards offers')
    return raw, offers


def latest_capture(explicit=''):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        load_capture(path)
        return path
    choices = []
    for p in (Path.home() / 'Downloads').glob('NFL_QB_PASSING_YARDS_DIRECT_CAPTURE_*.json'):
        try:
            raw, _ = load_capture(p)
            choices.append((scope.aware(raw['capturedAt']), p))
        except (ValueError, OSError, KeyError, TypeError):
            continue
    if not choices:
        raise ValueError('no valid QB passing-yards capture from the last 120 minutes; run prepare_nfl_week3_qb_capture_0380.command and export from PropsMadness')
    return max(choices, key=lambda x: x[0])[1]


def scoped_matches(adapter, payload, games):
    teams, matches = adapter.match_maps(payload)
    teams = {k: scope.team(v) for k, v in teams.items()}
    by_pair = {(scope.team(g['away_team']), scope.team(g['home_team'])): g for g in games}
    result, seen = {}, set()
    for mid, m in matches.items():
        pair = scope.team(m['away']), scope.team(m['home'])
        if pair not in by_pair:
            continue
        if pair in seen:
            raise ValueError('multiple provider matches for one scheduled matchup: ' + repr(pair))
        seen.add(pair)
        result[mid] = dict(by_pair[pair])
    return teams, result


def starter_rows(adapter, raw, offers, source, games):
    """Market provides current target identity only; exact current-roster GSIS join."""
    teams, matches = scoped_matches(adapter, raw['requests']['matches']['data'], games)
    people = {str(r.get('gsis_id') or ''): r for r in scope.read_csv(source / 'players.csv')}
    identities = defaultdict(set)
    for r in scope.read_csv(source / 'weekly_rosters.csv'):
        if int(float(r.get('season') or 0)) != 2026 or int(float(r.get('week') or 0)) != 3:
            continue
        if str(r.get('game_type') or 'REG') != 'REG' or str(r.get('position') or '').upper() != 'QB':
            continue
        if str(r.get('status') or '').upper() != 'ACT':
            continue
        pid = str(r.get('gsis_id') or '')
        tm = scope.team(r.get('team'))
        names = {adapter.roster_name(r), adapter.roster_name(people.get(pid, {}))}
        for name in names:
            if pid and tm and name:
                identities[(tm, adapter.cname(name))].add(pid)
    candidates = {}
    unresolved = []
    for entry in offers:
        if not isinstance(entry, dict):
            continue
        offer = entry.get('offer') if isinstance(entry.get('offer'), dict) else entry
        bet = offer.get('bet') if isinstance(offer.get('bet'), dict) else {}
        book = (bet.get('sportsbook') or {}).get('name')
        if book not in adapter.TRAD_BOOKS:
            continue
        player = offer.get('player') if isinstance(offer.get('player'), dict) else {}
        name = adapter.pname(player)
        tm = teams.get(str(player.get('teamId') or offer.get('teamId') or ''), '')
        game = matches.get(str(offer.get('matchId') or ''))
        if not game:
            continue
        if tm not in {game['away_team'], game['home_team']} or not name:
            unresolved.append({'game_id': game['game_id'], 'team': tm, 'qb_name': name, 'reason': 'INVALID_MARKET_TEAM_OR_NAME'})
            continue
        ids = identities.get((tm, adapter.cname(name)), set())
        if len(ids) != 1:
            unresolved.append({'game_id': game['game_id'], 'team': tm, 'qb_name': name, 'reason': 'CURRENT_ROSTER_GSIS_ID_MISSING_OR_AMBIGUOUS'})
            continue
        pid = next(iter(ids))
        key = (game['game_id'], tm, pid)
        if key not in candidates:
            candidates[key] = {'game_id': game['game_id'], 'team': tm, 'qb_gsis_id': pid,
                               'qb_name': name, 'identity_source': 'DIRECT_SPORTSBOOK_MARKET',
                               'kickoff_utc': game['kickoff_utc'], 'books': set()}
        candidates[key]['books'].add(book)
    by_team = defaultdict(list)
    for r in candidates.values():
        by_team[(r['game_id'], r['team'])].append(r)
    targets = []
    for game in games:
        for tm in (game['away_team'], game['home_team']):
            rows = by_team[(game['game_id'], tm)]
            if len(rows) != 1:
                unresolved.append({'game_id': game['game_id'], 'team': tm, 'reason': 'MISSING_OR_MULTIPLE_MARKET_QBS', 'count': len(rows)})
            else:
                r = dict(rows[0]); r['books'] = '|'.join(sorted(r['books'])); targets.append(r)
    return sorted(targets, key=lambda r: (r['kickoff_utc'], r['game_id'], r['team'])), unresolved


def qb_slate(code_root, data_root, py, source, games, excluded, cap):
    raw, offers = load_capture(cap)
    adapter = module('week3_qb_identity_adapter', code_root / 'scripts/nfl/build_nfl_qb_week2_verified_starters_0243.py')
    rows, unresolved = starter_rows(adapter, raw, offers, source, games)
    directory = data_root / 'data/prospective/nfl/qb_week3_remaining_0245' / run_id()
    directory.mkdir(parents=True, exist_ok=False)
    capture = directory / 'QB_MARKET_SOURCE_CAPTURE.json'
    shutil.copy2(cap, capture)
    scope.write_csv(directory / 'NFL_QB_WEEK3_STARTERS.csv', rows)
    scope.write_csv(directory / 'NFL_QB_WEEK3_UNRESOLVED.csv', unresolved)
    audit = {'version': '0.2.4.5', 'status': 'STARTER_IDENTITY_CHECK', 'createdAt': scope.utcnow().isoformat(),
             'scope': games, 'excludedStartedGames': excluded, 'pregameSource': str(source),
             'capture': str(capture), 'captureSha256': scope.sha(capture), 'captureCapturedAt': raw['capturedAt'],
             'expectedQbs': len(games) * 2, 'resolvedQbs': len(rows), 'unresolved': unresolved,
             'marketFieldsUsedAsModelFeatures': False, 'coefficientRefitPerformed': False,
             'targetOrLater2026OutcomeRowsAdmitted': 0, 'oddsPapiRequests': 0,
             'marketExecutionEligible': False}
    audit_path = directory / 'NFL_QB_WEEK3_AUDIT.json'
    audit_path.write_text(json.dumps(audit, indent=2) + '\n')
    if unresolved or len(rows) != 2 * len(games):
        raise ValueError(f'QB starter identity incomplete; review {directory / "NFL_QB_WEEK3_UNRESOLVED.csv"}')
    output = []
    shared = None
    for i, row in enumerate(rows, 1):
        scope.before_kickoff(games)
        print(f'QB {i}/{len(rows)}: {row["qb_name"]} · {row["game_id"]}', flush=True)
        args = ['--root', str(data_root), '--code-root', str(code_root), '--game-id', row['game_id'],
                '--team', row['team'], '--qb-gsis-id', row['qb_gsis_id'], '--qb-name', row['qb_name'],
                '--identity-source', row['identity_source'], '--kickoff-utc', row['kickoff_utc']]
        if shared:
            args += ['--source-manifest', str(shared)]
        run(py, code_root / 'scripts/nfl/score_nfl_qb_week3_asof_0245.py', *args)
        pointer = data_root / 'data/prospective/nfl/CURRENT_QB_PASSING_YARDS_WEEK3_0245'
        score_path = data_root / pointer.read_text().strip() / 'NFL_QB_PASSING_YARDS_ASOF_SCORE.json'
        score = json.loads(score_path.read_text())
        target = score['target']
        if (target['game_id'], target['team'], target['qb_gsis_id']) != (row['game_id'], row['team'], row['qb_gsis_id']):
            raise ValueError('QB score identity mismatch')
        if (score.get('coefficientRefitPerformed') is not False or score.get('candidateReselectionPerformed') is not False
                or score.get('targetOrLater2026OutcomeRowsAdmitted') != 0 or score.get('marketPriceFieldsAdmitted') != 0
                or score.get('max2026HistoryWeek') != 2):
            raise ValueError('QB score prior-history/frozen-model invariants failed')
        observed_source = (data_root / score['sourceProspectiveManifest']).resolve()
        if shared and shared != observed_source:
            raise ValueError('QB shared prospective source changed during the slate')
        shared = observed_source
        d = score['frozenPredictiveDistribution']
        output.append({'game_id': row['game_id'], 'team': row['team'], 'opponent': target['opponent'],
                       'qb_name': row['qb_name'], 'qb_gsis_id': row['qb_gsis_id'], 'kickoff_utc': row['kickoff_utc'],
                       'projection_passing_yards': score['projectionPassingYards'], 'predictive_p50': d['predictiveQuantiles']['p50'],
                       'central80_low': d['central80'][0], 'central80_high': d['central80'][1],
                       'score_path': str(score_path.relative_to(data_root)), 'score_sha256': scope.sha(score_path)})
    scope.before_kickoff(games)
    board = directory / 'NFL_QB_PASSING_YARDS_SLATE_PROJECTIONS.csv'
    scope.write_csv(board, output)
    audit.update({'status': 'PROSPECTIVE_SHADOW_SLATE_COMPLETE', 'completedAt': scope.utcnow().isoformat(),
                  'sharedProspectiveSourceManifest': str(shared), 'boardSha256': scope.sha(board), 'rows': len(output)})
    audit_path.write_text(json.dumps(audit, indent=2) + '\n')
    scope.before_kickoff(games)
    scope.atomic_text(data_root / 'data/prospective/nfl/CURRENT_QB_WEEK3_REMAINING_0245', str(directory.relative_to(data_root)) + '\n')
    print(f'QB FORECAST BOARD: {board}', flush=True)
    run(py, code_root / 'scripts/nfl/evaluate_nfl_qb_week3_market_0262.py', '--code-root', code_root,
        '--data-root', data_root, '--capture', capture)
    return directory


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--code-root', default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument('--data-root', default='/Users/abbeyfelix/Developer/MODEL')
    ap.add_argument('--mode', choices=('all', 'omega', 'qb'), default='all')
    ap.add_argument('--capture', default='')
    ap.add_argument('--reuse-pregame', action='store_true', help='reuse a verified Week 3 source captured within 120 minutes')
    args = ap.parse_args()
    code_root, data_root = Path(args.code_root).resolve(), Path(args.data_root).expanduser().resolve()
    py = sys.executable
    before = freeze_files(data_root)
    import pyarrow.parquet  # noqa: F401 -- fail before downloads if the pinned environment is absent
    report_dir = data_root / 'data/prospective/nfl/week3_runs_0380' / run_id()
    report_dir.mkdir(parents=True, exist_ok=False)
    report = {'version': '0.38.0', 'startedAt': scope.utcnow().isoformat(), 'codeRoot': str(code_root),
              'dataRoot': str(data_root), 'mode': args.mode, 'omegaStatus': 'NOT_REQUESTED', 'qbStatus': 'NOT_REQUESTED',
              'status': 'RUNNING', 'frozenModelHashesBefore': before, 'oddsPapiRequests': 0}
    try:
        if not args.reuse_pregame:
            run(py, code_root / 'scripts/nfl/capture_nfl_week3_pregame_0380.py', '--root', data_root, '--week', '3')
        source = scope.resolve_pregame(data_root)
        meta, games, excluded = scope.verify_pregame(source)
        report.update({'pregameSource': str(source), 'selectedGames': games, 'excludedStartedGames': excluded})
        print(f'WEEK 3: {len(games)} remaining games; {len(excluded)} started games excluded', flush=True)
        if args.mode in ('all', 'omega'):
            report['omegaStatus'] = 'RUNNING'
            refresh_results(code_root, data_root)
            run(py, code_root / 'scripts/nfl/refresh_omega_2026_snap_counts_0290.py', '--root', data_root)
            run(py, code_root / 'scripts/nfl/freeze_omega_week3_remaining_0380.py', '--root', data_root, '--code-root', code_root, '--week', '3')
            report['omegaStatus'] = 'FORECAST_COMPLETE_AVAILABILITY_UNVERIFIED'
        if args.mode in ('all', 'qb'):
            report['qbStatus'] = 'RUNNING'
            cap = latest_capture(args.capture)
            report['qbDirectory'] = str(qb_slate(code_root, data_root, py, source, games, excluded, cap))
            report['qbStatus'] = 'SHADOW_FORECAST_AND_MARKET_COMPARISON_COMPLETE'
        report['status'] = 'COMPLETE'
    except BaseException as exc:
        report['status'] = 'BLOCKED'
        report['blocker'] = str(exc)
        raise
    finally:
        changed = [p for p, digest in before.items() if not Path(p).exists() or scope.sha(p) != digest]
        report['frozenModelFilesChanged'] = changed
        if changed:
            report['status'] = 'FAILED_FROZEN_MODEL_INTEGRITY'
        report['finishedAt'] = scope.utcnow().isoformat()
        result = report_dir / 'NFL_WEEK3_RUN_REPORT.json'
        result.write_text(json.dumps(report, indent=2) + '\n')
        print(f'RUN REPORT: {result}', flush=True)
        print(f'RUN STATUS: {report["status"]}; OMEGA: {report["omegaStatus"]}; QB: {report["qbStatus"]}', flush=True)
        if changed:
            raise RuntimeError('frozen model artifacts changed during run: ' + ', '.join(changed))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, importlib.util, json, subprocess, sys, zipfile
from collections import Counter
from typing import Any

ROOT = Path('/Users/abbeyfelix/Developer/MODEL')
OLD = ROOT / 'scripts/nfl/import_omega_propsmadness_nfl_ta_direct_01710.py'
EXPECTED_SCHEMA = 'OMEGA_PM_NFL_TA_DIRECT_CAPTURE_0.17.6'
EXPECTED_SLUG = 'player-tackles-assists'


def load_old():
    spec = importlib.util.spec_from_file_location('omega_pm_01710_helpers', OLD)
    if spec is None or spec.loader is None:
        raise SystemExit(f'FAIL cannot load 0.17.10 helpers: {OLD}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def team_abbr(t: Any) -> str:
    if not isinstance(t, dict):
        return ''
    for k in ('nameAbbreviation', 'abbreviation', 'abbr', 'code', 'shortName', 'name'):
        v = t.get(k)
        if v not in (None, ''):
            return str(v).strip()
    return ''


def team_id(t: Any) -> str:
    if not isinstance(t, dict):
        return ''
    for k in ('id', 'teamId', 'team_id'):
        v = t.get(k)
        if v not in (None, ''):
            return str(v)
    return ''


def iso_from_epoch(v: Any) -> str:
    if v in (None, ''):
        return ''
    try:
        return datetime.fromtimestamp(float(v), tz=timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    except Exception:
        return str(v)


def extract_matches(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw = payload.get('matches')
        if isinstance(raw, list):
            out = []
            for x in raw:
                if not isinstance(x, dict):
                    continue
                m = x.get('match') if isinstance(x.get('match'), dict) else x
                out.append(m)
            return out
        for k in ('games', 'events'):
            raw = payload.get(k)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x.get('match', x) for x in payload if isinstance(x, dict)]
    return []


def build_match_maps(payload: Any) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    teams: dict[str, str] = {}
    matches: dict[str, dict[str, str]] = {}
    for m in extract_matches(payload):
        mid = m.get('id') or m.get('matchId') or m.get('match_id') or m.get('eventId')
        if mid in (None, ''):
            continue
        home = m.get('homeTeam') if isinstance(m.get('homeTeam'), dict) else (m.get('home_team') if isinstance(m.get('home_team'), dict) else {})
        away = m.get('awayTeam') if isinstance(m.get('awayTeam'), dict) else (m.get('away_team') if isinstance(m.get('away_team'), dict) else {})
        hid, aid = team_id(home), team_id(away)
        habbr, aabbr = team_abbr(home), team_abbr(away)
        if hid and habbr:
            teams[hid] = habbr
        if aid and aabbr:
            teams[aid] = aabbr
        start = ''
        if m.get('startDateTimestamp') not in (None, ''):
            start = iso_from_epoch(m.get('startDateTimestamp'))
        else:
            for k in ('startTime', 'startDate', 'date', 'gameDate'):
                if m.get(k) not in (None, ''):
                    start = str(m.get(k))
                    break
        matches[str(mid)] = {
            'home_team': habbr,
            'away_team': aabbr,
            'home_team_id': hid,
            'away_team_id': aid,
            'game_date': start,
            'status': str(m.get('status') or ''),
        }
    return teams, matches


def player_name(player: dict[str, Any]) -> str:
    v = player.get('name') or player.get('fullName')
    if v:
        return str(v).strip()
    return ' '.join(str(x).strip() for x in (player.get('firstName'), player.get('lastName')) if x).strip()


def row_from_offer(mod, entry: dict[str, Any], payload_market: dict[str, Any], teams: dict[str, str], matches: dict[str, dict[str, str]], captured: str, idx: int) -> tuple[dict[str, str], str]:
    root = entry.get('offer') if isinstance(entry.get('offer'), dict) else entry
    offer_type = str(root.get('offerType') or '').strip()
    is_reference = offer_type == 'noOffer'
    quote = root.get('referenceBet') if is_reference else root.get('bet')
    if not isinstance(quote, dict):
        raise ValueError('missing quote object')

    sportsbook = quote.get('sportsbook') if isinstance(quote.get('sportsbook'), dict) else {}
    book = sportsbook.get('name') or sportsbook.get('slug') or sportsbook.get('id')
    if not book:
        raise ValueError('missing sportsbook')

    line = mod.recursive_line(quote)
    if line is None:
        raise ValueError('missing line')
    over, under = mod.odds_pair(quote.get('odds'))
    if over is None and under is None:
        over, under = mod.recursive_side_odds(quote)
    if over is None and under is None:
        raise ValueError('missing over/under American odds')

    player = root.get('player') if isinstance(root.get('player'), dict) else {}
    pname = player_name(player)
    if not pname:
        raise ValueError('missing player name')
    pid = player.get('id') or root.get('playerId') or ''
    pteam_id = str(player.get('teamId') or player.get('team_id') or root.get('teamId') or '')
    pteam = teams.get(pteam_id, '')

    mid = str(root.get('matchId') or root.get('match_id') or '')
    mm = matches.get(mid, {})
    home, away = mm.get('home_team', ''), mm.get('away_team', '')
    opponent = ''
    if pteam and pteam == home:
        opponent = away
    elif pteam and pteam == away:
        opponent = home

    market = quote.get('market') if isinstance(quote.get('market'), dict) else payload_market
    injury = entry.get('injury') if isinstance(entry.get('injury'), dict) else {}
    injury_bits = []
    if injury.get('status'):
        injury_bits.append(f"injury_status={injury.get('status')}")
    if injury.get('statusDetail'):
        injury_bits.append(f"injury_detail={injury.get('statusDetail')}")

    classification = 'REFERENCE_ONLY_NON_EXECUTABLE' if is_reference else 'EXECUTABLE_OFFER'
    notes = [classification, f"PropsMadness market slug {market.get('slug') or payload_market.get('slug') or EXPECTED_SLUG}"]
    notes.extend(injury_bits)

    r = {k: '' for k in mod.FIELDS}
    r.update({
        'captured_at': captured,
        'source': 'propsmadness-reference-api' if is_reference else 'propsmadness-table-api',
        'book': str(book),
        'game_id': mid,
        'game_date': mm.get('game_date', ''),
        'away_team': away,
        'home_team': home,
        'player_id': str(pid),
        'player_name': pname,
        'player_team': pteam,
        'opponent': opponent,
        'market_kind': 'tackles_assists',
        'market_label': str(market.get('name') or payload_market.get('name') or 'Tackles + Assists'),
        'line': str(float(line)).rstrip('0').rstrip('.'),
        'settlement_scope': 'UNKNOWN',
        'includes_special_teams': 'UNKNOWN',
        'stat_correction_policy': 'UNKNOWN',
        'source_event_id': f'{mid}:{pid or pname}:{book}:{line}:{idx}',
        'notes': '; '.join(notes),
    })
    if over is not None and under is not None:
        r['over_odds_american'] = str(over)
        r['under_odds_american'] = str(under)
    elif over is not None:
        r['one_sided_side'] = 'OVER'
        r['one_sided_odds_american'] = str(over)
    else:
        r['one_sided_side'] = 'UNDER'
        r['one_sided_odds_american'] = str(under)
    return r, classification


def main() -> int:
    mod = load_old()
    downloads = Path.home() / 'Downloads'
    caps = sorted(downloads.glob('OMEGA_0176_PROPSMADNESS_NFL_TA_DIRECT_CAPTURE_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not caps:
        raise SystemExit('FAIL no OMEGA 0.17.6 direct capture found in ~/Downloads')
    src = caps[0]
    raw = src.read_bytes()
    try:
        data = json.loads(raw)
    except Exception as e:
        raise SystemExit(f'FAIL capture is not valid JSON: {e}')
    if data.get('schemaVersion') != EXPECTED_SCHEMA:
        raise SystemExit(f"FAIL wrong capture schema: {data.get('schemaVersion')}")
    if data.get('marketSlug') != EXPECTED_SLUG:
        raise SystemExit('FAIL capture market slug mismatch')

    req = data.get('requests') or {}
    market_req = req.get('market') or {}
    matches_req = req.get('matches') or {}
    if market_req.get('ok') is not True:
        raise SystemExit(f"FAIL market endpoint HTTP {market_req.get('status')}")
    if matches_req.get('ok') is not True:
        raise SystemExit(f"FAIL matches endpoint HTTP {matches_req.get('status')}")
    payload = market_req.get('data')
    matches_payload = matches_req.get('data')
    if not isinstance(payload, dict) or not isinstance(payload.get('offers'), list) or not payload.get('offers'):
        raise SystemExit('FAIL market payload offers[] missing/empty')
    if not isinstance(matches_payload, (dict, list)):
        raise SystemExit('FAIL matches payload missing')
    pm = payload.get('market') if isinstance(payload.get('market'), dict) else {}
    if pm.get('slug') and pm.get('slug') != EXPECTED_SLUG:
        raise SystemExit(f"FAIL observed market slug {pm.get('slug')} != {EXPECTED_SLUG}")

    teams, matches = build_match_maps(matches_payload)
    if not teams or not matches:
        raise SystemExit(f'FAIL current nested PropsMadness matches schema not resolved · teams {len(teams)} · matches {len(matches)}')

    captured = market_req.get('observedAt') or data.get('capturedAt') or now()
    rows: list[dict[str, str]] = []
    quarantine: list[dict[str, str]] = []
    classes = Counter()
    for i, entry in enumerate(payload['offers']):
        try:
            if not isinstance(entry, dict):
                raise ValueError('offer is not an object')
            r, cls = row_from_offer(mod, entry, pm, teams, matches, captured, i)
            rows.append(r)
            classes[cls] += 1
        except Exception as e:
            quarantine.append({'raw_index': str(i), 'reason': str(e), 'raw_json': json.dumps(entry, ensure_ascii=False, separators=(',', ':'))[:12000]})

    if not rows:
        raise SystemExit(f'FAIL no T+A quotes normalized from {len(payload["offers"])} offers')
    if len(quarantine) / len(payload['offers']) > 0.25:
        raise SystemExit(f'FAIL schema drift: quarantined {len(quarantine)}/{len(payload["offers"])}')

    digest = hashlib.sha256(raw).hexdigest()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    sid = f'{stamp}_{digest[:8]}'
    outdir = ROOT / 'data/raw/nfl/omega/propsmadness_ta_direct_01711' / sid
    outdir.mkdir(parents=True, exist_ok=False)
    (outdir / 'PROPSMADNESS_NFL_TA_DIRECT_CAPTURE.json').write_bytes(raw)

    csvp = outdir / 'OMEGA_TACKLE_MARKET_ROWS_01711.csv'
    with csvp.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=mod.FIELDS, lineterminator='\n')
        w.writeheader(); w.writerows(rows)
    qp = outdir / 'OMEGA_TACKLE_MARKET_QUARANTINE_01711.csv'
    with qp.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['raw_index', 'reason', 'raw_json'], lineterminator='\n')
        w.writeheader(); w.writerows(quarantine)

    audit = {
        'schemaVersion': 'OMEGA_PM_NFL_TA_DIRECT_ADAPTER_AUDIT_0.17.11',
        'sourceId': sid,
        'sourceSha256': digest,
        'marketSlug': EXPECTED_SLUG,
        'endpointOfferRows': len(payload['offers']),
        'normalizedRows': len(rows),
        'quoteClassCounts': dict(classes),
        'quarantinedRows': len(quarantine),
        'teamMapCount': len(teams),
        'matchMapCount': len(matches),
        'rowsWithPlayerTeam': sum(bool(r['player_team']) for r in rows),
        'rowsWithOpponent': sum(bool(r['opponent']) for r in rows),
        'rowsWithGameDate': sum(bool(r['game_date']) for r in rows),
        'twoSidedRows': sum(bool(r['over_odds_american'] and r['under_odds_american']) for r in rows),
        'oneSidedRows': sum(bool(r['one_sided_side']) for r in rows),
        'modelFieldsPresent': False,
        'omegaWrites': 0,
        'oddsPapiRequests': 0,
        'note': '0.17.11 supports nested matches[].match, nameAbbreviation, startDateTimestamp, and preserves noOffer/referenceBet as non-executable market reference rows.'
    }
    (outdir / 'OMEGA_0.17.11_PROPSMADNESS_ADAPTER_AUDIT.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')

    append = ROOT / 'scripts/nfl/append_omega_tackle_market_snapshot_017.py'
    subprocess.run([sys.executable, str(append), str(csvp), '--source', 'propsmadness-direct-api'], check=True)

    print()
    print('OMEGA 0.17.11 — PROPSMADNESS NFL T+A CURRENT-SCHEMA IMPORT')
    print(f'PASS endpoint offers {len(payload["offers"])} · normalized {len(rows)} · quarantine {len(quarantine)}')
    print(f'PASS matches {len(matches)} · teams {len(teams)} · player-team {audit["rowsWithPlayerTeam"]}/{len(rows)} · opponent {audit["rowsWithOpponent"]}/{len(rows)}')
    print(f'PASS quote classes {dict(classes)}')
    print(f'PASS two-sided {audit["twoSidedRows"]} · one-sided {audit["oneSidedRows"]}')
    print('PASS referenceBet/noOffer rows explicitly NON-EXECUTABLE · model fields 0 · OddsPapi 0')
    print(f'AUDIT: {outdir/"OMEGA_0.17.11_PROPSMADNESS_ADAPTER_AUDIT.json"}')

    compare = ROOT / 'scripts/nfl/compare_omega_week2_dual_track_market_0341.py'
    comparison = 'NOT_RUN'
    if compare.exists():
        cp = subprocess.run([sys.executable, str(compare)], text=True, capture_output=True)
        print()
        print('--- OMEGA 0.34.1 WEEK 2 DOWNSTREAM COMPARISON ---')
        if cp.stdout:
            print(cp.stdout.rstrip())
        if cp.returncode != 0:
            if cp.stderr:
                print(cp.stderr.rstrip())
            print(f'NOTE comparison blocked (exit {cp.returncode}); immutable market snapshot remains valid.')
            comparison = 'BLOCKED'
        else:
            comparison = 'PASS'

    handoff = downloads / 'OMEGA_01711_PROPSMADNESS_NFL_TA_ADAPTER_HANDOFF.zip'
    if handoff.exists():
        handoff.unlink()
    with zipfile.ZipFile(handoff, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in (outdir / 'OMEGA_0.17.11_PROPSMADNESS_ADAPTER_AUDIT.json', outdir / 'PROPSMADNESS_NFL_TA_DIRECT_CAPTURE.json', csvp, qp):
            z.write(p, 'OMEGA_01711_HANDOFF/' + p.name)
    print(f'COMPARISON STATUS: {comparison}')
    print(f'UPLOAD: {handoff}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

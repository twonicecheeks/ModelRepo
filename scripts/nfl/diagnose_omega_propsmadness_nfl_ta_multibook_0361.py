#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json

EXPECTED_SLUG = 'player-tackles-assists'


def main() -> int:
    downloads = Path.home() / 'Downloads'
    caps = sorted(
        downloads.glob('OMEGA_0360_PROPSMADNESS_NFL_TA_MULTIBOOK_*.json'),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not caps:
        raise SystemExit('FAIL no OMEGA 0.36 multibook capture found in ~/Downloads')
    src = caps[0]
    data = json.loads(src.read_text(encoding='utf-8'))
    reqs = data.get('playerMarketRequests') or []
    print('OMEGA 0.36.1 — MULTIBOOK CAPTURE DIAGNOSTIC')
    print(f'CAPTURE: {src}')
    print(f'schemaVersion: {data.get("schemaVersion")}')
    print(f'fatalError: {data.get("fatalError")}')
    print(f'player requests: {len(reqs)}')

    http = Counter()
    data_keys = Counter()
    total_bets = 0
    slug_counts = Counter()
    nonnull_line = 0
    any_odds = 0
    expected_slug_rows = 0
    expected_slug_nonnull = 0
    sample = []

    for r in reqs:
        resp = r.get('response') or {}
        http[(resp.get('status'), bool(resp.get('ok')))] += 1
        payload = resp.get('data')
        if isinstance(payload, dict):
            for k in payload.keys():
                data_keys[k] += 1
            bets = payload.get('bets')
            if isinstance(bets, list):
                total_bets += len(bets)
                for b in bets:
                    if not isinstance(b, dict):
                        continue
                    market = b.get('market') if isinstance(b.get('market'), dict) else {}
                    slug = str(market.get('slug') or '')
                    slug_counts[slug] += 1
                    line = b.get('line')
                    odds = b.get('odds') if isinstance(b.get('odds'), dict) else {}
                    has_line = line not in (None, '')
                    has_odds = odds.get('over') not in (None, '') or odds.get('under') not in (None, '')
                    nonnull_line += int(has_line)
                    any_odds += int(has_odds)
                    if slug == EXPECTED_SLUG:
                        expected_slug_rows += 1
                        expected_slug_nonnull += int(has_line and has_odds)
                if bets and len(sample) < 5:
                    sample.append({
                        'playerId': r.get('playerId'),
                        'playerName': r.get('playerName'),
                        'matchId': r.get('matchId'),
                        'endpoint': r.get('endpoint'),
                        'bets_sample': bets[:3],
                    })

    print('HTTP:', dict(http))
    print('response data keys:', dict(data_keys))
    print(f'total bets[] rows: {total_bets}')
    print('market slugs:', dict(slug_counts))
    print(f'rows with non-null line: {nonnull_line}')
    print(f'rows with any odds: {any_odds}')
    print(f'expected slug rows ({EXPECTED_SLUG}): {expected_slug_rows}')
    print(f'expected slug rows with non-null line+odds: {expected_slug_nonnull}')
    print('SAMPLE RESPONSES:')
    for x in sample:
        print(json.dumps(x, ensure_ascii=False, separators=(',', ':'))[:6000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

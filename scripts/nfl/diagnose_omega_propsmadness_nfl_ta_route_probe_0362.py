#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from collections import Counter
import json

EXPECTED_SCHEMA = 'OMEGA_PM_NFL_TA_ROUTE_PROBE_0.36.2'
SLUG = 'player-tackles-assists'


def usable_bet(b):
    if not isinstance(b, dict):
        return False
    m = b.get('market') if isinstance(b.get('market'), dict) else {}
    if m.get('slug') != SLUG:
        return False
    odds = b.get('odds') if isinstance(b.get('odds'), dict) else {}
    return b.get('line') is not None and (odds.get('over') is not None or odds.get('under') is not None)


def generic_ta_rows(payload):
    if not isinstance(payload, dict):
        return []
    raw = payload.get('offer')
    if not isinstance(raw, list):
        return []
    out = []
    for x in raw:
        if not isinstance(x, dict):
            continue
        bet = x.get('bet') if isinstance(x.get('bet'), dict) else {}
        market = bet.get('market') if isinstance(bet.get('market'), dict) else {}
        if market.get('slug') == SLUG:
            out.append(x)
    return out


def main() -> int:
    downloads = Path.home() / 'Downloads'
    caps = sorted(downloads.glob('OMEGA_0362_PROPSMADNESS_NFL_TA_ROUTE_PROBE_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not caps:
        raise SystemExit('FAIL no OMEGA 0.36.2 route-probe capture found in ~/Downloads')
    src = caps[0]
    data = json.loads(src.read_text(encoding='utf-8'))
    if data.get('schemaVersion') != EXPECTED_SCHEMA:
        raise SystemExit(f"FAIL wrong schema {data.get('schemaVersion')}")
    if data.get('fatalError'):
        raise SystemExit(f"FAIL browser probe fatalError: {data.get('fatalError')}")
    probes = data.get('probes')
    if not isinstance(probes, list) or not probes:
        raise SystemExit('FAIL probes[] missing/empty')

    generic_http = Counter()
    alt_http = Counter()
    generic_rows = generic_usable = 0
    alt_rows = alt_usable = 0
    generic_books = Counter()
    alt_books = Counter()
    generic_offer_types = Counter()
    sample_hits = []

    for p in probes:
        gr = p.get('genericResponse') if isinstance(p.get('genericResponse'), dict) else {}
        ar = p.get('altResponse') if isinstance(p.get('altResponse'), dict) else {}
        generic_http[(gr.get('status'), gr.get('ok'))] += 1
        alt_http[(ar.get('status'), ar.get('ok'))] += 1

        gp = gr.get('data')
        for x in generic_ta_rows(gp):
            generic_rows += 1
            generic_offer_types[str(x.get('offerType') or '')] += 1
            bet = x.get('bet') if isinstance(x.get('bet'), dict) else {}
            book = bet.get('sportsbook') if isinstance(bet.get('sportsbook'), dict) else {}
            if book.get('name'):
                generic_books[str(book.get('name'))] += 1
            if usable_bet(bet):
                generic_usable += 1
                if len(sample_hits) < 8:
                    sample_hits.append({'route':'generic','playerName':p.get('playerName'),'matchId':p.get('matchId'),'bet':bet})

        ap = ar.get('data')
        bets = ap.get('bets') if isinstance(ap, dict) and isinstance(ap.get('bets'), list) else []
        alt_rows += len(bets)
        for b in bets:
            if isinstance(b, dict):
                book = b.get('sportsbook') if isinstance(b.get('sportsbook'), dict) else {}
                if book.get('name'):
                    alt_books[str(book.get('name'))] += 1
            if usable_bet(b):
                alt_usable += 1
                if len(sample_hits) < 8:
                    sample_hits.append({'route':'alt','playerName':p.get('playerName'),'matchId':p.get('matchId'),'bet':b})

    print('OMEGA 0.36.2 — PROPSMADNESS NFL T+A ROUTE PROBE DIAGNOSTIC')
    print(f'CAPTURE: {src}')
    print(f'players probed: {len(probes)} · matches: {len({str(x.get("matchId")) for x in probes})}')
    print(f'generic HTTP: {dict(generic_http)}')
    print(f'alt HTTP: {dict(alt_http)}')
    print(f'generic T+A rows: {generic_rows} · usable line+odds: {generic_usable}')
    print(f'generic offer types: {dict(generic_offer_types)}')
    print(f'generic books: {dict(generic_books)}')
    print(f'alt T+A rows: {alt_rows} · usable line+odds: {alt_usable}')
    print(f'alt books: {dict(alt_books)}')
    if sample_hits:
        print('USABLE SAMPLE HITS:')
        for x in sample_hits:
            print(json.dumps(x, separators=(',',':'), ensure_ascii=False))
    else:
        print('USABLE SAMPLE HITS: NONE')

    if generic_usable == 0 and alt_usable == 0:
        print('DIAGNOSIS: PropsMadness currently exposes populated T+A referenceBet rows in Explore, but neither sampled generic player offers nor sampled alternate-line T+A routes expose executable/multibook line+odds data.')
        print('NEXT: retain 0.17.11 reference-only market snapshot; do not promote null multibook placeholders or fabricate book prices.')
    elif generic_usable > 0:
        print('DIAGNOSIS: generic per-player bet-offers contains usable T+A quotes; build a hardened adapter from that route.')
    else:
        print('DIAGNOSIS: alternate T+A route contains usable quotes; build a targeted alt-line adapter from that route.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

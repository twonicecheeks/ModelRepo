#!/usr/bin/env python3
"""OMEGA 0.18.1 — explicit provider-name alias hotfix over frozen 0.18.0 comparison.

Downstream only. No OMEGA model fields, probabilities, coefficients, or frozen artifacts
are changed. This version adds a verified, team-scoped PropsMadness display-name alias:
JuJu Brents (Dolphins) -> Julius Brents.

The underlying 0.18.0 comparison engine remains authoritative for all other behavior.
"""
from __future__ import annotations

from pathlib import Path
import json

import compare_omega_tackle_market_0180 as base

ALIAS_KEY = ('JUJUBRENTS', 'DOLPHINS')
ALIAS_VALUE = 'JULIUSBRENTS'


def main() -> int:
    base.EXPLICIT_PROVIDER_NAME_ALIASES[ALIAS_KEY] = ALIAS_VALUE
    rc = base.main()

    root = Path('/Users/abbeyfelix/Developer/MODEL')
    ptr = root / 'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_MARKET_COMPARISON'
    if ptr.exists():
        sid = ptr.read_text(encoding='utf-8').strip()
        audit = root / 'data/prospective/nfl/omega/market_comparison_0180' / sid / 'OMEGA_0.18.0_MARKET_COMPARISON_AUDIT.json'
        if audit.exists():
            obj = json.loads(audit.read_text(encoding='utf-8'))
            aliases = dict(obj.get('explicitTeamScopedAliases') or {})
            aliases['JUJUBRENTS|DOLPHINS'] = 'JULIUSBRENTS'
            obj['explicitTeamScopedAliases'] = aliases
            obj['identityBridgeVersion'] = '0.18.1'
            obj['identityHotfix'] = 'Verified provider display-name alias JuJu Brents (Miami Dolphins) -> Julius Brents; no fuzzy matching.'
            audit.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
            print('PASS 0.18.1 alias: JuJu Brents (Dolphins) -> Julius Brents')
            print('PASS alias is team-scoped · fuzzy matching remains NO · OMEGA-I unchanged')
    return int(rc or 0)


if __name__ == '__main__':
    raise SystemExit(main())

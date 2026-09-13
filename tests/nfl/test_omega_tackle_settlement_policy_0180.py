#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/compare_omega_tackle_market_0180.py'
spec=importlib.util.spec_from_file_location('m',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

dk=m.settlement_policy_for_book('DraftKings')
assert dk['status']=='RESOLVED'
assert dk['includes_special_teams']=='FALSE'
assert 'DEFENSIVE' in dk['settlement_scope']

ud=m.settlement_policy_for_book('Underdog Fantasy')
assert ud['status']=='RESOLVED'
assert ud['includes_special_teams']=='FALSE'
assert 'SOLO_TACKLES_PLUS_ASSISTS' in ud['settlement_scope']

nv=m.settlement_policy_for_book('Novig')
assert nv['status']=='PARTIAL_UNRESOLVED_SPECIAL_TEAMS'
assert nv['includes_special_teams']=='UNKNOWN'
assert 'NO_REGRADE' in nv['stat_correction_policy']

other=m.settlement_policy_for_book('Unknown Book')
assert other['status']=='UNRESOLVED_UNKNOWN_BOOK'

# Raw settlement fields cannot override book policy.
assert m.settlement_resolved({'book':'DraftKings','settlement_scope':'UNKNOWN'}) is True
assert m.settlement_resolved({'book':'Novig','settlement_scope':'RESOLVED','includes_special_teams':'TRUE','stat_correction_policy':'X'}) is False

print('PASS OMEGA 0.18.0 book-specific settlement policy contracts')

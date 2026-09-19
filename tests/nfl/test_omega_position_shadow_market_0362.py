#!/usr/bin/env python3
from pathlib import Path
import importlib.util

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/compare_omega_position_shadow_market_0362.py'
spec=importlib.util.spec_from_file_location('m0362',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

rows=[
 {'game_id':'G','player_id':'P','book':'DraftKings','line':'7.5',
  'over_odds_american':'-110','under_odds_american':'-120',
  'one_sided_side':'','one_sided_odds_american':'','market_captured_at':'2026-09-19T10:00:00Z'},
 {'game_id':'G','player_id':'P','book':'DraftKings','line':'7.5',
  'over_odds_american':'-110','under_odds_american':'-120',
  'one_sided_side':'','one_sided_odds_american':'','market_captured_at':'2026-09-19T10:01:00Z'},
 {'game_id':'G','player_id':'P','book':'DraftKings','line':'7.5',
  'over_odds_american':'-105','under_odds_american':'-125',
  'one_sided_side':'','one_sided_odds_american':'','market_captured_at':'2026-09-19T10:02:00Z'},
]
out,removed=m.dedupe_market_rows(rows)
assert len(out)==2 and removed==1
same=[r for r in out if r['over_odds_american']=='-110']
assert len(same)==1 and same[0]['market_captured_at']=='2026-09-19T10:01:00Z'
print('PASS OMEGA 0.36.2 repeated-offer dedupe contracts')

#!/usr/bin/env python3
from pathlib import Path
import importlib.util,sys

root=Path(__file__).resolve().parents[2]
p=root/'scripts/nfl/build_omega_week2_market_verification_queue_0351.py'
spec=importlib.util.spec_from_file_location('q0351',p)
m=importlib.util.module_from_spec(spec);sys.modules['q0351']=m;spec.loader.exec_module(m)

base={
  'role_state':'ROLE_ALIGNED','tracks_agree_side':'TRUE','control_best_ev':'0.12',
  'market_quote_classification':'EXECUTABLE_OFFER','book':'DraftKings'
}
assert m.queue_class(base)=='PRIMARY_DIRECT_BOOK_VERIFY'

x=dict(base,market_quote_classification='REFERENCE_ONLY_NON_EXECUTABLE')
assert m.queue_class(x)=='REFERENCE_ONLY_WATCH'

x=dict(base,book='Underdog Fantasy')
assert m.queue_class(x)=='ALTERNATIVE_PLATFORM_REVIEW'

x=dict(base,role_state='REVIEW_BACKUP_CONFLICT')
assert m.queue_class(x)=='BACKUP_CONFLICT_QUARANTINE'

x=dict(base,role_state='STARTER_CONFLICT_REVIEW')
assert m.queue_class(x)=='STARTER_CONFLICT_REVIEW'

x=dict(base,tracks_agree_side='FALSE')
assert m.queue_class(x)=='TRACK_DISAGREEMENT_REVIEW'

rows=[
 {'queue_class':'PRIMARY_DIRECT_BOOK_VERIFY','game_id':'G','player_name':'A','side':'UNDER','control_ev_at_quote':.10,'book':'DraftKings'},
 {'queue_class':'PRIMARY_DIRECT_BOOK_VERIFY','game_id':'G','player_name':'A','side':'UNDER','control_ev_at_quote':.15,'book':'BetMGM'},
 {'queue_class':'PRIMARY_DIRECT_BOOK_VERIFY','game_id':'G','player_name':'B','side':'OVER','control_ev_at_quote':.05,'book':'DraftKings'},
]
best=m.best_primary_per_player(rows)
assert len(best)==2
assert best[0]['player_name']=='A' and best[0]['book']=='BetMGM'
assert m.venue_class('DraftKings')=='TRADITIONAL_SPORTSBOOK'
assert m.venue_class('Props Builder')=='ALTERNATIVE_OR_FANTASY_PLATFORM'
print('PASS OMEGA 0.35.1 mixed executable/reference verification queue contracts')

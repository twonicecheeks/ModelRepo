#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json
import tempfile

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


with tempfile.TemporaryDirectory() as td:
    rr=Path(td)
    (rr/'data/models/nfl').mkdir(parents=True)
    (rr/'data/models/nfl/CURRENT_OMEGA_POSITION_CHALLENGER_0360').write_text('CUR\n')
    cur=rr/'data/models/nfl/omega_position_challenger_0360/CUR'
    cur.mkdir(parents=True)
    report={
      'positionTaxonomy':'ARCHETYPE_GATED_LB_V4',
      'gateSummary':{'LB':'RESEARCH_ONLY_NO_PROMOTION','DB':'RESEARCH_ONLY_NO_PROMOTION','DL':'KEEP_CONTROL','EDGE':'KEEP_CONTROL'}
    }
    (cur/'OMEGA_0.36_POSITION_CHALLENGER_BAKEOFF.json').write_text(json.dumps(report))
    try:
        m.resolve_shadow(rr)
    except SystemExit as e:
        assert 'has not cleared historical shadow gate' in str(e)
    else:
        raise AssertionError('0362 must fail closed when current LB gate is rejected')

    report['gateSummary']['LB']='NEXT_STAGE_SHADOW_SIGNAL'
    (cur/'OMEGA_0.36_POSITION_CHALLENGER_BAKEOFF.json').write_text(json.dumps(report))
    sp=rr/'data/prospective/nfl/omega';sp.mkdir(parents=True)
    sd=rr/'data/prospective/nfl/omega_position_shadow_0361/OLD';sd.mkdir(parents=True)
    (sp/'CURRENT_OMEGA_POSITION_SHADOW_0361').write_text('data/prospective/nfl/omega_position_shadow_0361/OLD\n')
    (sd/'OMEGA_0.36.1_WEEK2_POSITION_SHADOW.csv').write_text('game_id,player_id\nG,P\n')
    audit={'sourcePositionArtifactId':'OLD_ARTIFACT','positionTaxonomy':'ARCHETYPE_GATED_LB_V4','gateSummary':{'LB':'NEXT_STAGE_SHADOW_SIGNAL'}}
    (sd/'OMEGA_0.36.1_WEEK2_POSITION_SHADOW_AUDIT.json').write_text(json.dumps(audit))
    try:
        m.resolve_shadow(rr)
    except SystemExit as e:
        assert 'stale OMEGA 0.36.1 shadow' in str(e)
    else:
        raise AssertionError('0362 must reject stale shadow lineage')

    audit['sourcePositionArtifactId']='CUR'
    (sd/'OMEGA_0.36.1_WEEK2_POSITION_SHADOW_AUDIT.json').write_text(json.dumps(audit))
    p,ap,aud,oid=m.resolve_shadow(rr)
    assert oid=='CUR' and p.exists() and ap.exists() and aud['sourcePositionArtifactId']=='CUR'

print('PASS OMEGA 0.36.2 stale-shadow and rejected-gate fail-closed contracts')

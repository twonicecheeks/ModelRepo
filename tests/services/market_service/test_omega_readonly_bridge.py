#!/usr/bin/env python3
from __future__ import annotations
import csv, importlib.util, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
service=ROOT/'services/market-service/src/model_service.py'
spec=importlib.util.spec_from_file_location('svc_omega',service)
svc=importlib.util.module_from_spec(spec); spec.loader.exec_module(svc)
with tempfile.TemporaryDirectory() as td:
    root=Path(td); base=root/'data/prospective/nfl/omega'; base.mkdir(parents=True)
    pid='P1'; cid='C1'
    (base/'CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER').write_text(pid+'\n')
    (base/'CURRENT_OMEGA_TACKLE_MARKET_COMPARISON').write_text(cid+'\n')
    pp=base/'tackle_probability_016'/pid; pp.mkdir(parents=True)
    with (pp/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['game_id','kickoff_utc','team','opponent','player_name','position','distribution_role_tier','predicted_xtc','predicted_snap_share','verified_ready','verified_block_reason','game_status','injury_designation','listed_starter']);w.writeheader();w.writerow({'game_id':'2026_01_CHI_CAR','kickoff_utc':'2026-09-13T17:00:00Z','team':'CHI','opponent':'CAR','player_name':'Test Defender','position':'LB','distribution_role_tier':'STARTER','predicted_xtc':'7.2','predicted_snap_share':'.88','verified_ready':'TRUE','listed_starter':'TRUE'})
    cp=base/'market_comparison_0180'/cid; cp.mkdir(parents=True)
    with (cp/'OMEGA_0.18.0_MARKET_COMPARISON.csv').open('w',newline='') as f:
        fields=['game_id_model','player_name','team','opponent','line','predicted_xtc','predicted_snap_share','distribution_role_tier','model_p_over','model_p_under','model_vs_novig_over','model_vs_novig_under','market_novig_over','market_novig_under','over_price','under_price','verified_ready','verified_block_reason','market_reference_quality','actionability','actionability_blockers','one_sided_side','one_sided_price','one_sided_break_even','one_sided_prob_edge']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerow({'game_id_model':'2026_01_CHI_CAR','player_name':'Test Defender','team':'CHI','opponent':'CAR','line':'6.5','predicted_xtc':'7.2','predicted_snap_share':'.88','distribution_role_tier':'STARTER','model_p_over':'.61','model_p_under':'.39','model_vs_novig_over':'.09','model_vs_novig_under':'-.09','market_novig_over':'.52','market_novig_under':'.48','over_price':'-105','verified_ready':'TRUE','market_reference_quality':'TWO_SIDED_NO_VIG','actionability':'ACTIONABLE'})
    out=svc.load_omega_nfl_current(root)
    assert out['status']=='PASS',out
    assert out['oddsPapiRequests']==0 and out['readOnly'] is True
    assert out['gameCount']==1 and out['games'][0]['away']=='CHI' and out['games'][0]['home']=='CAR'
    assert out['games'][0]['marketRows'][0]['player']=='Test Defender'
    assert out['games'][0]['marketRows'][0]['side']=='OVER'
    assert abs(out['games'][0]['marketRows'][0]['probabilityEdge']-.09)<1e-9
print('PASS local service 2.3.7 OMEGA bridge: read-only current tackle ledgers, matchup grouping, zero OddsPapi requests')

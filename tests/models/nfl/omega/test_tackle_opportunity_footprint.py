import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[4]
MOD=ROOT/"packages/models/nfl/omega/tackle_opportunity_footprint.py"
spec=importlib.util.spec_from_file_location("tf",MOD); tf=importlib.util.module_from_spec(spec); sys.modules["tf"]=tf; spec.loader.exec_module(tf)


def play(game,season,week,fam,credits,off="B",deff="A"):
    return {"game_id":game,"season":season,"week":week,"posteam":off,"defteam":deff,"play_family":fam,"original_defense_credit_units":credits,"is_nullified_or_deleted":0}


def exp(game,season,week,pid,pct,credits,team="A",pg="LB"):
    return {"game_id":game,"season":season,"week":week,"team":team,"opponent":"B","player_id":pid,"display_name":pid,"position":pg,"position_group":pg,"defense_snaps":pct*60,"defense_pct":pct,"combined_standard_def_scrimmage":credits,"eligible_standard_rate_fit":1}


def event(game,season,week,pid,fam,team="A"):
    return {"game_id":game,"season":season,"week":week,"player_id":pid,"credit_team":team,"play_family":fam,"combined_credit_unit":1,"is_standard_def_scrimmage_credit":1}


class FootprintTests(unittest.TestCase):
    def test_family_share_is_strictly_lagged_and_normalized(self):
        outs=tf.aggregate_team_family_opportunities([
            play("2016_01",2016,1,"RUSH",1), play("2016_01",2016,1,"COMPLETE_PASS",1),
            play("2017_01",2017,1,"RUSH",1), play("2017_01",2017,1,"RUSH",1),
        ])
        a=tf.build_team_family_share_pregame_rows(outs)[0]
        outs2=tf.aggregate_team_family_opportunities([
            play("2016_01",2016,1,"RUSH",1), play("2016_01",2016,1,"COMPLETE_PASS",1),
            play("2017_01",2017,1,"SACK",1), play("2017_01",2017,1,"SACK",1),
        ])
        b=tf.build_team_family_share_pregame_rows(outs2)[0]
        self.assertAlmostEqual(sum(a[f"pred_share_{f}"] for f in tf.FAMILIES),1.0,places=10)
        self.assertAlmostEqual(sum(b[f"pred_share_{f}"] for f in tf.FAMILIES),1.0,places=10)
        for f in tf.FAMILIES:
            self.assertAlmostEqual(a[f"pred_share_{f}"],b[f"pred_share_{f}"],places=12)

    def test_topology_changes_players_differently(self):
        base={"game_id":"g","team":"A","player_id":"p","actual_xtc":5}
        for f in tf.FAMILIES:
            base[f"prior_last8_exposure_{f}"]=100.0
            base[f"prior_last8_credits_{f}"]=10.0
            base[f"position_prior_rate_{f}"]=0.1
        rush=dict(base); rush["prior_last8_credits_RUSH"]=30.0
        pas=dict(base); pas["player_id"]="q"; pas["prior_last8_credits_COMPLETE_PASS"]=30.0
        x={('g','A'):50.0}; e={('g','A','p'):.8,('g','A','q'):.8}
        rs={f:0.0 for f in tf.FAMILIES}; rs['RUSH']=1.0
        ps={f:0.0 for f in tf.FAMILIES}; ps['COMPLETE_PASS']=1.0
        a=tf.score_rows([rush,pas],alpha=10,xto_predictions=x,exposure_predictions=e,family_share_predictions={('g','A'):rs})
        b=tf.score_rows([rush,pas],alpha=10,xto_predictions=x,exposure_predictions=e,family_share_predictions={('g','A'):ps})
        amap={r['player_id']:r['topology_xtc'] for r in a}; bmap={r['player_id']:r['topology_xtc'] for r in b}
        self.assertGreater(amap['p'],amap['q'])
        self.assertGreater(bmap['q'],bmap['p'])

    def test_player_family_credits_reconcile_zero_and_positive(self):
        events=[event('2016_01',2016,1,'p','RUSH'),event('2016_01',2016,1,'p','COMPLETE_PASS')]
        pc=tf.aggregate_player_family_credits(events)
        self.assertEqual(pc[('2016_01','p')]['RUSH'],1.0)
        self.assertEqual(pc[('2016_01','p')]['COMPLETE_PASS'],1.0)
        self.assertEqual(pc[('2016_01','p')]['SACK'],0.0)

    def test_nullified_and_nonopportunity_plays_do_not_count(self):
        rows=[play('2016_01',2016,1,'RUSH',1),play('2016_01',2016,1,'RUSH',0)]
        z=play('2016_01',2016,1,'COMPLETE_PASS',1); z['is_nullified_or_deleted']=1; rows.append(z)
        out=tf.aggregate_team_family_opportunities(rows)[0]
        self.assertEqual(out['total_opportunity_plays'],1)
        self.assertEqual(out['opp_RUSH'],1)
        self.assertEqual(out['opp_COMPLETE_PASS'],0)

    def test_2025_fails_closed(self):
        with self.assertRaises(ValueError):
            tf.aggregate_team_family_opportunities([play('2025_01',2025,1,'RUSH',1)])

if __name__=='__main__': unittest.main()

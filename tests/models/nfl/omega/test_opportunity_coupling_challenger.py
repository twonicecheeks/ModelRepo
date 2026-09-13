import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[4]
MOD=ROOT/"packages/models/nfl/omega/opportunity_coupling_challenger.py"
spec=importlib.util.spec_from_file_location("oc",MOD); oc=importlib.util.module_from_spec(spec); sys.modules["oc"]=oc; spec.loader.exec_module(oc)


def exp_row(game,season,week,pid,pct,credits,team="A",pg="LB"):
    return {"game_id":game,"season":season,"week":week,"team":team,"opponent":"B","player_id":pid,"display_name":pid,"position":pg,"position_group":pg,"defense_snaps":pct*60,"defense_pct":pct,"combined_standard_def_scrimmage":credits,"eligible_standard_rate_fit":1}


def outcome(game,season,week,opp,team="A"):
    return {"game_id":game,"season":season,"week":week,"defense_team":team,"opportunity_plays":opp}


class OpportunityCouplingTests(unittest.TestCase):
    def test_target_game_does_not_enter_rate_features(self):
        rows=[exp_row("2016_01",2016,1,"p",.8,6),exp_row("2017_01",2017,1,"p",.9,10)]
        outs=[outcome("2016_01",2016,1,50),outcome("2017_01",2017,1,70)]
        totals={(r["game_id"],r["team"]):60.0 for r in rows}
        a=oc.build_opportunity_player_rows(rows,outs,totals)[0]
        rows2=[dict(x) for x in rows]; rows2[-1]["combined_standard_def_scrimmage"]=0; rows2[-1]["defense_pct"]=.1
        b=oc.build_opportunity_player_rows(rows2,outs,totals)[0]
        self.assertEqual(a["prior_last8_credits"],b["prior_last8_credits"])
        self.assertEqual(a["prior_last8_opportunity_exposure"],b["prior_last8_opportunity_exposure"])
        self.assertNotEqual(a["actual_xtc"],b["actual_xtc"])

    def test_prediction_increases_with_xto_all_else_equal(self):
        r={"game_id":"g","team":"A","player_id":"p","prior_last8_credits":20.0,"prior_last8_opportunity_exposure":100.0,"position_prior_credit_per_opportunity_exposure":.2,"actual_xtc":5}
        e={("g","A","p"):.8}
        low=oc.score_rows([r],alpha=50,xto_predictions={("g","A"):40},exposure_predictions=e)[0]["opportunity_coupled_xtc"]
        high=oc.score_rows([r],alpha=50,xto_predictions={("g","A"):60},exposure_predictions=e)[0]["opportunity_coupled_xtc"]
        self.assertGreater(high,low)
        self.assertAlmostEqual(high/low,1.5)

    def test_special_teams_only_rows_cannot_enter_when_ineligible(self):
        rows=[exp_row("2016_01",2016,1,"p",.5,1),exp_row("2017_01",2017,1,"q",.5,1)]
        rows[1]["eligible_standard_rate_fit"]=0
        outs=[outcome("2016_01",2016,1,40),outcome("2017_01",2017,1,40)]
        totals={(r["game_id"],r["team"]):60.0 for r in rows}
        out=oc.build_opportunity_player_rows(rows,outs,totals)
        self.assertFalse(any(r["player_id"]=="q" for r in out))

    def test_2025_is_fail_closed(self):
        rows=[exp_row("2025_01",2025,1,"p",.8,5)]
        outs=[outcome("2025_01",2025,1,50)]
        totals={("2025_01","A"):60.0}
        with self.assertRaises(ValueError): oc.build_opportunity_player_rows(rows,outs,totals)

if __name__=="__main__": unittest.main()

import importlib.util
import math
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve()
MOD = HERE.parents[4] / "packages/models/nfl/omega/assist_primary_decomposition.py"
spec = importlib.util.spec_from_file_location("assist_primary_decomposition", MOD)
ad = importlib.util.module_from_spec(spec); spec.loader.exec_module(ad)
FAMS = ("RUSH", "COMPLETE_PASS", "SCRAMBLE", "SACK", "OTHER_PASS")


def exposure(game, season, week, team, pid, pct, xtc, pos="LB"):
    return {
        "game_id": game, "season": str(season), "week": str(week), "team": team,
        "opponent": "OPP", "player_id": pid, "display_name": pid, "position_group": pos,
        "eligible_standard_rate_fit": "1", "defense_pct": str(pct),
        "defense_snaps": str(int(round(60*pct))), "combined_standard_def_scrimmage": str(xtc),
    }


def fam(game, season, week, team, rush=10):
    return {
        "game_id": game, "season": season, "week": week, "offense_team": "OPP", "defense_team": team,
        "total_opportunity_plays": rush,
        "opp_RUSH": rush, "opp_COMPLETE_PASS": 0, "opp_SCRAMBLE": 0, "opp_SACK": 0, "opp_OTHER_PASS": 0,
    }


class TestAssistPrimaryDecomposition(unittest.TestCase):
    def test_credit_roles_and_standard_scope(self):
        events = [
            {"season":"2024","game_id":"g","player_id":"p","play_family":"RUSH","credit_role":"SOLO","combined_credit_unit":"1","is_standard_def_scrimmage_credit":"1"},
            {"season":"2024","game_id":"g","player_id":"p","play_family":"RUSH","credit_role":"PRIMARY_WITH_ASSIST","combined_credit_unit":"1","is_standard_def_scrimmage_credit":"1"},
            {"season":"2024","game_id":"g","player_id":"p","play_family":"RUSH","credit_role":"ASSIST","combined_credit_unit":"1","is_standard_def_scrimmage_credit":"1"},
            {"season":"2024","game_id":"g","player_id":"p","play_family":"RUSH","credit_role":"ASSIST","combined_credit_unit":"1","is_standard_def_scrimmage_credit":"0"},
        ]
        got = ad.aggregate_player_family_credit_classes(events, FAMS)[("g","p")]["RUSH"]
        self.assertEqual(got["primary"], 2.0)
        self.assertEqual(got["assist"], 1.0)

    def test_explicit_zero_player_game_is_preserved_and_reconciles(self):
        exp = [
            exposure("g16",2016,1,"A","p",1.0,1),
            exposure("g17",2017,1,"A","p",1.0,0),
        ]
        f = [fam("g16",2016,1,"A",10), fam("g17",2017,1,"A",10)]
        cc = {("g16","p"):{x:{"primary":0.0,"assist":0.0} for x in FAMS}}
        cc[("g16","p")]["RUSH"]={"primary":1.0,"assist":0.0}
        rows = ad.build_player_credit_class_rows(exp,f,cc,{("g16","A"):60,("g17","A"):60},FAMS)
        self.assertEqual(len(rows),1)
        r=rows[0]
        self.assertEqual(r["actual_xtc"],0.0)
        self.assertEqual(r["actual_credit_class_sum"],0.0)
        self.assertGreater(r["prior_last8_primary_RUSH"],0.0)

    def test_same_week_position_prior_not_updated_mid_week(self):
        exp = [
            exposure("seed",2016,1,"A","seedp",1.0,1),
            exposure("g1",2017,1,"B","p1",1.0,4),
            exposure("g2",2017,1,"C","p2",1.0,0),
        ]
        f = [fam("seed",2016,1,"A",10), fam("g1",2017,1,"B",10), fam("g2",2017,1,"C",10)]
        cc={}
        for g,p,pri,ast in [("seed","seedp",1,0),("g1","p1",4,0)]:
            cc[(g,p)]={x:{"primary":0.0,"assist":0.0} for x in FAMS}
            cc[(g,p)]["RUSH"]={"primary":float(pri),"assist":float(ast)}
        rows=ad.build_player_credit_class_rows(exp,f,cc,{("seed","A"):60,("g1","B"):60,("g2","C"):60},FAMS)
        self.assertEqual(len(rows),2)
        priors=[r["position_prior_primary_rate_RUSH"] for r in rows]
        self.assertAlmostEqual(priors[0],priors[1],places=12)

    def test_equal_alphas_recombine_to_combined_shrinkage(self):
        row={"game_id":"g","team":"A","player_id":"p","actual_xtc":3.0,"position_group":"LB"}
        for f in FAMS:
            row[f"prior_last8_exposure_{f}"]=0.0
            row[f"prior_last8_primary_{f}"]=0.0
            row[f"prior_last8_assist_{f}"]=0.0
            row[f"position_prior_primary_rate_{f}"]=0.0
            row[f"position_prior_assist_rate_{f}"]=0.0
        row["prior_last8_exposure_RUSH"]=20.0
        row["prior_last8_primary_RUSH"]=2.0
        row["prior_last8_assist_RUSH"]=1.0
        row["position_prior_primary_rate_RUSH"]=0.08
        row["position_prior_assist_rate_RUSH"]=0.04
        scored=ad.score_rows([row],primary_alpha=50,assist_alpha=50,xto_predictions={("g","A"):10.0},exposure_predictions={("g","A","p"):1.0},family_share_predictions={("g","A"):{f:(1.0 if f=="RUSH" else 0.0) for f in FAMS}},families=FAMS)[0]
        combined_rate=(3.0+50*(0.12))/(20.0+50.0)
        self.assertAlmostEqual(scored["h004_xtc"],10.0*combined_rate,places=12)

    def test_2025_guard(self):
        with self.assertRaises(ValueError):
            ad.aggregate_player_family_credit_classes([
                {"season":"2025","game_id":"g","player_id":"p","play_family":"RUSH","credit_role":"SOLO","is_standard_def_scrimmage_credit":"1"}
            ], FAMS)


if __name__ == "__main__":
    unittest.main()

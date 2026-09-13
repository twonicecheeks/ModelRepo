import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
OMEGA = HERE.parents[4] / "packages" / "models" / "nfl" / "omega"
sys.path.insert(0, str(OMEGA))
import game_script_elasticity as gs


class GameScriptElasticityTests(unittest.TestCase):
    def test_score_state_boundaries(self):
        self.assertEqual(gs.score_state(-7), "TRAILING_7P")
        self.assertEqual(gs.score_state(-6), "NEUTRAL")
        self.assertEqual(gs.score_state(6), "NEUTRAL")
        self.assertEqual(gs.score_state(7), "LEADING_7P")

    def test_2025_guard(self):
        with self.assertRaises(ValueError):
            gs.aggregate_state_family_opportunities([{
                "season": 2025, "week": 1, "game_id": "g", "posteam": "A", "defteam": "B",
                "play_family": "RUSH", "original_defense_credit_units": 1,
                "is_nullified_or_deleted": 0, "score_differential": 0,
            }])

    def test_aggregate_excludes_non_opportunity_and_nullified(self):
        rows = [
            {"season":2024,"week":1,"game_id":"g","posteam":"A","defteam":"B","play_family":"RUSH","original_defense_credit_units":1,"is_nullified_or_deleted":0,"score_differential":-10},
            {"season":2024,"week":1,"game_id":"g","posteam":"A","defteam":"B","play_family":"COMPLETE_PASS","original_defense_credit_units":0,"is_nullified_or_deleted":0,"score_differential":0},
            {"season":2024,"week":1,"game_id":"g","posteam":"A","defteam":"B","play_family":"SACK","original_defense_credit_units":1,"is_nullified_or_deleted":1,"score_differential":10},
        ]
        out=gs.aggregate_state_family_opportunities(rows)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["total_opportunity_plays"],1)
        self.assertEqual(out[0]["opp_state_TRAILING_7P"],1)
        self.assertEqual(out[0]["opp_TRAILING_7P_RUSH"],1)

    def test_beta_zero_exactly_preserves_h008(self):
        h={"RUSH":.4,"COMPLETE_PASS":.4,"SCRAMBLE":.1,"SACK":.08,"OTHER_PASS":.02}
        s={"RUSH":.1,"COMPLETE_PASS":.6,"SCRAMBLE":.1,"SACK":.1,"OTHER_PASS":.1}
        z=gs.blend_family_shares(h,s,0.0)
        for f in gs.FAMILIES:
            self.assertAlmostEqual(z[f],h[f],places=12)

    def test_same_week_not_leaked(self):
        # 2016 seeds history. Two 2017 week-1 target games are emitted before either
        # updates history, so identical offense/defense priors must yield identical
        # predictions despite radically different target outcomes.
        seed={"game_id":"s","season":2016,"week":17,"offense_team":"A","defense_team":"B","total_opportunity_plays":10}
        for st in gs.STATES:
            seed[f"opp_state_{st}"]=0
            for f in gs.FAMILIES: seed[f"opp_{st}_{f}"]=0
        seed["opp_state_NEUTRAL"]=10;seed["opp_NEUTRAL_RUSH"]=10
        t1={"game_id":"g1","season":2017,"week":1,"offense_team":"A","defense_team":"B","total_opportunity_plays":10}
        t2={"game_id":"g2","season":2017,"week":1,"offense_team":"A","defense_team":"B","total_opportunity_plays":10}
        for t in (t1,t2):
            for st in gs.STATES:
                t[f"opp_state_{st}"]=0
                for f in gs.FAMILIES:t[f"opp_{st}_{f}"]=0
        t1["opp_state_LEADING_7P"]=10;t1["opp_LEADING_7P_COMPLETE_PASS"]=10
        t2["opp_state_TRAILING_7P"]=10;t2["opp_TRAILING_7P_SACK"]=10
        out=gs.build_script_family_pregame_rows([seed,t1,t2])
        r1=next(r for r in out if r["game_id"]=="g1");r2=next(r for r in out if r["game_id"]=="g2")
        for st in gs.STATES:self.assertAlmostEqual(r1[f"pred_state_share_{st}"],r2[f"pred_state_share_{st}"],places=12)
        for f in gs.FAMILIES:self.assertAlmostEqual(r1[f"script_share_{f}"],r2[f"script_share_{f}"],places=12)


if __name__ == "__main__":
    unittest.main()

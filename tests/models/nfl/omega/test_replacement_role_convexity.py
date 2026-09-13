import unittest
from packages.models.nfl.omega import replacement_role_convexity as rc


class ReplacementRoleConvexityTests(unittest.TestCase):
    def test_no_effect_without_activation(self):
        base={"game_id":"g","team":"T","player_id":"p","topology_xtc":5.0,"predicted_snap_share":.70}
        feat={"game_id":"g","team":"T","player_id":"p","prior_games":4,"prechange_baseline_snap_share":.65}
        out=rc.score_rows([base],{("g","T","p"):feat},beta=1.0)[0]
        self.assertEqual(out["h003_activated"],0)
        self.assertAlmostEqual(out["role_convexity_xtc"],5.0)

    def test_positive_jump_is_convex(self):
        base={"game_id":"g","team":"T","player_id":"p","topology_xtc":5.0,"predicted_snap_share":.85}
        feat={"game_id":"g","team":"T","player_id":"p","prior_games":4,"prechange_baseline_snap_share":.55}
        out=rc.score_rows([base],{("g","T","p"):feat},beta=.5)[0]
        self.assertEqual(out["h003_activated"],1)
        self.assertGreater(out["role_convexity_xtc"],5.0)
        self.assertAlmostEqual(out["h003_role_jump"],.30)

    def test_cold_start_does_not_activate(self):
        base={"game_id":"g","team":"T","player_id":"p","topology_xtc":3.0,"predicted_snap_share":.90}
        feat={"game_id":"g","team":"T","player_id":"p","prior_games":0,"prechange_baseline_snap_share":.30}
        out=rc.score_rows([base],{("g","T","p"):feat},beta=1.5)[0]
        self.assertEqual(out["h003_activated"],0)
        self.assertAlmostEqual(out["role_convexity_xtc"],3.0)

    def test_same_week_history_is_not_leaked(self):
        rows=[
            {"season":"2016","week":"1","eligible_standard_rate_fit":"1","game_id":"a","team":"T","player_id":"p","position_group":"LB","defense_pct":"0.2","combined_standard_def_scrimmage":"1"},
            {"season":"2016","week":"2","eligible_standard_rate_fit":"1","game_id":"b","team":"T","player_id":"p","position_group":"LB","defense_pct":"0.8","combined_standard_def_scrimmage":"5"},
            {"season":"2017","week":"1","eligible_standard_rate_fit":"1","game_id":"c","team":"T","player_id":"p","position_group":"LB","defense_pct":"0.9","combined_standard_def_scrimmage":"6"},
        ]
        out=rc.build_role_transition_rows(rows,{})
        target=[r for r in out if r["game_id"]=="c"][0]
        self.assertEqual(target["prior_games"],2)
        self.assertAlmostEqual(target["prechange_baseline_snap_share"],.2)
        self.assertAlmostEqual(target["last1_snap_share"],.8)

    def test_2025_rejected(self):
        rows=[{"season":"2025","week":"1","eligible_standard_rate_fit":"1","game_id":"g","team":"T","player_id":"p","defense_pct":"1","combined_standard_def_scrimmage":"1"}]
        with self.assertRaises(ValueError):
            rc.build_role_transition_rows(rows,{})


if __name__ == "__main__":
    unittest.main()

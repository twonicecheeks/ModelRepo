import unittest

from packages.models.nfl.omega import tackle_funnel_rigidity as fr


class TackleFunnelRigidityTests(unittest.TestCase):
    def test_similarity_identical_and_disjoint(self):
        self.assertAlmostEqual(fr.total_variation_similarity({"a": .6, "b": .4}, {"a": .6, "b": .4}), 1.0)
        self.assertAlmostEqual(fr.total_variation_similarity({"a": 1.0}, {"b": 1.0}), 0.0)

    def test_cold_start_blend_is_frozen_h008(self):
        tr={"game_id":"g","team":"T","player_id":"p","topology_xtc":5.0,"predicted_snap_share":.8,
            **{f"pred_opp_{f}":5.0 for f in fr.FAMILIES}}
        feature={"game_id":"g","team":"T","player_id":"p","prior_mean_snap_share":0.0,"prior_credit_share":0.0,
                 "history_confidence":0.0,"team_funnel_rigidity":1.0,
                 **{f"league_credit_per_opp_{f}":1.0 for f in fr.FAMILIES}}
        out=fr.score_rows([tr],{("g","T","p"):feature},lam=1.0)[0]
        self.assertAlmostEqual(out["funnel_xtc"],5.0)
        self.assertAlmostEqual(out["funnel_effective_weight"],0.0)

    def test_no_target_roster_normalization(self):
        base={"game_id":"g","team":"T","topology_xtc":4.0,"predicted_snap_share":.8,
              **{f"pred_opp_{f}":4.0 for f in fr.FAMILIES}}
        f1={"game_id":"g","team":"T","player_id":"p1","prior_mean_snap_share":.8,"prior_credit_share":.2,
            "history_confidence":1.0,"team_funnel_rigidity":.8,
            **{f"league_credit_per_opp_{f}":1.0 for f in fr.FAMILIES}}
        r1={**base,"player_id":"p1"}
        solo=fr.score_rows([r1],{("g","T","p1"):f1},lam=.5)[0]["funnel_xtc"]
        # Add another target-game player. p1 prediction must be unchanged because no realized participant normalization is allowed.
        f2={**f1,"player_id":"p2","prior_credit_share":.3}
        r2={**base,"player_id":"p2","topology_xtc":3.0}
        both=fr.score_rows([r1,r2],{("g","T","p1"):f1,("g","T","p2"):f2},lam=.5)[0]["funnel_xtc"]
        self.assertAlmostEqual(solo,both)

    def test_2025_rejected(self):
        rows=[{"season":"2025","eligible_standard_rate_fit":"1","game_id":"g","week":"1","team":"T","player_id":"p","defense_pct":"1","combined_standard_def_scrimmage":"1"}]
        with self.assertRaises(ValueError):
            fr.build_funnel_pregame_rows(rows,[],[],{})


if __name__ == "__main__":
    unittest.main()

import unittest
from xto_xtc_baseline import (
    aggregate_team_game_outcomes,
    build_team_pregame_rows,
    build_player_pregame_rows,
    fit_ridge,
    score_player_rows,
    TEAM_FEATURE_NAMES,
)

class OmegaBaselineTests(unittest.TestCase):
    def test_same_week_results_do_not_leak_into_features(self):
        outcomes = []
        # Seed 2016 histories for A offense / B defense and C offense / D defense.
        for game, off, deff, snaps, opp in [
            ("2016_17_A_B", "A", "B", 60, 40),
            ("2016_17_C_D", "C", "D", 70, 50),
            ("2017_01_A_B", "A", "B", 100, 90),
            ("2017_01_C_D", "C", "D", 20, 10),
        ]:
            season = int(game[:4]); week = int(game[5:7])
            outcomes.append({
                "game_id": game, "season": season, "week": week,
                "offense_team": off, "defense_team": deff,
                "defensive_snaps": snaps, "standard_plays": snaps,
                "opportunity_plays": opp, "credit_units": opp,
                "rush_plays": snaps//2, "complete_pass_plays": snaps//3,
                "other_pass_plays": 0, "sack_plays": 1, "scramble_plays": 1,
            })
        rows = build_team_pregame_rows(outcomes)
        y2017 = [r for r in rows if r["season"] == 2017]
        self.assertEqual(len(y2017), 2)
        a = next(r for r in y2017 if r["offense_team"] == "A")
        # Pregame feature must still reflect 2016's 60, not current week's 100.
        self.assertAlmostEqual(a["off_def_snaps_mean8"], 60.0)

    def test_zero_credit_player_remains_a_valid_target(self):
        team_rows = [{
            "game_id":"2016_17_X_Y","season":2016,"week":17,"offense_team":"X","defense_team":"Y",
            "actual_defensive_snaps":60,"actual_opportunity_plays":40,"actual_credit_units":45,
            **{n: 1.0 for n in TEAM_FEATURE_NAMES},
        },{
            "game_id":"2017_01_X_Y","season":2017,"week":1,"offense_team":"X","defense_team":"Y",
            "actual_defensive_snaps":60,"actual_opportunity_plays":40,"actual_credit_units":45,
            **{n: 1.0 for n in TEAM_FEATURE_NAMES},
        }]
        exposure = [
            {"game_id":"2016_17_X_Y","season":2016,"week":17,"team":"Y","opponent":"X","player_id":"p1","position_group":"LB","defense_snaps":30,"defense_pct":.5,"combined_standard_def_scrimmage":0,"eligible_standard_rate_fit":1},
            {"game_id":"2017_01_X_Y","season":2017,"week":1,"team":"Y","opponent":"X","player_id":"p1","position_group":"LB","defense_snaps":30,"defense_pct":.5,"combined_standard_def_scrimmage":0,"eligible_standard_rate_fit":1},
        ]
        pr = build_player_pregame_rows(exposure, team_rows)
        self.assertEqual(len(pr), 1)
        self.assertEqual(pr[0]["actual_xtc"], 0.0)
        scored = score_player_rows(pr, alpha=50, snap_predictions={("2017_01_X_Y","Y"):60})
        self.assertEqual(scored[0]["actual_xtc"], 0.0)

    def test_ridge_learns_simple_signal(self):
        rows=[]
        for i in range(1,30):
            r={n:0.0 for n in TEAM_FEATURE_NAMES}
            r["off_def_snaps_mean8"] = float(i)
            r["actual_defensive_snaps"] = 2.0*float(i)+5.0
            rows.append(r)
        m=fit_ridge(rows,target_key="actual_defensive_snaps",l2=.03)
        x={n:0.0 for n in TEAM_FEATURE_NAMES}; x["off_def_snaps_mean8"]=10.0
        p=m.predict([x[n] for n in TEAM_FEATURE_NAMES])
        self.assertTrue(23.0 < p < 27.0)

    def test_standard_play_aggregation_excludes_special_and_nullified(self):
        plays=[
            {"game_id":"g","season":2024,"week":1,"posteam":"A","defteam":"B","play_family":"RUSH","is_nullified_or_deleted":0,"original_defense_credit_units":1,"original_defense_solo":1,"original_defense_primary_with_assist":0,"original_defense_assists":0},
            {"game_id":"g","season":2024,"week":1,"posteam":"A","defteam":"B","play_family":"SPECIAL_TEAMS","is_nullified_or_deleted":0,"original_defense_credit_units":1},
            {"game_id":"g","season":2024,"week":1,"posteam":"A","defteam":"B","play_family":"RUSH","is_nullified_or_deleted":1,"original_defense_credit_units":1},
        ]
        exposure=[{"game_id":"g","team":"B","eligible_standard_rate_fit":1,"defense_snaps":60,"defense_pct":1.0}]
        out=aggregate_team_game_outcomes(plays, exposure)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["standard_plays"],1)
        self.assertEqual(out[0]["opportunity_plays"],1)

if __name__ == "__main__":
    unittest.main()

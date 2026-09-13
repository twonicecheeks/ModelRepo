import importlib.util, pathlib, unittest

MOD=pathlib.Path(__file__).resolve().parents[4]/"packages/models/nfl/omega/venue_credit_environment.py"
spec=importlib.util.spec_from_file_location("venue_credit_environment",MOD); ve=importlib.util.module_from_spec(spec); spec.loader.exec_module(ve)

class TestVenueEnvironment(unittest.TestCase):
    def test_identity_skips_2025_and_neutral_is_not_home(self):
        rows=[
          {"game_id":"2024_01_A_B","season":"2024","week":"1","source_home_team":"B","home_team":"B","away_team":"A","location":"Home"},
          {"game_id":"2025_01_A_B","season":"2025","week":"1","source_home_team":"B","home_team":"B","away_team":"A","location":"Home"},
        ]
        m=ve.build_game_identity_map(rows)
        self.assertIn("2024_01_A_B",m);self.assertNotIn("2025_01_A_B",m)
        self.assertTrue(ve.is_home_location("Home"));self.assertFalse(ve.is_home_location("Neutral"))

    def test_environment_adjusts_assists_only(self):
        prior={"year_assist_multiplier":1.10,"venue_profiles":{"B":{"shrunk_relative_assist_multiplier":1.20}}}
        ident={"g":{"source_home_team":"B","location":"Home"}}
        rows=[{"game_id":"g","pred_primary_total":4.0,"pred_assist_total":2.0,"h004_xtc":6.0}]
        out=ve.apply_environment(rows,ident,prior)[0]
        self.assertAlmostEqual(out["h005_primary"],4.0)
        self.assertAlmostEqual(out["h005_assist"],2.64)
        self.assertAlmostEqual(out["h005_xtc"],6.64)

    def test_neutral_gets_year_only(self):
        prior={"year_assist_multiplier":1.10,"venue_profiles":{"B":{"shrunk_relative_assist_multiplier":1.50}}}
        ident={"g":{"source_home_team":"B","location":"Neutral"}}
        out=ve.apply_environment([{"game_id":"g","pred_primary_total":4,"pred_assist_total":2}],ident,prior)[0]
        self.assertEqual(out["venue_proxy_applied"],0)
        self.assertAlmostEqual(out["h005_assist"],2.2)

    def test_venue_prior_is_relative_to_league_and_credibility_weighted(self):
        ident={}
        rows=[]
        # Two venue proxies, 24 games each, exact full credibility.
        for i in range(24):
            ident[f"a{i}"]={"source_home_team":"A","location":"Home"}; rows.append({"game_id":f"a{i}","season":2021+(i%3),"actual_assist":12,"pred_assist":10})
            ident[f"b{i}"]={"source_home_team":"B","location":"Home"}; rows.append({"game_id":f"b{i}","season":2021+(i%3),"actual_assist":8,"pred_assist":10})
        p=ve.build_environment_prior(rows,ident)
        self.assertAlmostEqual(p["development_global_assist_ratio"],1.0)
        self.assertAlmostEqual(p["venue_profiles"]["A"]["shrunk_relative_assist_multiplier"],1.2)
        self.assertAlmostEqual(p["venue_profiles"]["B"]["shrunk_relative_assist_multiplier"],0.8)

    def test_game_aggregation(self):
        rows=[
          {"game_id":"g","season":2024,"week":1,"actual_primary_total":2,"actual_assist_total":1,"pred_primary_total":1.8,"pred_assist_total":.9,"actual_xtc":3,"h004_xtc":2.7},
          {"game_id":"g","season":2024,"week":1,"actual_primary_total":1,"actual_assist_total":2,"pred_primary_total":1.1,"pred_assist_total":1.7,"actual_xtc":3,"h004_xtc":2.8},
        ]
        g=ve.aggregate_game_credit_predictions(rows)[0]
        self.assertEqual(g["actual_assist"],3.0);self.assertAlmostEqual(g["pred_assist"],2.6);self.assertEqual(g["actual_xtc"],6.0)

if __name__=="__main__":unittest.main()

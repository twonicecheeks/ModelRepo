import importlib.util, pathlib, unittest

MOD=pathlib.Path(__file__).resolve().parents[4]/"packages/models/nfl/omega/residual_persistence.py"
spec=importlib.util.spec_from_file_location("residual_persistence",MOD); rp=importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)

class TestResidualPersistence(unittest.TestCase):
    def test_gamma_zero_collapses_exactly_to_h008(self):
        rows=[{"topology_xtc":5.25,"h007_prior_residual_games":8,"h007_prior_residual_mean":1.2}]
        out=rp.apply_residual_correction(rows,alpha_games=4,gamma=0)[0]
        self.assertEqual(out["h007_xtc"],5.25)
        self.assertEqual(out["h007_correction"],0.0)

    def test_positive_history_increases_prediction(self):
        rows=[{"topology_xtc":4.0,"h007_prior_residual_games":4,"h007_prior_residual_mean":1.0}]
        out=rp.apply_residual_correction(rows,alpha_games=4,gamma=1)[0]
        self.assertAlmostEqual(out["h007_history_weight"],0.5)
        self.assertAlmostEqual(out["h007_xtc"],4.5)

    def test_negative_correction_is_floored_at_zero(self):
        rows=[{"topology_xtc":0.2,"h007_prior_residual_games":8,"h007_prior_residual_mean":-3.0}]
        out=rp.apply_residual_correction(rows,alpha_games=2,gamma=1)[0]
        self.assertEqual(out["h007_xtc"],0.0)

    def test_same_week_residual_does_not_leak(self):
        rows=[
          {"season":2021,"week":1,"game_id":"g1","player_id":"p","actual_xtc":8,"topology_xtc":4},
          {"season":2021,"week":1,"game_id":"g1b","player_id":"p","actual_xtc":1,"topology_xtc":4},
          {"season":2021,"week":2,"game_id":"g2","player_id":"p","actual_xtc":5,"topology_xtc":4},
        ]
        out=rp.build_strictly_lagged_residual_rows(rows)
        wk1=[r for r in out if r["week"]==1]
        self.assertTrue(all(r["h007_prior_residual_games"]==0 for r in wk1))
        wk2=[r for r in out if r["week"]==2][0]
        self.assertEqual(wk2["h007_prior_residual_games"],2)
        self.assertAlmostEqual(wk2["h007_prior_residual_mean"],0.5)

    def test_2025_rejected(self):
        with self.assertRaises(ValueError):
            rp.build_strictly_lagged_residual_rows([{"season":2025,"week":1,"player_id":"p","actual_xtc":1,"topology_xtc":1}])

if __name__=="__main__":unittest.main()

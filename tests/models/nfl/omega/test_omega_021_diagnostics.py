import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve()
SCRIPT = HERE.parents[4] / "scripts" / "nfl" / "build_omega_tackle_021_diagnostics.py"
spec = importlib.util.spec_from_file_location("omega021", SCRIPT)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class TestDiagnostics(unittest.TestCase):
    def test_compare_positive_improvement(self):
        rows=[{"a":1,"m":1.1,"b":2},{"a":3,"m":2.9,"b":1}]
        z=m.compare(rows,"a","m","b")
        self.assertGreater(z["maeImprovement"],0)
    def test_history_bands(self):
        self.assertEqual(m.history_band(0),"0_COLD")
        self.assertEqual(m.history_band(1),"1_PRIOR_GAME")
        self.assertEqual(m.history_band(3),"2-4_PRIOR_GAMES")
        self.assertEqual(m.history_band(7),"5-8_PRIOR_GAMES")
        self.assertEqual(m.history_band(9),"9+_PRIOR_GAMES")
    def test_bootstrap_cluster(self):
        rows=[]
        for g in range(8):
            rows.append({"game_id":str(g),"a":5,"m":5.1,"b":6})
            rows.append({"game_id":str(g),"a":2,"m":2.1,"b":3})
        z=m.cluster_bootstrap(rows,actual="a",model="m",bench="b",reps=200,seed=7)
        self.assertGreater(z["maeImprovementPoint"],0)
        self.assertGreater(z["maeProbabilityPositive"],.99)
    def test_calibration(self):
        rows=[{"p":1,"a":1},{"p":2,"a":2},{"p":3,"a":3},{"p":4,"a":4}]
        z=m.calibration_ols(rows,"p","a")
        self.assertAlmostEqual(z["slope"],1.0,places=8)
        self.assertAlmostEqual(z["intercept"],0.0,places=8)

if __name__ == '__main__': unittest.main()

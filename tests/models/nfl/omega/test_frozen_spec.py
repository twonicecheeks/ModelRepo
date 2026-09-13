import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve()
MODULE = HERE.parents[4] / "packages" / "models" / "nfl" / "omega" / "frozen_spec.py"
spec = importlib.util.spec_from_file_location("omega_frozen_spec", MODULE)
fs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fs)


class FrozenSpecTests(unittest.TestCase):
    def test_frozen_constants(self):
        self.assertEqual(fs.HOLDOUT_SEASON, 2025)
        self.assertEqual(fs.GLOBAL_FIT_SEASONS, tuple(range(2017, 2025)))
        self.assertEqual(fs.XDEFENSIVE_SNAPS_L2, 0.1)
        self.assertEqual(fs.XTO_L2, 0.3)
        self.assertEqual(fs.EXPOSURE_L2, 0.01)
        self.assertEqual(fs.FAMILY_ALPHA, 50.0)
        self.assertEqual(fs.TEAM_WINDOW_GAMES, 8)
        self.assertEqual(fs.PLAYER_FAMILY_RATE_WINDOW_GAMES, 8)
        self.assertEqual(len(fs.FAMILIES), 5)

    def test_strong_pass(self):
        self.assertEqual(fs.verdict(1.8, 1.6, 2.4, 2.2, 0.01, 0.01), "STRONG_PASS")

    def test_directional_pass(self):
        self.assertEqual(fs.verdict(1.8, 1.6, 2.4, 2.2, -0.01, 0.01), "DIRECTIONAL_PASS")

    def test_fail_both(self):
        self.assertEqual(fs.verdict(1.6, 1.8, 2.2, 2.4, -0.1, -0.1), "FAIL_BOTH")

    def test_mixed(self):
        self.assertEqual(fs.verdict(1.8, 1.6, 2.2, 2.4, 0.01, -0.01), "MIXED")


if __name__ == "__main__":
    unittest.main()

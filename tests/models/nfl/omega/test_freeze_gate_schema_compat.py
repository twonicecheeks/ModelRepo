import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[4]
SCRIPT = ROOT / "scripts" / "nfl" / "freeze_omega_tackle_011.py"
spec = importlib.util.spec_from_file_location("omega_freeze_gate", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FreezeGateSchemaCompatibilityTests(unittest.TestCase):
    def test_omega_02_historical_xsnap_key_is_accepted(self):
        selection = {"xSnapL2": 0.1, "xTOL2": 0.3}
        self.assertEqual(
            mod.require_float_alias(
                selection,
                ("xSnapL2", "xDefensiveSnapsL2"),
                "baseline xDefensiveSnaps L2",
            ),
            0.1,
        )

    def test_descriptive_alias_is_accepted(self):
        selection = {"xDefensiveSnapsL2": "0.1"}
        self.assertEqual(
            mod.require_float_alias(
                selection,
                ("xSnapL2", "xDefensiveSnapsL2"),
                "baseline xDefensiveSnaps L2",
            ),
            0.1,
        )

    def test_missing_field_fails_closed_with_schema_message(self):
        with self.assertRaises(SystemExit) as cm:
            mod.require_float_alias({}, ("xSnapL2", "xDefensiveSnapsL2"), "baseline xDefensiveSnaps L2")
        self.assertIn("expected one of", str(cm.exception))
        self.assertIn("xSnapL2", str(cm.exception))

    def test_non_numeric_field_fails_closed(self):
        with self.assertRaises(SystemExit) as cm:
            mod.require_float_alias({"xSnapL2": None}, ("xSnapL2",), "baseline xDefensiveSnaps L2")
        self.assertIn("missing", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

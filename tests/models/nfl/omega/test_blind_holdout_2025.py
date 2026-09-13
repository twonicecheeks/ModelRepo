import unittest
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/"packages/models/nfl/omega"))
import blind_holdout_2025 as bh

class TestBlindHoldout(unittest.TestCase):
    def test_pinned_freeze_hash(self):
        self.assertEqual(bh.FROZEN_SPEC_SHA256,"c2ca80b6a144c3aa86bc41bdb82f6f5618ffa279a38f4c6d358025ed7fbd69fb")
    def test_blind_schema_accepts_predictions(self):
        bh.assert_blind_schema(["game_id","player_id","predicted_xtc","benchmark_last4_xtc","predicted_snap_share"])
    def test_blind_schema_rejects_target(self):
        with self.assertRaises(ValueError): bh.assert_blind_schema(["game_id","actual_xtc","predicted_xtc"])
    def test_blind_schema_rejects_snap_outcome(self):
        with self.assertRaises(ValueError): bh.assert_blind_schema(["defense_snaps","predicted_xtc"])

if __name__=="__main__": unittest.main()

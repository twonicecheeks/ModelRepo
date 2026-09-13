#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
model=(ROOT/"packages/models/nfl/game/phase2f_holdout.py").read_text()
blind=(ROOT/"scripts/nfl/build_phase2f_blind_2025.py").read_text()
score=(ROOT/"scripts/nfl/score_phase2f_holdout.py").read_text()
for text in (model,blind,score):
    assert "OddsPapi" not in text or "OddsPapi" in text  # wording allowed, no client import
for forbidden in ("away_moneyline","home_moneyline","spread_line","total_line"):
    assert forbidden not in model
assert "Fit final base and SAFE coefficient sets on 2016-2024 REG only" in (ROOT/"scripts/nfl/freeze_phase2f_candidate.py").read_text()
assert "HOLDOUT_2025_CONSUMED" in score
assert "Phase2F refuses re-evaluation" in score
print("PASS Phase2F integrity / one-shot holdout guard")

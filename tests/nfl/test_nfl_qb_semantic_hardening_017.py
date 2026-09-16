#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
import qb_semantic_hardening_017 as q

assert q.assert_development_only([2016, 2024]) == (2016, 2024)
try:
    q.assert_development_only([2025])
except ValueError:
    pass
else:
    raise AssertionError("2025 must remain sealed")

assert q.replay_review_evidence({"desc":"The Replay Official reviewed the ruling"})
assert q.replay_review_evidence({"desc":"Dallas challenged the runner was down ruling"})
assert not q.replay_review_evidence({"desc":"ordinary pass play"})

f = q.fumble_evidence({"fumble":1,"desc":"receiver FUMBLES"})
assert f["any"] and f["fumble_flag"] and f["description_fumble"]
assert q.classify_nonlateral_residual({"lateral_reception":0,"fumble":1}) == "FUMBLE_SEQUENCE"
assert q.classify_nonlateral_residual({"lateral_reception":1,"fumble":0}) == "LATERAL_RECEPTION"
assert q.classify_nonlateral_residual({"lateral_reception":0,"fumble":0,"desc":"ordinary completion"}) == "UNEXPLAINED_NONFUMBLE"

assert q.disposition(other_dropbacks=0, conflict_rows=5, nonreview_conflicts=0, unexplained_nonfumble=0) == "SEMANTICS_HARDENED_WITH_RARE_EVENT_QUARANTINE"
assert q.model_fit_authorized("SEMANTICS_HARDENED_WITH_RARE_EVENT_QUARANTINE")
assert not q.model_fit_authorized("PASSING_RESIDUAL_REQUIRES_REVIEW")

print("PASS NFL QB State 0.1.7 semantic hardening contracts · 2025 sealed")

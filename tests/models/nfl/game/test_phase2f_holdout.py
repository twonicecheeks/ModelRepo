#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/"packages/models/nfl/game"))
import phase2f_holdout as p
assert p.SAFE_VARIANT=="safe_no_last4_no_turnover_no_rush_epa"
assert p.SAFE_L2==0.3 and p.BASE_L2==0.3
assert p.STAGE_WEIGHTS=={"week1":0.0,"weeks2to4":1.0,"week5plus":0.75}
assert p.season_stage(1)=="week1" and p.season_stage(4)=="weeks2to4" and p.season_stage(5)=="week5plus"
assert p.blend_probability(.4,.8,1)==.4
assert p.blend_probability(.4,.8,2)==.8
assert abs(p.blend_probability(.4,.8,7)-.7)<1e-12
for n in ("last4_off_success_rate_diff","missing__last4_lag_qb_epa_diff","std_off_turnover_rate_diff","prior_season_def_takeaway_rate_diff","last8_lag_qb_int_rate_diff","std_off_rush_epa_diff","prior_season_def_rush_epa_allowed_diff"):
    assert not p.selected_feature_keep(n), n
assert p.selected_feature_keep("last8_off_success_rate_diff")
assert p.verdict(.23,.22,.65,.64,.001,.002)=="STRONG_PASS"
assert p.verdict(.23,.22,.65,.64,-.001,.002)=="DIRECTIONAL_PASS"
assert p.verdict(.22,.23,.64,.65)=="FAIL_BOTH"
assert p.verdict(.23,.22,.64,.65)=="MIXED"
print("PASS Phase2F frozen constants / features / verdict policy")

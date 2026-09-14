#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'packages/models/nfl/omega'))
import current_role_snap_distribution_challenger as cr


def base(**kw):
    r={"season":2024,"week":1,"team":"DAL","position_group":"LB","prior_games":0,
       "last4_snap_share_std":0.0,"depth_present":1,"depth_rank":1,"depth_position":"ILB",
       "prev_depth_rank":2,"prev_depth_team":"DAL","prev_depth_present":1,"promoted_to_rank1":1,
       "demoted_from_rank1":0,"rank_improvement":1,"rank_demotion":0}
    r.update(kw); return r


def main():
    f=cr.role_features(base(),.25)
    assert f["rank1"]==1 and f["rank1_LB"]==1 and f["starter_gap"]==.75
    assert f["promoted_to_rank1"]==1 and f["rank1_cold_start"]==1
    assert cr.depth_position_band("RCB")=="CB"
    assert cr.depth_position_band("FS")=="S"
    assert cr.depth_position_band("RDE")=="EDGE"
    assert cr.depth_band(1)=="R1" and cr.depth_band(3)=="R3PLUS" and cr.depth_band(0)=="MISSING"
    assert cr.transition_band(base())=="PROMOTE_R1"

    # Missing depth state must be an exact H012 fallback regardless of learned coefficients.
    m=cr.RoleCorrectionModel([0.0]*len(cr.FEATURE_NAMES),[1.0]*len(cr.FEATURE_NAMES),.5,[1.0]*len(cr.FEATURE_NAMES),.1)
    missing=base(depth_present=0,depth_rank=0)
    assert abs(m.predict(missing,.42)-.42)<1e-12

    # A tiny synthetic fit should remain bounded and executable.
    rows=[]
    for i in range(120):
        r=base(week=2+(i%10),prior_games=4,depth_rank=1 if i%2==0 else 2,
               prev_depth_rank=2 if i%2==0 else 1,promoted_to_rank1=1 if i%2==0 else 0,
               demoted_from_rank1=0 if i%2==0 else 1)
        r["h012_center"]=.45 if i%2==0 else .80
        r["actual_snap_share"]=.85 if i%2==0 else .45
        rows.append(r)
    fitted=cr.fit_correction(rows,.3)
    assert 0<=fitted.predict(rows[0],rows[0]["h012_center"])<=1
    assert 0<=fitted.predict(rows[1],rows[1]["h012_center"])<=1
    print("PASS OMEGA 0.2.7 current-role snap distribution tests · 10")
    return 0

if __name__=="__main__": raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import math
from pathlib import Path

HERE=Path(__file__).resolve()
SCRIPT=HERE.parents[2]/"scripts/nfl/score_omega_tackle_013_holdout.py"
spec=importlib.util.spec_from_file_location("omega013",SCRIPT)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def row(g,a,p,b,pg="LB",prior=9):
    return {"game_id":g,"actual_xtc":a,"predicted_xtc":p,"benchmark_last4_xtc":b,"position_group":pg,"prior_games":prior}

# Metric direction: positive improvement means OMEGA is better.
r=[row("g1",5,5,3),row("g2",1,1,4)]
c=m.compare(r)
assert c["model"]["mae"] == 0
assert c["maeImprovement"] > 0
assert c["rmseImprovement"] > 0

# Frozen verdict semantics.
boot={"maeImprovementCI95":[0.01,0.2],"rmseImprovementCI95":[0.01,0.2]}
assert m.precommitted_verdict({"maeImprovement":0.1,"rmseImprovement":0.2},boot)=="STRONG_PASS"
boot2={"maeImprovementCI95":[-0.01,0.2],"rmseImprovementCI95":[0.01,0.2]}
assert m.precommitted_verdict({"maeImprovement":0.1,"rmseImprovement":0.2},boot2)=="DIRECTIONAL_PASS"
assert m.precommitted_verdict({"maeImprovement":-0.1,"rmseImprovement":-0.2},boot)=="FAIL_BOTH"
assert m.precommitted_verdict({"maeImprovement":0.1,"rmseImprovement":-0.2},boot)=="MIXED"

# Fixed history bands from OMEGA 0.2.1 diagnostics.
assert [m.history_band(x) for x in (0,1,2,4,5,8,9,50)] == [
    "0_COLD","1_PRIOR_GAME","2-4_PRIOR_GAMES","2-4_PRIOR_GAMES",
    "5-8_PRIOR_GAMES","5-8_PRIOR_GAMES","9+_PRIOR_GAMES","9+_PRIOR_GAMES"
]

# Calibration recovers y = 1 + 2x.
rr=[row(f"g{i}",1+2*i,i,i) for i in range(1,6)]
cal=m.calibration_ols(rr,"predicted_xtc")
assert abs(cal["intercept"]-1)<1e-12
assert abs(cal["slope"]-2)<1e-12
assert abs(cal["r2"]-1)<1e-12

# Deterministic percentile interpolation.
assert abs(m.percentile([0,10],.25)-2.5)<1e-12

print("PASS omega 0.13 scoring unit tests")

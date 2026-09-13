#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve()
SCRIPT=HERE.parents[2]/"scripts/nfl/resume_omega_tackle_0131_holdout.py"
spec=importlib.util.spec_from_file_location("omega0131",SCRIPT)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ctx={"blindAudit":{"source":{"2025ExposureAudit":{
    "snapDefensiveExposureRows":10539,
    "resolvedSnapDefensiveExposureRows":10524,
    "unresolvedSnapDefensiveExposureRows":15,
    "fitEligibleRows":10524,
    "zeroStandardCreditSnapRows":1875,
}}}}
a=m.resolved_zero_reconciliation(ctx,1860)
assert a["expectedResolvedLedgerZeroCreditRows"]==1860
try:
    m.resolved_zero_reconciliation(ctx,1859)
except SystemExit:
    pass
else:
    raise AssertionError("scope guard did not fail closed")
boot={"maeImprovementCI95":[0.01,0.2],"rmseImprovementCI95":[0.01,0.2]}
assert m.precommitted_verdict({"maeImprovement":0.1,"rmseImprovement":0.2},boot)=="STRONG_PASS"
assert m.BOOTSTRAP_REPS==10000 and m.BOOTSTRAP_SEED==290013
print("PASS omega 0.13.1 controlled-resume hotfix tests")

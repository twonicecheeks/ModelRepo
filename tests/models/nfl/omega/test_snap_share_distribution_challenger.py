#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import math, sys

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/"packages/models/nfl/omega"))
import snap_share_distribution_challenger as sd


def obs(i, pg, prior, center, actual):
    return sd.ResidualObservation(
        game_id=f"2023_01_A_B_{i}", season=2023, week=1, player_id=f"p{i}",
        position_group=pg, prior_games=prior, center=center, actual=actual,
        residual=actual-center,
    )


def test_role_tiers():
    assert sd.role_tier(.349)=="LOW"
    assert sd.role_tier(.35)=="ROTATIONAL"
    assert sd.role_tier(.65)=="STARTER"
    assert sd.role_tier(.85)=="EVERY_DOWN"


def test_crps_degenerate_equals_absolute_error():
    assert abs(sd.empirical_crps([.6],.8)-.2)<1e-12
    assert abs(sd.empirical_crps([.6,.6,.6],.8)-.2)<1e-12


def test_empirical_distribution_bounded_and_probabilities_sum():
    xs=[]
    for i in range(120):
        actual=max(0,min(1,.9 + ((i%9)-4)*.03))
        xs.append(obs(i,"DB",12,.90,actual))
    cal=sd.EmpiricalResidualCalibrator(xs,min_pool=80)
    row={"position_group":"DB","prior_games":20}
    d=cal.summarize(row,.97,.95)
    assert 0 <= d["q05"] <= d["q95"] <= 1
    assert 0 <= d["distribution_mean"] <= 1
    assert abs(d["p_low"]+d["p_rotational"]+d["p_starter"]+d["p_every_down"]-1)<1e-12
    assert d["pool_n"]>=80
    assert 0 <= d["crps"] <= 1
    assert 0 <= d["pit"] <= 1


def test_hierarchical_fallback_is_deterministic():
    xs=[]
    for i in range(100):
        xs.append(obs(i,"LB",10,.72,.70 + (i%5)*.01))
    cal=sd.EmpiricalResidualCalibrator(xs,min_pool=80)
    # DB has no specific pool; role pool is sufficiently populated and must be used
    row={"position_group":"DB","prior_games":0}
    key,samples=cal.samples(row,.72)
    assert key[0] in {"R","GLOBAL"}
    assert len(samples)==100


def test_context_uses_only_pregame_state_fields():
    row={"position_group":"LB","prior_games":0,"actual_snap_share":.99,"future_secret":123}
    keys=sd.context_candidates(row,.42)
    flat={x for k in keys for x in k}
    assert "LB" in flat and "COLD_0" in flat and "ROTATIONAL" in flat
    assert ".99" not in flat and "123" not in flat


def main():
    tests=[v for k,v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests: t()
    print(f"PASS OMEGA 0.2.3 snap-share distribution tests · {len(tests)}")
    return 0


if __name__=="__main__": raise SystemExit(main())

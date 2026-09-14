"""OMEGA 0.2.7 current-role snap-share distribution challenger.

Research-only layer beside frozen OMEGA.  H012 remains the historical-usage
anchor.  This module learns a leakage-safe correction from current pregame depth
rank / role transitions and a role-conditioned empirical residual distribution.
Availability/no-play probability remains separate.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt
from statistics import fmean
from typing import Any, Iterable, Sequence

import snap_share_distribution_challenger as sd

VERSION = "0.2.7"
LINEAGE = "omega-tackle-v0.2.7-current-role-snap-distribution-challenger-2026-09-14"
L2_GRID = (0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
MIN_POOL = 60

FEATURE_NAMES = (
    "h012_center",
    "h012_center_sq",
    "depth_rank",
    "depth_rank_inv",
    "rank1",
    "rank2",
    "rank3plus",
    "prev_depth_present",
    "prev_rank1",
    "prev_rank2",
    "prev_rank3plus",
    "rank_improvement",
    "rank_demotion",
    "promoted_to_rank1",
    "demoted_from_rank1",
    "team_changed",
    "week1",
    "cold_start",
    "one_prior_game",
    "last4_snap_share_std",
    "rank1_week1",
    "rank1_cold_start",
    "rank1_DB",
    "rank1_LB",
    "rank1_DL",
    "rank2_DB",
    "rank2_LB",
    "rank2_DL",
    "rank3plus_DB",
    "rank3plus_LB",
    "rank3plus_DL",
    "rank1_x_h012",
    "rank2plus_x_h012",
    "starter_gap",
    "backup_gap",
    "depth_pos_CB",
    "depth_pos_S",
    "depth_pos_ILB",
    "depth_pos_EDGE",
    "depth_pos_IDL",
    "depth_pos_OTHER",
)


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def depth_position_band(value: Any) -> str:
    p = str(value or "").strip().upper().replace(" ", "")
    if p in {"CB", "LCB", "RCB", "NB", "NCB", "SCB"} or "CORNER" in p:
        return "CB"
    if p in {"S", "FS", "SS", "SAF", "LS", "RS"} or "SAF" in p:
        return "S"
    if p in {"ILB", "MLB", "LILB", "RILB", "MIB"}:
        return "ILB"
    if p in {"OLB", "LOLB", "ROLB", "DE", "LDE", "RDE", "EDGE", "ED"}:
        return "EDGE"
    if p in {"DT", "LDT", "RDT", "NT", "DL", "IDL"}:
        return "IDL"
    return "OTHER"


def depth_band(rank: int | float | None) -> str:
    try:
        r = int(float(rank or 0))
    except (TypeError, ValueError):
        r = 0
    if r == 1:
        return "R1"
    if r == 2:
        return "R2"
    if r >= 3:
        return "R3PLUS"
    return "MISSING"


def transition_band(row: dict[str, Any]) -> str:
    if not int(float(row.get("prev_depth_present") or 0)):
        return "NO_PREV"
    if int(float(row.get("promoted_to_rank1") or 0)):
        return "PROMOTE_R1"
    if int(float(row.get("demoted_from_rank1") or 0)):
        return "DEMOTE_R1"
    if float(row.get("rank_improvement") or 0) > 0 or float(row.get("rank_demotion") or 0) > 0:
        return "RANK_CHANGED"
    if int(float(row.get("team_changed") or 0)):
        return "TEAM_CHANGED"
    return "STABLE"


def role_features(row: dict[str, Any], h012_center: float) -> dict[str, float]:
    """Build pregame-only role correction features.

    When current depth state is absent the caller should use exact H012 fallback;
    these zeros are still returned for diagnostics.
    """
    c = clip01(h012_center)
    try:
        rank = max(0, int(float(row.get("depth_rank") or 0)))
    except (TypeError, ValueError):
        rank = 0
    try:
        prev = max(0, int(float(row.get("prev_depth_rank") or 0)))
    except (TypeError, ValueError):
        prev = 0
    present = 1.0 if rank > 0 else 0.0
    prev_present = 1.0 if prev > 0 else 0.0
    r1 = 1.0 if rank == 1 else 0.0
    r2 = 1.0 if rank == 2 else 0.0
    r3 = 1.0 if rank >= 3 else 0.0
    p1 = 1.0 if prev == 1 else 0.0
    p2 = 1.0 if prev == 2 else 0.0
    p3 = 1.0 if prev >= 3 else 0.0
    improve = float(max(0, prev-rank)) if present and prev_present else 0.0
    demote = float(max(0, rank-prev)) if present and prev_present else 0.0
    promoted = 1.0 if rank == 1 and prev >= 2 else 0.0
    demoted = 1.0 if prev == 1 and rank >= 2 else 0.0
    pg = str(row.get("position_group") or "").upper()
    week1 = 1.0 if int(float(row.get("week") or 0)) == 1 else 0.0
    cold = 1.0 if int(float(row.get("prior_games") or 0)) == 0 else 0.0
    one = 1.0 if int(float(row.get("prior_games") or 0)) == 1 else 0.0
    team_changed = 1.0 if str(row.get("prev_depth_team") or "") and str(row.get("prev_depth_team") or "") != str(row.get("team") or "") else 0.0
    pb = depth_position_band(row.get("depth_position"))
    out = {
        "h012_center": c,
        "h012_center_sq": c*c,
        "depth_rank": float(min(rank, 5)) if present else 0.0,
        "depth_rank_inv": (1.0/rank) if present else 0.0,
        "rank1": r1, "rank2": r2, "rank3plus": r3,
        "prev_depth_present": prev_present,
        "prev_rank1": p1, "prev_rank2": p2, "prev_rank3plus": p3,
        "rank_improvement": min(3.0, improve),
        "rank_demotion": min(3.0, demote),
        "promoted_to_rank1": promoted,
        "demoted_from_rank1": demoted,
        "team_changed": team_changed,
        "week1": week1,
        "cold_start": cold,
        "one_prior_game": one,
        "last4_snap_share_std": float(row.get("last4_snap_share_std") or 0.0),
        "rank1_week1": r1*week1,
        "rank1_cold_start": r1*cold,
        "rank1_DB": r1*(1.0 if pg == "DB" else 0.0),
        "rank1_LB": r1*(1.0 if pg == "LB" else 0.0),
        "rank1_DL": r1*(1.0 if pg == "DL" else 0.0),
        "rank2_DB": r2*(1.0 if pg == "DB" else 0.0),
        "rank2_LB": r2*(1.0 if pg == "LB" else 0.0),
        "rank2_DL": r2*(1.0 if pg == "DL" else 0.0),
        "rank3plus_DB": r3*(1.0 if pg == "DB" else 0.0),
        "rank3plus_LB": r3*(1.0 if pg == "LB" else 0.0),
        "rank3plus_DL": r3*(1.0 if pg == "DL" else 0.0),
        "rank1_x_h012": r1*c,
        "rank2plus_x_h012": (r2+r3)*c,
        "starter_gap": r1*(1.0-c),
        "backup_gap": (r2+r3)*c,
    }
    for b in ("CB","S","ILB","EDGE","IDL","OTHER"):
        out[f"depth_pos_{b}"] = present*(1.0 if pb == b else 0.0)
    return out


def _solve_linear(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    aug = [list(map(float,row)) + [float(rhs)] for row,rhs in zip(a,b)]
    for col in range(n):
        pivot = max(range(col,n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("singular linear system")
        if pivot != col:
            aug[col],aug[pivot] = aug[pivot],aug[col]
        p = aug[col][col]
        aug[col] = [x/p for x in aug[col]]
        for r in range(n):
            if r == col: continue
            f = aug[r][col]
            if abs(f) < 1e-18: continue
            aug[r] = [x-f*y for x,y in zip(aug[r],aug[col])]
    return [aug[i][-1] for i in range(n)]


@dataclass
class RoleCorrectionModel:
    means: list[float]
    scales: list[float]
    intercept: float
    coefficients: list[float]
    l2: float

    def correction(self, row: dict[str, Any], h012_center: float) -> float:
        if int(float(row.get("depth_present") or 0)) == 0:
            return 0.0
        f = role_features(row,h012_center)
        z = self.intercept
        for i,name in enumerate(FEATURE_NAMES):
            z += self.coefficients[i]*((f[name]-self.means[i])/self.scales[i])
        return max(-0.75,min(0.75,z))

    def predict(self, row: dict[str, Any], h012_center: float) -> float:
        return clip01(h012_center + self.correction(row,h012_center))

    def to_dict(self) -> dict[str, Any]:
        return {"modelClass":"H012_PLUS_STANDARDIZED_RIDGE_ROLE_RESIDUAL","version":VERSION,"lineage":LINEAGE,
                "featureNames":list(FEATURE_NAMES),"means":self.means,"scales":self.scales,
                "intercept":self.intercept,"coefficients":self.coefficients,"l2":self.l2,
                "target":"actual_snap_share_minus_chronological_h012_center","missingDepthFallback":"EXACT_H012"}


def fit_correction(rows: Sequence[dict[str, Any]], l2: float) -> RoleCorrectionModel:
    rr = [r for r in rows if int(float(r.get("depth_present") or 0)) == 1]
    if not rr:
        raise ValueError("no depth-covered rows for role correction")
    xs = [[role_features(r,float(r["h012_center"]))[n] for n in FEATURE_NAMES] for r in rr]
    ys = [float(r["actual_snap_share"])-float(r["h012_center"]) for r in rr]
    p = len(FEATURE_NAMES)
    means = [fmean(x[j] for x in xs) for j in range(p)]
    scales=[]
    for j in range(p):
        var=fmean((x[j]-means[j])**2 for x in xs)
        scales.append(sqrt(var) if var>1e-12 else 1.0)
    zx=[[(x[j]-means[j])/scales[j] for j in range(p)] for x in xs]
    ybar=fmean(ys); yc=[y-ybar for y in ys]
    xtx=[[0.0]*p for _ in range(p)]; xty=[0.0]*p; n=float(len(rr))
    for x,y in zip(zx,yc):
        for j in range(p):
            xty[j]+=x[j]*y/n
            for k in range(p): xtx[j][k]+=x[j]*x[k]/n
    for j in range(p): xtx[j][j]+=float(l2)
    coefs=_solve_linear(xtx,xty)
    return RoleCorrectionModel(means,scales,ybar,coefs,float(l2))


def _context_candidates(row: dict[str, Any], center: float) -> tuple[tuple[str,...],...]:
    pg = str(row.get("position_group") or "OTHER").upper()
    if pg not in {"DB","LB","DL"}: pg="OTHER"
    hb = sd.history_band(int(float(row.get("prior_games") or 0)))
    rt = sd.role_tier(center)
    db = depth_band(row.get("depth_rank"))
    tb = transition_band(row)
    return (
        ("P_D_T_R",pg,db,tb,rt),
        ("P_D_R",pg,db,rt),
        ("D_T_R",db,tb,rt),
        ("D_R",db,rt),
        ("H_D_R",hb,db,rt),
        ("P_R",pg,rt),
        ("R",rt),
        ("GLOBAL",),
    )


@dataclass(frozen=True)
class RoleResidualObservation:
    row: dict[str, Any]
    center: float
    actual: float
    residual: float


class RoleResidualCalibrator:
    def __init__(self, observations: Iterable[RoleResidualObservation], min_pool: int=MIN_POOL):
        self.min_pool=int(min_pool); self.observations=list(observations)
        if not self.observations: raise ValueError("empty role residual calibrator")
        pools: dict[tuple[str,...],list[float]]=defaultdict(list)
        for o in self.observations:
            for key in _context_candidates(o.row,o.center): pools[key].append(float(o.residual))
        self.pools={k:tuple(v) for k,v in pools.items()}

    def select_pool(self,row:dict[str,Any],center:float):
        for key in _context_candidates(row,center)[:-1]:
            vals=self.pools.get(key,())
            if len(vals)>=self.min_pool: return key,vals
        return ("GLOBAL",),self.pools[("GLOBAL",)]

    def summarize(self,row:dict[str,Any],center:float,actual:float|None=None)->dict[str,Any]:
        key,res=self.select_pool(row,center); samples=[clip01(center+r) for r in res]; n=len(samples)
        low=sum(x<.35 for x in samples)/n; rotational=sum(.35<=x<.65 for x in samples)/n
        starter=sum(.65<=x<.85 for x in samples)/n; every=sum(x>=.85 for x in samples)/n
        out={"point_center":clip01(center),"distribution_mean":fmean(samples),"distribution_median":sd.percentile(samples,.5),
             "q05":sd.percentile(samples,.05),"q10":sd.percentile(samples,.10),"q25":sd.percentile(samples,.25),
             "q75":sd.percentile(samples,.75),"q90":sd.percentile(samples,.90),"q95":sd.percentile(samples,.95),
             "p_low":low,"p_rotational":rotational,"p_starter":starter,"p_every_down":every,
             "p_ge_035":1-low,"p_ge_065":starter+every,"p_ge_085":every,"pool_key":"|".join(key),"pool_n":n}
        if actual is not None:
            y=clip01(actual)
            out.update({"actual":y,"crps":sd.empirical_crps(samples,y),"pit":sd.mid_pit(samples,y),
                        "covered_50":int(out["q25"]<=y<=out["q75"]),"covered_80":int(out["q10"]<=y<=out["q90"]),
                        "covered_90":int(out["q05"]<=y<=out["q95"]),"width_50":out["q75"]-out["q25"],
                        "width_80":out["q90"]-out["q10"],"width_90":out["q95"]-out["q05"],
                        "brier_ge_035":(out["p_ge_035"]-int(y>=.35))**2,
                        "brier_ge_065":(out["p_ge_065"]-int(y>=.65))**2,
                        "brier_ge_085":(out["p_ge_085"]-int(y>=.85))**2})
        return out

    def pool_summary(self)->list[dict[str,Any]]:
        out=[]
        for k,v in sorted(self.pools.items()):
            out.append({"pool_key":"|".join(k),"n":len(v),"residual_mean":fmean(v),
                        "residual_q10":sd.percentile(v,.1),"residual_q50":sd.percentile(v,.5),"residual_q90":sd.percentile(v,.9)})
        return out


def make_role_observation(row:dict[str,Any],center:float)->RoleResidualObservation:
    actual=clip01(float(row["actual_snap_share"])); c=clip01(center)
    return RoleResidualObservation(dict(row),c,actual,actual-c)

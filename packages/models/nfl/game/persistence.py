"""Empirical NFL metric-persistence research for Phase 2B.

Persistence is estimated only from historical team-game observations supplied to the
function. It is an audit/research artifact in Phase 2B; no coefficient is silently
injected into production probabilities.
"""
from __future__ import annotations
from collections import defaultdict
from math import sqrt
from statistics import fmean
from typing import Any, Iterable

VERSION="0.1.0"
NOISY_METRICS={"off_turnover_rate","def_takeaway_rate"}


def _num(v:Any):
    try:
        x=float(v)
    except (TypeError,ValueError): return None
    return None if x!=x else x


def corr(xs:list[float],ys:list[float])->float|None:
    if len(xs)<20 or len(xs)!=len(ys): return None
    mx,my=fmean(xs),fmean(ys); vx=sum((x-mx)**2 for x in xs); vy=sum((y-my)**2 for y in ys)
    if vx<=1e-12 or vy<=1e-12:return None
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sqrt(vx*vy)


def lag1_persistence(rows:Iterable[dict[str,Any]], metrics:Iterable[str], *, max_season:int)->dict[str,dict[str,Any]]:
    by_team=defaultdict(list)
    for r in rows:
        try:s=int(r["season"]); w=int(r["week"])
        except Exception:continue
        if s>max_season:continue
        by_team[str(r["team"]).upper()].append((s,w,str(r["game_id"]),r))
    for v in by_team.values():v.sort()
    out={}
    for metric in metrics:
        xs=[];ys=[]
        for seq in by_team.values():
            prev=None
            for s,w,g,r in seq:
                cur=_num(r.get(metric))
                if cur is None:continue
                if prev is not None:
                    xs.append(prev);ys.append(cur)
                prev=cur
        raw=corr(xs,ys)
        rho=0.0 if raw is None else min(0.98,max(0.0,raw))
        # Turnover-like metrics are deliberately never granted more than moderate
        # persistence without evidence; this is an audit flag, not a hard model weight.
        capped=min(rho,0.45) if metric in NOISY_METRICS else rho
        out[metric]={"pairs":len(xs),"rawLag1Correlation":raw,"researchPersistence":capped,
                     "noiseGuardApplied":metric in NOISY_METRICS and capped<rho}
    return out

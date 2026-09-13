"""NFL Phase 2B challenger-model math.

All functions are historical-development only. They never read sportsbook prices and
are designed to consume pregame-only rows produced by Phase 1B.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import erf, exp, log, sqrt
from statistics import fmean
from typing import Iterable, Sequence

VERSION = "0.2.0"
LINEAGE = "nfl-game-v0.2.0-dynamic-challengers-2026-09-09"

PASSING_CORE_STEMS = (
    "off_dropback_epa", "off_cpoe", "off_sack_rate", "off_explosive_pass_rate",
    "def_dropback_epa_allowed", "def_sack_rate_generated", "def_explosive_pass_rate_allowed",
)
HORIZONS = ("prior_season", "std", "last4", "last8")


def sigmoid(z: float) -> float:
    if z >= 0:
        e = exp(-min(z, 40.0)); return 1.0/(1.0+e)
    e = exp(max(z, -40.0)); return e/(1.0+e)


def clip_prob(p: float) -> float:
    return min(1-1e-9, max(1e-9, float(p)))


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def simplex_project(v: Sequence[float]) -> list[float]:
    """Euclidean projection onto nonnegative unit simplex."""
    if not v:
        raise ValueError("empty vector")
    u = sorted((float(x) for x in v), reverse=True)
    cssv = 0.0; rho = -1
    for i, x in enumerate(u):
        cssv += x
        t = (cssv - 1.0)/(i+1)
        if x - t > 0:
            rho = i
    if rho < 0:
        return [1.0/len(v)]*len(v)
    theta = (sum(u[:rho+1])-1.0)/(rho+1)
    return [max(0.0, float(x)-theta) for x in v]


def sparse_passing_feature_names(full_names: Sequence[str]) -> tuple[str, ...]:
    keep = {"rest_days_diff", "missing__rest_days_diff", "neutral_site", "missing__neutral_site"}
    for h in HORIZONS:
        for stem in PASSING_CORE_STEMS:
            base = f"{h}_{stem}_diff"
            keep.add(base); keep.add(f"missing__{base}")
    return tuple(n for n in full_names if n in keep)


def select_columns(x: Sequence[float|None], full_names: Sequence[str], selected_names: Sequence[str]) -> tuple[float|None,...]:
    idx = {n:i for i,n in enumerate(full_names)}
    return tuple(x[idx[n]] for n in selected_names)


@dataclass
class Standardizer:
    means: list[float]
    scales: list[float]
    def transform(self, x: Sequence[float|None]) -> list[float]:
        return [((self.means[i] if v is None else float(v))-self.means[i])/self.scales[i] for i,v in enumerate(x)]


def fit_standardizer(xs: Sequence[Sequence[float|None]]) -> Standardizer:
    if not xs: raise ValueError("empty design")
    p=len(xs[0]); means=[]; scales=[]
    for j in range(p):
        good=[float(r[j]) for r in xs if r[j] is not None]
        m=fmean(good) if good else 0.0
        var=fmean((z-m)**2 for z in good) if len(good)>1 else 0.0
        means.append(m); scales.append(sqrt(var) if var>1e-12 else 1.0)
    return Standardizer(means,scales)


@dataclass
class GenericLogit:
    names: tuple[str,...]; standardizer: Standardizer; intercept: float; coefficients: list[float]; l2: float
    def predict(self, x: Sequence[float|None]) -> float:
        tx=self.standardizer.transform(x)
        return sigmoid(self.intercept + sum(a*b for a,b in zip(self.coefficients,tx)))


def fit_generic_logit(xs: Sequence[Sequence[float|None]], ys: Sequence[int], names: Sequence[str], *, l2: float, max_iter: int=180) -> GenericLogit:
    if not xs or len(xs)!=len(ys): raise ValueError("bad design")
    st=fit_standardizer(xs); X=[st.transform(x) for x in xs]; n=float(len(xs)); p=len(names)
    ybar=min(1-1e-6,max(1e-6,fmean(ys))); b=log(ybar/(1-ybar)); w=[0.0]*p
    for it in range(max_iter):
        gb=0.0; gw=[0.0]*p
        for row,y in zip(X,ys):
            e=sigmoid(b+sum(a*z for a,z in zip(w,row)))-y; gb+=e
            for j,z in enumerate(row): gw[j]+=e*z
        gb/=n
        for j in range(p): gw[j]=gw[j]/n+l2*w[j]
        step=0.12/sqrt(1+it/80)
        b-=step*gb
        for j in range(p): w[j]-=step*gw[j]
    return GenericLogit(tuple(names),st,b,w,float(l2))


@dataclass
class RidgeMargin:
    names: tuple[str,...]; standardizer: Standardizer; intercept: float; coefficients: list[float]; l2: float; residual_sigma: float
    def expected_margin(self,x:Sequence[float|None])->float:
        tx=self.standardizer.transform(x); return self.intercept+sum(a*b for a,b in zip(self.coefficients,tx))
    def win_probability(self,x:Sequence[float|None])->float:
        return clip_prob(normal_cdf(self.expected_margin(x)/max(self.residual_sigma,1e-6)))


def fit_ridge_margin(xs:Sequence[Sequence[float|None]], margins:Sequence[float], names:Sequence[str], *, l2:float, max_iter:int=220)->RidgeMargin:
    if not xs or len(xs)!=len(margins): raise ValueError("bad margin design")
    st=fit_standardizer(xs); X=[st.transform(x) for x in xs]; n=float(len(xs)); p=len(names)
    b=fmean(margins); w=[0.0]*p
    for it in range(max_iter):
        gb=0.0; gw=[0.0]*p
        for row,y in zip(X,margins):
            e=(b+sum(a*z for a,z in zip(w,row)))-float(y); gb+=e
            for j,z in enumerate(row): gw[j]+=e*z
        gb/=n
        for j in range(p): gw[j]=gw[j]/n+l2*w[j]
        step=0.02/sqrt(1+it/100)
        b-=step*gb
        for j in range(p): w[j]-=step*gw[j]
    resid=[float(y)-(b+sum(a*z for a,z in zip(w,row))) for row,y in zip(X,margins)]
    sigma=sqrt(fmean(r*r for r in resid)) if resid else 13.5
    return RidgeMargin(tuple(names),st,b,w,float(l2),max(sigma,5.0))


@dataclass
class LogitPool:
    weights:list[float]; intercept:float; l2:float
    def predict(self, probs:Sequence[float])->float:
        if len(probs)!=len(self.weights): raise ValueError("pool dimension mismatch")
        logits=[log(clip_prob(p)/(1-clip_prob(p))) for p in probs]
        return sigmoid(self.intercept+sum(w*z for w,z in zip(self.weights,logits)))


def fit_logit_pool(prob_rows:Sequence[Sequence[float]], ys:Sequence[int], *, l2:float=0.03, max_iter:int=300)->LogitPool:
    """Constrained nonnegative simplex stacker on base-model logits."""
    if not prob_rows or len(prob_rows)!=len(ys): raise ValueError("bad pool data")
    m=len(prob_rows[0]); w=[1.0/m]*m; b=0.0; n=float(len(ys))
    Z=[[log(clip_prob(p)/(1-clip_prob(p))) for p in row] for row in prob_rows]
    for it in range(max_iter):
        gb=0.0; gw=[0.0]*m
        for z,y in zip(Z,ys):
            e=sigmoid(b+sum(a*c for a,c in zip(w,z)))-y; gb+=e
            for j,c in enumerate(z): gw[j]+=e*c
        gb/=n
        for j in range(m): gw[j]=gw[j]/n+l2*(w[j]-1.0/m)
        step=0.08/sqrt(1+it/120)
        b-=step*gb
        w=simplex_project([w[j]-step*gw[j] for j in range(m)])
    return LogitPool(w,b,float(l2))


def model_disagreement(probs:Sequence[float])->float:
    if len(probs)<2:return 0.0
    m=fmean(probs); return sqrt(fmean((p-m)**2 for p in probs))

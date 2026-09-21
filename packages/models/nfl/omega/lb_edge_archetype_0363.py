"""OMEGA 0.36.3 — development-only off-ball LB vs EDGE archetype gate.

Purpose
-------
Provider position labels are not sufficiently granular for a position-specific
tackle challenger. Generic LB labels can describe true off-ball linebackers or
edge rushers. This module learns a football-role classifier from *clean* historical
labels only:

  OFFBALL_LB: explicit ILB / MLB evidence
  EDGE: explicit DE / EDGE / OLB evidence
  AMBIG_LB: generic LB without decisive evidence

The classifier uses only strictly-lagged OMEGA H008/H012 pregame features. It reads
no sportsbook fields and no target-game outcomes when applied prospectively.

Generic-LB rows must clear a fixed high-confidence threshold before they may enter
the LB residual challenger. False negatives are preferable to contaminating the
off-ball-LB shadow with edge rushers.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log1p
from statistics import fmean
from typing import Any, Iterable, Sequence
import math

VERSION="0.36.3"
LINEAGE="omega-lb-edge-archetype-v0.36.3-development-only"
FIXED_L2=1.0
GENERIC_LB_OFFBALL_THRESHOLD=0.80
MAX_ITER=40

FEATURES=(
    "control_xtc","predicted_xto","predicted_snap_share","prior_games_log",
    "pred_credit_RUSH","pred_credit_COMPLETE_PASS","pred_credit_SCRAMBLE",
    "pred_credit_SACK","pred_credit_OTHER_PASS",
    "shrunk_rate_RUSH","shrunk_rate_COMPLETE_PASS","shrunk_rate_SCRAMBLE",
    "shrunk_rate_SACK","shrunk_rate_OTHER_PASS",
    "credit_share_RUSH","credit_share_COMPLETE_PASS","credit_share_SCRAMBLE",
    "credit_share_SACK","credit_share_OTHER_PASS",
)

EDGE_TOKENS={"DE","EDGE","OLB","LDE","RDE","LE","RE","LEO","RUSH","JACK"}
OFFBALL_TOKENS={"ILB","MLB"}
INTERIOR_TOKENS={"DL","DT","NT","IDL","LDT","RDT"}
DB_TOKENS={"DB","CB","S","FS","SS","SAFETY"}


def num(v:Any,default:float=0.0)->float:
    try:
        if v in (None,""):return float(default)
        x=float(v)
        return x if math.isfinite(x) else float(default)
    except (TypeError,ValueError):
        return float(default)


def _norm(v:Any)->str:
    return str(v or "").strip().upper().replace("-","").replace("_","").replace(" ","")


def explicit_role_label(row:dict[str,Any])->str:
    """Return OFFBALL_LB, EDGE, AMBIG_LB, DL, DB, or OTHER.

    Depth evidence is considered explicit. Generic LB is never assumed off-ball.
    Generic LB/DL disagreement is treated as EDGE-like ambiguity and therefore
    kept out of the off-ball challenger.
    """
    raw=_norm(row.get("position"))
    pg=_norm(row.get("position_group"))
    depth={
        _norm(row.get("depth_position")),
        _norm(row.get("current_depth_position")),
        _norm(row.get("previous_week_depth_position")),
    }
    depth.discard("")
    evidence={x for x in {raw,pg,*depth} if x}

    if evidence & DB_TOKENS:
        return "DB"
    if evidence & EDGE_TOKENS:
        return "EDGE"
    if evidence & OFFBALL_TOKENS:
        return "OFFBALL_LB"
    if (("LB" in evidence) and bool(evidence & INTERIOR_TOKENS)):
        return "EDGE"
    if evidence & INTERIOR_TOKENS:
        return "DL"
    if "LB" in evidence:
        return "AMBIG_LB"
    return "OTHER"


def _feature_map(row:dict[str,Any])->dict[str,float]:
    control=max(0.0,num(row.get("control_xtc",row.get("topology_xtc",row.get("predicted_xtc")))))
    credits={
        f:max(0.0,num(row.get(f"pred_credit_{f}",row.get(f"control_pred_credit_{f}"))))
        for f in ("RUSH","COMPLETE_PASS","SCRAMBLE","SACK","OTHER_PASS")
    }
    total=max(1e-9,sum(credits.values()))
    return {
        "control_xtc":control,
        "predicted_xto":max(0.0,num(row.get("predicted_xto"))),
        "predicted_snap_share":max(0.0,min(1.0,num(row.get("predicted_snap_share",row.get("control_h012_snap_share"))))),
        "prior_games_log":log1p(max(0.0,num(row.get("prior_games")))),
        **{f"pred_credit_{f}":credits[f] for f in credits},
        **{f"shrunk_rate_{f}":max(0.0,num(row.get(f"shrunk_rate_{f}"))) for f in credits},
        **{f"credit_share_{f}":credits[f]/total for f in credits},
    }


def vector(row:dict[str,Any])->tuple[float,...]:
    fm=_feature_map(row)
    return tuple(float(fm[n]) for n in FEATURES)


def _sigmoid(x:float)->float:
    if x>=0:
        z=exp(-min(x,40.0));return 1.0/(1.0+z)
    z=exp(max(x,-40.0));return z/(1.0+z)


def _solve(a:list[list[float]],b:list[float])->list[float]:
    n=len(b);aug=[list(map(float,r))+[float(y)] for r,y in zip(a,b)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(aug[r][col]))
        if abs(aug[pivot][col])<1e-10:
            aug[pivot][col]+=1e-8
        if pivot!=col:aug[col],aug[pivot]=aug[pivot],aug[col]
        z=aug[col][col]
        if abs(z)<1e-14:z=1e-14
        aug[col]=[x/z for x in aug[col]]
        for r in range(n):
            if r==col:continue
            f=aug[r][col]
            if abs(f)<1e-18:continue
            aug[r]=[x-f*y for x,y in zip(aug[r],aug[col])]
    return [aug[i][-1] for i in range(n)]


@dataclass
class ArchetypeModel:
    feature_names:tuple[str,...]
    means:list[float]
    scales:list[float]
    intercept:float
    coefficients:list[float]
    l2:float=FIXED_L2
    threshold:float=GENERIC_LB_OFFBALL_THRESHOLD

    def probability_offball(self,row:dict[str,Any])->float:
        x=vector(row)
        z=self.intercept
        for i,v in enumerate(x):
            z+=self.coefficients[i]*((v-self.means[i])/self.scales[i])
        return _sigmoid(z)

    def to_dict(self)->dict[str,Any]:
        return {
            "version":VERSION,"lineage":LINEAGE,"featureNames":list(self.feature_names),
            "means":self.means,"scales":self.scales,"intercept":self.intercept,
            "coefficients":self.coefficients,"l2":self.l2,
            "genericLbOffballThreshold":self.threshold,
            "trainingLabels":{"OFFBALL_LB":1,"EDGE":0},
        }

    @classmethod
    def from_dict(cls,d:dict[str,Any])->"ArchetypeModel":
        return cls(
            feature_names=tuple(d["featureNames"]),
            means=[float(x) for x in d["means"]],
            scales=[float(x) for x in d["scales"]],
            intercept=float(d["intercept"]),
            coefficients=[float(x) for x in d["coefficients"]],
            l2=float(d.get("l2",FIXED_L2)),
            threshold=float(d.get("genericLbOffballThreshold",GENERIC_LB_OFFBALL_THRESHOLD)),
        )


def fit(rows:Sequence[dict[str,Any]],l2:float=FIXED_L2)->ArchetypeModel:
    labeled=[]
    for r in rows:
        lab=explicit_role_label(r)
        if lab=="OFFBALL_LB":labeled.append((r,1.0))
        elif lab=="EDGE":labeled.append((r,0.0))
    if len(labeled)<200:
        raise ValueError(f"insufficient clean LB/EDGE archetype rows: {len(labeled)}")
    xs=[vector(r) for r,_ in labeled];ys=[y for _,y in labeled];k=len(FEATURES)
    means=[fmean(x[j] for x in xs) for j in range(k)]
    scales=[]
    for j in range(k):
        var=fmean((x[j]-means[j])**2 for x in xs)
        scales.append(math.sqrt(var) if var>1e-12 else 1.0)
    zx=[[(x[j]-means[j])/scales[j] for j in range(k)] for x in xs]

    beta=[0.0]*(k+1)
    # Prior-balanced intercept avoids class-count imbalance dominating initialization.
    ybar=min(.999,max(.001,fmean(ys)))
    beta[0]=math.log(ybar/(1-ybar))

    for _ in range(MAX_ITER):
        grad=[0.0]*(k+1)
        h=[[0.0]*(k+1) for _ in range(k+1)]
        n=float(len(zx))
        for x,y in zip(zx,ys):
            xa=[1.0]+x
            p=_sigmoid(sum(b*v for b,v in zip(beta,xa)))
            w=max(1e-6,p*(1-p))
            d=p-y
            for j in range(k+1):
                grad[j]+=d*xa[j]/n
                for q in range(k+1):
                    h[j][q]+=w*xa[j]*xa[q]/n
        for j in range(1,k+1):
            grad[j]+=float(l2)*beta[j]
            h[j][j]+=float(l2)
        h[0][0]+=1e-8
        step=_solve(h,grad)
        beta=[b-s for b,s in zip(beta,step)]
        if max(abs(s) for s in step)<1e-7:
            break
    return ArchetypeModel(FEATURES,means,scales,beta[0],beta[1:],float(l2),GENERIC_LB_OFFBALL_THRESHOLD)


def classify(row:dict[str,Any],model:ArchetypeModel)->dict[str,Any]:
    lab=explicit_role_label(row)
    if lab=="OFFBALL_LB":
        return {"role":"OFFBALL_LB","offballProbability":1.0,"eligibleForLbChallenger":True,"reason":"EXPLICIT_ILB_MLB"}
    if lab=="EDGE":
        return {"role":"EDGE","offballProbability":0.0,"eligibleForLbChallenger":False,"reason":"EXPLICIT_EDGE_OR_CONFLICT"}
    if lab=="DL":
        return {"role":"DL","offballProbability":0.0,"eligibleForLbChallenger":False,"reason":"INTERIOR_DL"}
    if lab=="DB":
        return {"role":"DB","offballProbability":0.0,"eligibleForLbChallenger":False,"reason":"DEFENSIVE_BACK"}
    if lab=="AMBIG_LB":
        p=model.probability_offball(row)
        ok=p>=model.threshold
        return {
            "role":"OFFBALL_LB" if ok else "EDGE_OR_AMBIG_LB",
            "offballProbability":p,"eligibleForLbChallenger":ok,
            "reason":"GENERIC_LB_ARCHETYPE_HIGH_CONFIDENCE" if ok else "GENERIC_LB_ARCHETYPE_NOT_HIGH_CONFIDENCE",
        }
    return {"role":"OTHER","offballProbability":None,"eligibleForLbChallenger":False,"reason":"UNSUPPORTED_ROLE"}


def metrics(rows:Sequence[dict[str,Any]],model:ArchetypeModel)->dict[str,Any]:
    z=[]
    for r in rows:
        lab=explicit_role_label(r)
        if lab not in {"OFFBALL_LB","EDGE"}:continue
        y=1 if lab=="OFFBALL_LB" else 0
        p=model.probability_offball(r)
        z.append((p,y))
    if not z:return {"n":0}
    brier=fmean((p-y)**2 for p,y in z)
    logloss=fmean(-(y*math.log(max(1e-12,p))+(1-y)*math.log(max(1e-12,1-p))) for p,y in z)
    acc=fmean(1.0 if (p>=.5)==bool(y) else 0.0 for p,y in z)
    hi=[(p,y) for p,y in z if p>=GENERIC_LB_OFFBALL_THRESHOLD or p<=1-GENERIC_LB_OFFBALL_THRESHOLD]
    hiacc=fmean(1.0 if (p>=.5)==bool(y) else 0.0 for p,y in hi) if hi else None
    return {"n":len(z),"brier":brier,"logLoss":logloss,"accuracy":acc,
            "highConfidenceN":len(hi),"highConfidenceAccuracy":hiacc}


if __name__=="__main__":
    print(f"OMEGA {VERSION} · {LINEAGE}")

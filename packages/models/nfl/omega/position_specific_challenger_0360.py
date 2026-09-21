"""OMEGA 0.36.0 — position-specific tackle-allocation challenger.

Development-only shadow layer around frozen H008/H012 expected tackle credits.

DET@BUF + cumulative 2026 diagnostics motivated a narrow hypothesis:
- DL control is already well centered; preserve it as the no-change reference.
- LB error may depend on RUSH/SCRAMBLE/SACK opportunity composition.
- DB error may depend on COMPLETE_PASS/OTHER_PASS versus RUSH opportunity mix.

The challenger predicts a residual around control xTC using only pregame quantities
already produced by OMEGA's strictly-lagged H008/H012 machinery. No target-game
snaps, outcomes, markets, sportsbook prices, 2025 holdout rows, or 2026 rows enter
development fitting.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log1p, sqrt
from statistics import fmean
from typing import Any, Iterable, Sequence
import random

VERSION="0.36.0"
LINEAGE="omega-position-specific-residual-v0.36.0-det-buf-2026-09-17"
HOLDOUT_SEASON=2025
PROSPECTIVE_SEASON=2026
FIXED_L2=1.0
MAX_ABS_CORRECTION=2.5
POSITIONS=("DL","EDGE","LB","DB")

LB_FEATURES=(
    "control_xtc","predicted_xto","predicted_snap_share","prior_games_log",
    "pred_credit_RUSH","pred_credit_SCRAMBLE","pred_credit_COMPLETE_PASS","pred_credit_SACK",
    "pred_share_RUSH","pred_share_SCRAMBLE","pred_share_COMPLETE_PASS","pred_share_SACK",
    "shrunk_rate_RUSH","shrunk_rate_SCRAMBLE","shrunk_rate_COMPLETE_PASS",
    "rush_x_scramble_share","mobile_family_credit_share",
)
DB_FEATURES=(
    "control_xtc","predicted_xto","predicted_snap_share","prior_games_log",
    "pred_credit_COMPLETE_PASS","pred_credit_OTHER_PASS","pred_credit_RUSH",
    "pred_share_COMPLETE_PASS","pred_share_OTHER_PASS","pred_share_RUSH",
    "shrunk_rate_COMPLETE_PASS","shrunk_rate_OTHER_PASS","shrunk_rate_RUSH",
    "pass_family_share","pass_family_credit_share",
)


def num(v:Any,default:float=0.0)->float:
    try:
        if v in (None,""):return float(default)
        x=float(v)
        return x if x==x else float(default)
    except (TypeError,ValueError):
        return float(default)


def canonical_position(v:Any)->str:
    x=str(v or "").strip().upper()
    if x in {"DB","CB","S","FS","SS","SAFETY"}:return "DB"
    if x in {"LB","ILB","MLB"}:return "LB"
    if x in {"EDGE","DE","OLB"}:return "EDGE"
    if x in {"DL","DT","NT"}:return "DL"
    return x or "UNK"


def _position_tokens(row:dict[str,Any])->set[str]:
    vals=[]
    for key in (
        "position","position_group","depth_position","current_depth_position",
        "previous_week_depth_position","depth_role",
    ):
        s=str(row.get(key) or "").strip().upper()
        if s:
            vals.append(s.replace("-","").replace("_","").replace(" ",""))
    return set(vals)


def canonical_position_row(row:dict[str,Any])->str:
    """Four-way tackle taxonomy: interior DL / EDGE / off-ball LB / DB.

    This classifier is intentionally conservative for the LB challenger. Any
    explicit edge evidence (DE/EDGE/OLB or depth-chart equivalents), or a provider
    conflict between generic LB and DL labels, is routed to EDGE and remains on
    frozen control. Only clean LB/ILB/MLB evidence can enter the off-ball-LB
    residual challenger.
    """
    toks=_position_tokens(row)

    db={"DB","CB","S","FS","SS","SAFETY"}
    edge={"DE","EDGE","OLB","LDE","RDE","LE","RE","LEO","RUSH","JACK"}
    interior={"DL","DT","NT","IDL","LDT","RDT"}
    offball={"LB","ILB","MLB"}

    if toks & db:
        return "DB"
    if toks & edge:
        return "EDGE"

    # Generic LB/DL disagreement is itself edge-like ambiguity. Do not allow such
    # rows into the off-ball-LB challenger.
    if (toks & offball) and (toks & interior):
        return "EDGE"

    if toks & interior:
        return "DL"
    if toks & {"ILB","MLB"}:
        return "LB"
    if "LB" in toks:
        return "LB"

    return canonical_position(row.get("position_group") or row.get("position"))


def assert_development_only(seasons:Iterable[int])->tuple[int,...]:
    s=tuple(sorted({int(x) for x in seasons}))
    if not s:raise ValueError("development seasons required")
    bad=[x for x in s if x>=HOLDOUT_SEASON]
    if bad:
        raise ValueError("OMEGA 0.36 development forbids sealed 2025 and prospective 2026: "+",".join(map(str,bad)))
    return s


def candidate_feature_names(position:str)->tuple[str,...]:
    p=canonical_position(position)
    if p=="LB":return LB_FEATURES
    if p=="DB":return DB_FEATURES
    if p in {"DL","EDGE"}:return ()
    raise ValueError(f"unsupported position group {position}")


def feature_map(row:dict[str,Any],position:str|None=None)->dict[str,float]:
    p=canonical_position(position) if position is not None else canonical_position_row(row)
    control=max(0.0,num(row.get("control_xtc",row.get("topology_xtc",row.get("predicted_xtc")))))
    rush=num(row.get("pred_credit_RUSH",row.get("control_pred_credit_RUSH")))
    scr=num(row.get("pred_credit_SCRAMBLE",row.get("control_pred_credit_SCRAMBLE")))
    sack=num(row.get("pred_credit_SACK",row.get("control_pred_credit_SACK")))
    comp=num(row.get("pred_credit_COMPLETE_PASS",row.get("control_pred_credit_COMPLETE_PASS")))
    other=num(row.get("pred_credit_OTHER_PASS",row.get("control_pred_credit_OTHER_PASS")))
    sr=num(row.get("pred_share_RUSH"))
    ss=num(row.get("pred_share_SCRAMBLE"))
    sc=num(row.get("pred_share_COMPLETE_PASS"))
    so=num(row.get("pred_share_OTHER_PASS"))
    denom=max(1e-9,control)
    out={
        "control_xtc":control,
        "predicted_xto":max(0.0,num(row.get("predicted_xto"))),
        "predicted_snap_share":max(0.0,min(1.0,num(row.get("predicted_snap_share",row.get("control_h012_snap_share"))))),
        "prior_games_log":log1p(max(0.0,num(row.get("prior_games")))),
        "pred_credit_RUSH":rush,
        "pred_credit_SCRAMBLE":scr,
        "pred_credit_COMPLETE_PASS":comp,
        "pred_credit_SACK":sack,
        "pred_credit_OTHER_PASS":other,
        "pred_share_RUSH":sr,
        "pred_share_SCRAMBLE":ss,
        "pred_share_COMPLETE_PASS":sc,
        "pred_share_SACK":num(row.get("pred_share_SACK")),
        "pred_share_OTHER_PASS":so,
        "shrunk_rate_RUSH":num(row.get("shrunk_rate_RUSH")),
        "shrunk_rate_SCRAMBLE":num(row.get("shrunk_rate_SCRAMBLE")),
        "shrunk_rate_COMPLETE_PASS":num(row.get("shrunk_rate_COMPLETE_PASS")),
        "shrunk_rate_SACK":num(row.get("shrunk_rate_SACK")),
        "shrunk_rate_OTHER_PASS":num(row.get("shrunk_rate_OTHER_PASS")),
        "rush_x_scramble_share":sr*ss,
        "mobile_family_credit_share":(scr+sack)/denom,
        "pass_family_share":sc+so,
        "pass_family_credit_share":(comp+other)/denom,
    }
    return out


def vector(row:dict[str,Any],position:str)->tuple[float,...]:
    fm=feature_map(row,position)
    return tuple(float(fm[n]) for n in candidate_feature_names(position))


def _solve(a:list[list[float]],b:list[float])->list[float]:
    n=len(b); aug=[list(map(float,r))+[float(y)] for r,y in zip(a,b)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(aug[r][col]))
        if abs(aug[pivot][col])<1e-12:raise ValueError("singular system")
        if pivot!=col:aug[col],aug[pivot]=aug[pivot],aug[col]
        z=aug[col][col];aug[col]=[x/z for x in aug[col]]
        for r in range(n):
            if r==col:continue
            f=aug[r][col]
            if abs(f)<1e-18:continue
            aug[r]=[x-f*y for x,y in zip(aug[r],aug[col])]
    return [aug[i][-1] for i in range(n)]


@dataclass
class ResidualModel:
    position:str
    feature_names:tuple[str,...]
    means:list[float]
    scales:list[float]
    intercept:float
    coefficients:list[float]
    l2:float=FIXED_L2

    def correction(self,row:dict[str,Any])->float:
        x=vector(row,self.position)
        z=self.intercept
        for i,v in enumerate(x):
            z+=self.coefficients[i]*((v-self.means[i])/self.scales[i])
        return max(-MAX_ABS_CORRECTION,min(MAX_ABS_CORRECTION,z))

    def predict(self,row:dict[str,Any])->float:
        base=max(0.0,num(row.get("control_xtc",row.get("topology_xtc",row.get("predicted_xtc")))))
        return max(0.0,base+self.correction(row))

    def to_dict(self)->dict[str,Any]:
        return {"version":VERSION,"lineage":LINEAGE,"position":self.position,
                "featureNames":list(self.feature_names),"means":self.means,"scales":self.scales,
                "intercept":self.intercept,"coefficients":self.coefficients,"l2":self.l2,
                "target":"actual_xtc_minus_control_xtc","maxAbsCorrection":MAX_ABS_CORRECTION}

    @classmethod
    def from_dict(cls,d:dict[str,Any])->"ResidualModel":
        return cls(
            position=canonical_position(d["position"]),
            feature_names=tuple(d["featureNames"]),
            means=[float(x) for x in d["means"]],
            scales=[float(x) for x in d["scales"]],
            intercept=float(d["intercept"]),
            coefficients=[float(x) for x in d["coefficients"]],
            l2=float(d.get("l2",FIXED_L2)),
        )


def fit_residual(rows:Sequence[dict[str,Any]],position:str,l2:float=FIXED_L2)->ResidualModel:
    p=canonical_position(position)
    names=candidate_feature_names(p)
    if p in {"DL","EDGE"}:raise ValueError(f"{p} is no-change control in 0.36")
    rr=[r for r in rows if canonical_position_row(r)==p]
    if len(rr)<50:raise ValueError(f"insufficient {p} training rows: {len(rr)}")
    xs=[vector(r,p) for r in rr]
    ys=[num(r.get("actual_xtc"))-num(r.get("control_xtc")) for r in rr]
    k=len(names)
    means=[fmean(x[j] for x in xs) for j in range(k)]
    scales=[]
    for j in range(k):
        var=fmean((x[j]-means[j])**2 for x in xs)
        scales.append(sqrt(var) if var>1e-12 else 1.0)
    zx=[[(x[j]-means[j])/scales[j] for j in range(k)] for x in xs]
    ybar=fmean(ys);yc=[y-ybar for y in ys]
    xtx=[[0.0]*k for _ in range(k)];xty=[0.0]*k;n=float(len(rr))
    for x,y in zip(zx,yc):
        for j in range(k):
            xty[j]+=x[j]*y/n
            for q in range(k):xtx[j][q]+=x[j]*x[q]/n
    for j in range(k):xtx[j][j]+=float(l2)
    coefs=_solve(xtx,xty)
    return ResidualModel(p,names,means,scales,ybar,coefs,float(l2))


def apply_challengers(rows:Sequence[dict[str,Any]],models:dict[str,ResidualModel],out_key:str="position_challenger_xtc")->list[dict[str,Any]]:
    out=[]
    for r in rows:
        z=dict(r);p=canonical_position_row(r);base=max(0.0,num(r.get("control_xtc")))
        if p=="DL":
            pred=base;corr=0.0;track="DL_CONTROL_NO_CHANGE"
        elif p=="EDGE":
            pred=base;corr=0.0;track="EDGE_OLB_CONTROL_NO_CHANGE"
        elif p in models:
            pred=models[p].predict(r);corr=pred-base;track=f"{p}_RESIDUAL_SHADOW"
        else:
            pred=base;corr=0.0;track="CONTROL_FALLBACK"
        z[out_key]=pred;z["position_challenger_correction"]=corr;z["position_challenger_track"]=track
        out.append(z)
    return out


def count_metrics(rows:Sequence[dict[str,Any]],pred_key:str)->dict[str,Any]:
    if not rows:return {"n":0}
    err=[num(r.get(pred_key))-num(r.get("actual_xtc")) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(x) for x in err),
            "rmse":sqrt(fmean(x*x for x in err)),"biasPredMinusActual":fmean(err)}


def paired_game_bootstrap(rows:Sequence[dict[str,Any]],base_key:str,cand_key:str,reps:int=1000,seed:int=20260919)->dict[str,Any]:
    by={}
    for r in rows:by.setdefault(str(r.get("game_id") or ""),[]).append(r)
    gids=sorted(k for k in by if k)
    if len(gids)<2:raise ValueError("bootstrap requires >=2 games")
    def delta(sample):
        b=count_metrics(sample,base_key);c=count_metrics(sample,cand_key)
        return {"maeImprovement":b["mae"]-c["mae"],"rmseImprovement":b["rmse"]-c["rmse"]}
    obs=delta(list(rows));rng=random.Random(seed);draws={k:[] for k in obs}
    for _ in range(reps):
        s=[]
        for _j in gids:s.extend(by[rng.choice(gids)])
        d=delta(s)
        for k,v in d.items():draws[k].append(v)
    def q(xs,p):
        z=sorted(xs);i=(len(z)-1)*p;lo=int(i);hi=min(lo+1,len(z)-1);w=i-lo
        return z[lo]*(1-w)+z[hi]*w
    return {"cluster":"game_id","reps":reps,"observed":obs,
            "ci95":{k:{"low":q(v,.025),"high":q(v,.975)} for k,v in draws.items()}}


def promotion_gate(position:str,base:dict[str,Any],cand:dict[str,Any],boot:dict[str,Any],brier_improvement:float|None)->dict[str,Any]:
    p=canonical_position(position)
    if p in {"DL","EDGE"}:
        return {"status":"KEEP_CONTROL","reason":f"{p} preregistered no-change reference in 0.36"}
    mae=base.get("mae",0)-cand.get("mae",0);rmse=base.get("rmse",0)-cand.get("rmse",0)
    ci=boot.get("ci95",{})
    qualifies=bool(mae>0 and rmse>0 and brier_improvement is not None and brier_improvement>0
                   and ci.get("maeImprovement",{}).get("low",0)>0
                   and ci.get("rmseImprovement",{}).get("low",0)>0)
    return {"status":"NEXT_STAGE_SHADOW_SIGNAL" if qualifies else "RESEARCH_ONLY_NO_PROMOTION",
            "maeImprovement":mae,"rmseImprovement":rmse,"brierImprovement":brier_improvement,
            "requiresProspectiveValidation":True}


if __name__=="__main__":
    print(f"OMEGA {VERSION} · {LINEAGE}")

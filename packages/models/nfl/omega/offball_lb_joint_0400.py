"""OMEGA 0.40 — joint clean off-ball-LB exposure + family-opportunity challenger.

0.40.0 LB EXPOSURE
  Fit the existing H012 strictly-lagged exposure feature set specifically on clean
  explicit ILB/MLB rows. Uses frozen H012 L2; no hyperparameter search.

0.40.1 FAMILY OPPORTUNITY
  Fit one fixed-L2 team model per H008 play family from strictly-lagged team
  opportunity features + strictly-lagged predicted family shares. Uses frozen xTO
  L2; no hyperparameter search.

0.40.2 PLAYER xTC ABLATIONS
  CONTROL          = frozen H008 opportunity * frozen H012 snap * frozen rate
  EXPOSURE_ONLY    = frozen opportunity * LB-specific snap * frozen rate
  OPPORTUNITY_ONLY = family-opportunity challenger * frozen snap * frozen rate
  JOINT            = family-opportunity challenger * LB-specific snap * frozen rate

Player family conversion rates stay frozen so this experiment isolates the two
mechanisms identified by OMEGA 0.39.

2025 is sealed. 2026 is prospective. Market data is forbidden.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import fmean
from typing import Any, Sequence
import math,random

VERSION="0.40.0"
LINEAGE="omega-offball-lb-joint-exposure-opportunity-v0.40.0-2026-09-19"
HOLDOUT_SEASON=2025
PROSPECTIVE_SEASON=2026
FAMILIES=("RUSH","COMPLETE_PASS","SCRAMBLE","SACK","OTHER_PASS")

# Borrow the already-frozen regularization values; do not tune them here.
EXPOSURE_L2=0.01
OPPORTUNITY_L2=0.3

EXPOSURE_FEATURES=(
    "position_prior_snap_share","prior_games_cap8","prior_games_log",
    "last1_snap_share","last2_snap_share_mean","last4_snap_share_mean",
    "last8_snap_share_mean","last4_snap_share_std","last4_snap_share_min",
    "last4_snap_share_max","last1_minus_last4","last2_minus_last8",
    "position_DB","position_LB","position_DL","position_OTHER",
    "cold_start","one_prior_game",
)

TEAM_BASE_FEATURES=(
    "off_def_snaps_mean8","def_def_snaps_mean8",
    "off_opportunity_plays_mean8","def_opportunity_plays_mean8",
    "off_opportunity_rate8","def_opportunity_rate8",
    "off_credits_per_opportunity8","def_credits_per_opportunity8",
    "off_rush_share8","off_complete_pass_share8","off_scramble_share8",
    "off_sack_share8","off_games_available8","def_games_available8",
)
OPPORTUNITY_FEATURES=TEAM_BASE_FEATURES+tuple(f"pred_share_{f}" for f in FAMILIES)


def num(v:Any,default:float=0.0)->float:
    try:
        if v in (None,""):return float(default)
        x=float(v)
        return x if math.isfinite(x) else float(default)
    except (TypeError,ValueError):
        return float(default)


def assert_development_only(seasons:Sequence[int])->tuple[int,...]:
    s=tuple(sorted({int(x) for x in seasons}))
    if not s:raise ValueError("development seasons required")
    if any(x>=HOLDOUT_SEASON for x in s):
        raise ValueError("OMEGA 0.40 forbids 2025+ in development")
    return s


def _solve(a:list[list[float]],b:list[float])->list[float]:
    n=len(b);aug=[list(map(float,r))+[float(y)] for r,y in zip(a,b)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(aug[r][col]))
        if abs(aug[pivot][col])<1e-12:aug[pivot][col]+=1e-8
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
class RidgeModel:
    feature_names:tuple[str,...]
    means:list[float]
    scales:list[float]
    intercept:float
    coefficients:list[float]
    l2:float
    target_name:str
    clip_low:float=0.0
    clip_high:float|None=None

    def predict(self,row:dict[str,Any])->float:
        z=self.intercept
        for i,n in enumerate(self.feature_names):
            z+=self.coefficients[i]*((num(row.get(n))-self.means[i])/self.scales[i])
        z=max(self.clip_low,z)
        if self.clip_high is not None:z=min(self.clip_high,z)
        return z

    def to_dict(self):
        return {
            "version":VERSION,"lineage":LINEAGE,"modelClass":"STANDARDIZED_FIXED_L2_RIDGE",
            "featureNames":list(self.feature_names),"means":self.means,"scales":self.scales,
            "intercept":self.intercept,"coefficients":self.coefficients,"l2":self.l2,
            "targetName":self.target_name,"clipLow":self.clip_low,"clipHigh":self.clip_high,
        }

    @classmethod
    def from_dict(cls,d):
        return cls(tuple(d["featureNames"]),[float(x) for x in d["means"]],[float(x) for x in d["scales"]],
                   float(d["intercept"]),[float(x) for x in d["coefficients"]],float(d["l2"]),
                   str(d["targetName"]),float(d.get("clipLow",0.0)),
                   None if d.get("clipHigh") is None else float(d["clipHigh"]))


def fit_ridge(rows:Sequence[dict[str,Any]],features:tuple[str,...],target:str,l2:float,
              clip_high:float|None=None)->RidgeModel:
    if len(rows)<100:raise ValueError(f"insufficient rows for {target}: {len(rows)}")
    xs=[[num(r.get(n)) for n in features] for r in rows];ys=[num(r.get(target)) for r in rows]
    p=len(features);means=[fmean(x[j] for x in xs) for j in range(p)];scales=[]
    for j in range(p):
        var=fmean((x[j]-means[j])**2 for x in xs)
        scales.append(sqrt(var) if var>1e-12 else 1.0)
    zx=[[(x[j]-means[j])/scales[j] for j in range(p)] for x in xs]
    ybar=fmean(ys);yc=[y-ybar for y in ys];n=float(len(rows))
    xtx=[[0.0]*p for _ in range(p)];xty=[0.0]*p
    for x,y in zip(zx,yc):
        for j in range(p):
            xty[j]+=x[j]*y/n
            for q in range(p):xtx[j][q]+=x[j]*x[q]/n
    for j in range(p):xtx[j][j]+=float(l2)
    beta=_solve(xtx,xty)
    return RidgeModel(features,means,scales,ybar,beta,float(l2),target,0.0,clip_high)


def build_exposure_examples(control_rows:Sequence[dict],exposure_rows:Sequence[dict])->list[dict]:
    """Join clean-control identities to strictly-lagged H012 feature rows."""
    emap={(str(r.get("game_id") or ""),str(r.get("team") or ""),str(r.get("player_id") or "")):r for r in exposure_rows}
    out=[]
    for c in control_rows:
        key=(str(c.get("game_id") or ""),str(c.get("team") or ""),str(c.get("player_id") or ""))
        e=emap.get(key)
        if e is None:continue
        z=dict(e)
        z["control_snap_share"]=num(c.get("predicted_snap_share"))
        z["actual_snap_share"]=num(c.get("actual_snap_share"),num(e.get("actual_snap_share")))
        out.append(z)
    return out


def build_opportunity_examples(team_rows:Sequence[dict],family_rows:Sequence[dict])->list[dict]:
    """Join strictly-lagged team predictors to strictly-lagged family-share rows."""
    tmap={(str(r.get("game_id") or ""),str(r.get("defense_team") or "")):r for r in team_rows}
    out=[]
    for f in family_rows:
        key=(str(f.get("game_id") or ""),str(f.get("defense_team") or ""))
        t=tmap.get(key)
        if t is None:continue
        z=dict(t)
        z.update({
            "game_id":key[0],"defense_team":key[1],
            "season":int(num(f.get("season"))),"week":int(num(f.get("week"))),
        })
        for fam in FAMILIES:
            z[f"pred_share_{fam}"]=num(f.get(f"pred_share_{fam}"))
            z[f"actual_opp_{fam}"]=num(f.get(f"actual_opp_{fam}"))
        out.append(z)
    return out


def fit_exposure(rows:Sequence[dict])->RidgeModel:
    return fit_ridge(rows,EXPOSURE_FEATURES,"actual_snap_share",EXPOSURE_L2,clip_high=1.0)


def fit_opportunities(rows:Sequence[dict])->dict[str,RidgeModel]:
    return {f:fit_ridge(rows,OPPORTUNITY_FEATURES,f"actual_opp_{f}",OPPORTUNITY_L2) for f in FAMILIES}


def score_ablation(control_rows:Sequence[dict],exposure_model:RidgeModel,
                   exposure_feature_map:dict[tuple[str,str,str],dict],
                   opportunity_models:dict[str,RidgeModel],
                   opportunity_feature_map:dict[tuple[str,str],dict])->list[dict]:
    out=[]
    for r in control_rows:
        pk=(str(r.get("game_id") or ""),str(r.get("team") or ""),str(r.get("player_id") or ""))
        tk=(pk[0],pk[1]);er=exposure_feature_map.get(pk);tr=opportunity_feature_map.get(tk)
        if er is None or tr is None:continue
        base_snap=max(0.0,min(1.0,num(r.get("predicted_snap_share"))))
        chal_snap=exposure_model.predict(er)
        z=dict(r);z["omega040_exposure_snap_share"]=chal_snap
        totals={"control":0.0,"exposure":0.0,"opportunity":0.0,"joint":0.0}
        for f in FAMILIES:
            base_opp=max(0.0,num(r.get(f"pred_opp_{f}")))
            chal_opp=max(0.0,opportunity_models[f].predict(tr))
            rate=max(0.0,num(r.get(f"shrunk_rate_{f}")))
            z[f"omega040_opp_{f}"]=chal_opp
            z[f"omega040_credit_control_{f}"]=base_opp*base_snap*rate
            z[f"omega040_credit_exposure_{f}"]=base_opp*chal_snap*rate
            z[f"omega040_credit_opportunity_{f}"]=chal_opp*base_snap*rate
            z[f"omega040_credit_joint_{f}"]=chal_opp*chal_snap*rate
            totals["control"]+=z[f"omega040_credit_control_{f}"]
            totals["exposure"]+=z[f"omega040_credit_exposure_{f}"]
            totals["opportunity"]+=z[f"omega040_credit_opportunity_{f}"]
            totals["joint"]+=z[f"omega040_credit_joint_{f}"]
        z["omega040_control_xtc"]=totals["control"]
        z["omega040_exposure_only_xtc"]=totals["exposure"]
        z["omega040_opportunity_only_xtc"]=totals["opportunity"]
        z["omega040_joint_xtc"]=totals["joint"]
        out.append(z)
    return out


def metrics(rows:Sequence[dict],pred_key:str,actual_key:str="actual_xtc")->dict[str,Any]:
    if not rows:return {"n":0}
    e=[num(r.get(pred_key))-num(r.get(actual_key)) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(x) for x in e),"rmse":sqrt(fmean(x*x for x in e)),
            "biasPredMinusActual":fmean(e)}


def snap_metrics(rows:Sequence[dict],pred_key:str)->dict[str,Any]:
    return metrics(rows,pred_key,"actual_snap_share")


def opportunity_metrics(rows:Sequence[dict],fam:str,pred_key:str)->dict[str,Any]:
    return metrics(rows,pred_key,f"actual_opp_{fam}")


def paired_game_bootstrap(rows:Sequence[dict],base_key:str,cand_key:str,reps:int=1000,seed:int=20260919):
    by={}
    for r in rows:by.setdefault(str(r.get("game_id") or ""),[]).append(r)
    gids=sorted(k for k in by if k)
    if len(gids)<2:raise ValueError("bootstrap requires >=2 games")
    def delta(sample):
        b=metrics(sample,base_key);c=metrics(sample,cand_key)
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


def advancement_gate(folds:list[dict],base:dict,joint:dict,boot:dict,
                     snap_improvement:float,opportunity_improvement:float):
    ci=boot["ci95"];positive=sum(1 for f in folds if f["jointMaeImprovement"]>0)
    bias_ok=abs(joint["biasPredMinusActual"])<=abs(base["biasPredMinusActual"])+0.05
    ok=bool(
        base["mae"]>joint["mae"] and base["rmse"]>joint["rmse"]
        and ci["maeImprovement"]["low"]>0 and ci["rmseImprovement"]["low"]>0
        and positive>=3 and bias_ok and snap_improvement>0 and opportunity_improvement>0
    )
    return {
        "status":"NEXT_STAGE_SHADOW_SIGNAL" if ok else "RESEARCH_ONLY_NO_PROMOTION",
        "positiveJointMaeSeasons":positive,"requiredPositiveJointMaeSeasons":3,
        "snapMaeImprovement":snap_improvement,"meanFamilyOpportunityMaeImprovement":opportunity_improvement,
        "absBiasGatePass":bias_ok,
        "probabilityCalibrationGate":"DEFERRED_TO_PROSPECTIVE_OR_CHRONOLOGICAL_DISTRIBUTION_FIT",
    }

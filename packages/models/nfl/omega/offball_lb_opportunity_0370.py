"""OMEGA 0.37.0-0.37.2 — generative off-ball-LB tackle opportunity challenger.

This module decomposes player tackle credits into two football mechanisms:

0.37.0 TEAM POOL
    Predict the total standard defensive tackle credits that clean off-ball LBs on
    a defense will receive in a game.

0.37.1 PLAYER ALLOCATION
    Predict each clean off-ball LB's share of that team LB tackle-credit pool.

0.37.2 COMBINED PLAYER xTC
    predicted team LB pool * predicted player allocation share.

All features are available pregame. Team/player outcome histories are updated only
after an entire week is emitted. No market fields are accepted or referenced.

The 2025 holdout is sealed. 2026 is prospective and may not enter development fit.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import log1p, sqrt
from statistics import fmean
from typing import Any, Sequence
import math
import random

VERSION="0.37.0"
LINEAGE="omega-offball-lb-generative-v0.37.0-2026-09-19"
HOLDOUT_SEASON=2025
PROSPECTIVE_SEASON=2026
FIXED_L2_TEAM=1.0
FIXED_L2_ALLOC=1.0
HISTORY_WINDOW=8

FAMILIES=("RUSH","COMPLETE_PASS","SCRAMBLE","SACK","OTHER_PASS")

TEAM_FEATURES=(
    "predicted_xto",
    "lb_predicted_snap_sum",
    "lb_player_count",
    "pred_opp_RUSH",
    "pred_opp_COMPLETE_PASS",
    "pred_opp_SCRAMBLE",
    "pred_opp_SACK",
    "pred_opp_OTHER_PASS",
    "lag_lb_pool_last1",
    "lag_lb_pool_mean2",
    "lag_lb_pool_mean4",
    "lag_lb_pool_mean8",
    "lag_lb_pool_per_xto_mean4",
    "prior_team_games_log",
)

ALLOC_FEATURES=(
    "predicted_snap_share",
    "snap_share_within_lb_room",
    "predicted_credit_share_within_lb_room",
    "prior_games_log",
    "pred_credit_RUSH_share_room",
    "pred_credit_COMPLETE_PASS_share_room",
    "pred_credit_SCRAMBLE_share_room",
    "pred_credit_SACK_share_room",
    "pred_credit_OTHER_PASS_share_room",
    "lag_player_lb_share_last1",
    "lag_player_lb_share_mean2",
    "lag_player_lb_share_mean4",
    "lag_player_lb_share_mean8",
    "lb_player_count",
    "max_other_predicted_snap_share",
)


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
        raise ValueError("OMEGA 0.37 development forbids sealed 2025 and prospective 2026")
    return s


def mean_or(xs:Sequence[float],fallback:float)->float:
    return fmean(xs) if xs else float(fallback)


def _solve(a:list[list[float]],b:list[float])->list[float]:
    n=len(b);aug=[list(map(float,r))+[float(y)] for r,y in zip(a,b)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(aug[r][col]))
        if abs(aug[pivot][col])<1e-12:
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
            z+=self.coefficients[i]*((float(row[n])-self.means[i])/self.scales[i])
        z=max(self.clip_low,z)
        if self.clip_high is not None:z=min(self.clip_high,z)
        return z

    def to_dict(self)->dict[str,Any]:
        return {
            "version":VERSION,"lineage":LINEAGE,"modelClass":"STANDARDIZED_FIXED_L2_RIDGE",
            "featureNames":list(self.feature_names),"means":self.means,"scales":self.scales,
            "intercept":self.intercept,"coefficients":self.coefficients,"l2":self.l2,
            "targetName":self.target_name,"clipLow":self.clip_low,"clipHigh":self.clip_high,
        }

    @classmethod
    def from_dict(cls,d:dict[str,Any])->"RidgeModel":
        return cls(
            tuple(d["featureNames"]),[float(x) for x in d["means"]],[float(x) for x in d["scales"]],
            float(d["intercept"]),[float(x) for x in d["coefficients"]],float(d["l2"]),
            str(d["targetName"]),float(d.get("clipLow",0.0)),
            None if d.get("clipHigh") is None else float(d["clipHigh"]),
        )


def fit_ridge(rows:Sequence[dict[str,Any]],features:tuple[str,...],target:str,l2:float,
              clip_high:float|None=None)->RidgeModel:
    if len(rows)<100:raise ValueError(f"insufficient rows for {target}: {len(rows)}")
    xs=[[float(r[n]) for n in features] for r in rows]
    ys=[float(r[target]) for r in rows]
    p=len(features);means=[fmean(x[j] for x in xs) for j in range(p)]
    scales=[]
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


def _season_week(r:dict[str,Any])->tuple[int,int]:
    return int(num(r.get("season"))),int(num(r.get("week")))


def build_decomposition_rows(clean_lb_control_rows:Sequence[dict[str,Any]])->tuple[list[dict],list[dict]]:
    """Build leakage-safe team-pool and player-allocation examples.

    Input rows must already be clean explicit off-ball LB rows with pregame OMEGA
    control features and target-game actual_xtc outcome.
    """
    if not clean_lb_control_rows:return [],[]
    if any(int(num(r.get("season")))>=HOLDOUT_SEASON for r in clean_lb_control_rows):
        raise ValueError("sealed/prospective row entered OMEGA 0.37 decomposition")

    groups:dict[tuple[int,int,str,str],list[dict[str,Any]]]=defaultdict(list)
    for r in clean_lb_control_rows:
        season,week=_season_week(r)
        key=(season,week,str(r.get("game_id") or ""),str(r.get("team") or ""))
        if key[2] and key[3]:groups[key].append(r)

    team_hist:dict[str,list[dict[str,float]]]=defaultdict(list)
    player_hist:dict[str,list[float]]=defaultdict(list)
    team_rows=[];player_rows=[]

    week_keys=sorted({(k[0],k[1]) for k in groups})
    for sw in week_keys:
        batch=[(k,v) for k,v in groups.items() if (k[0],k[1])==sw]
        pending_team=[];pending_player=[]
        for key,rr in sorted(batch,key=lambda kv:(kv[0][2],kv[0][3])):
            season,week,gid,team=key
            actual_pool=sum(max(0.0,num(r.get("actual_xtc"))) for r in rr)
            xto=mean_or([num(r.get("predicted_xto")) for r in rr],0.0)
            snap_sum=sum(max(0.0,num(r.get("predicted_snap_share"))) for r in rr)
            nplayers=len(rr)
            fam_share={f:mean_or([num(r.get(f"pred_share_{f}")) for r in rr],0.0) for f in FAMILIES}

            th=team_hist[team][-HISTORY_WINDOW:]
            fallback_pool=6.0
            last1=th[-1]["pool"] if th else fallback_pool
            pools=[x["pool"] for x in th]
            pxto=[x["pool_per_xto"] for x in th]
            team_row={
                "game_id":gid,"season":season,"week":week,"team":team,
                "opponent":str(rr[0].get("opponent") or ""),
                "actual_lb_pool":actual_pool,
                "control_lb_pool":sum(max(0.0,num(r.get("control_xtc"))) for r in rr),
                "predicted_xto":xto,"lb_predicted_snap_sum":snap_sum,
                "lb_player_count":float(nplayers),
                "lag_lb_pool_last1":last1,
                "lag_lb_pool_mean2":mean_or(pools[-2:],fallback_pool),
                "lag_lb_pool_mean4":mean_or(pools[-4:],fallback_pool),
                "lag_lb_pool_mean8":mean_or(pools[-8:],fallback_pool),
                "lag_lb_pool_per_xto_mean4":mean_or(pxto[-4:],fallback_pool/max(1.0,xto)),
                "prior_team_games_log":log1p(len(th)),
            }
            for f in FAMILIES:
                team_row[f"pred_opp_{f}"]=max(0.0,xto*fam_share[f])
            team_rows.append(team_row)
            pending_team.append((team,actual_pool,actual_pool/max(1e-9,xto)))

            room_credit_total=sum(max(0.0,num(r.get("control_xtc"))) for r in rr)
            room_family_total={f:sum(max(0.0,num(r.get(f"pred_credit_{f}"))) for r in rr) for f in FAMILIES}
            max_snap=max([max(0.0,num(r.get("predicted_snap_share"))) for r in rr] or [0.0])
            for r in rr:
                pid=str(r.get("player_id") or "")
                actual=max(0.0,num(r.get("actual_xtc")))
                target_share=(actual/actual_pool) if actual_pool>0 else 0.0
                ph=player_hist[pid][-HISTORY_WINDOW:]
                fallback_share=1.0/max(1,nplayers)
                ps=max(0.0,num(r.get("predicted_snap_share")))
                row={
                    "game_id":gid,"season":season,"week":week,"team":team,
                    "opponent":str(r.get("opponent") or ""),"player_id":pid,
                    "display_name":str(r.get("display_name") or r.get("player_name") or ""),
                    "position":str(r.get("position") or ""),"position_group":str(r.get("position_group") or ""),
                    "actual_xtc":actual,"actual_lb_pool":actual_pool,"actual_lb_share":target_share,
                    "control_xtc":max(0.0,num(r.get("control_xtc"))),
                    "control_lb_pool":room_credit_total,
                    "control_lb_share":max(0.0,num(r.get("control_xtc")))/max(1e-9,room_credit_total),
                    "predicted_snap_share":ps,
                    "snap_share_within_lb_room":ps/max(1e-9,snap_sum),
                    "predicted_credit_share_within_lb_room":max(0.0,num(r.get("control_xtc")))/max(1e-9,room_credit_total),
                    "prior_games_log":log1p(max(0.0,num(r.get("prior_games")))),
                    "lag_player_lb_share_last1":ph[-1] if ph else fallback_share,
                    "lag_player_lb_share_mean2":mean_or(ph[-2:],fallback_share),
                    "lag_player_lb_share_mean4":mean_or(ph[-4:],fallback_share),
                    "lag_player_lb_share_mean8":mean_or(ph[-8:],fallback_share),
                    "lb_player_count":float(nplayers),
                    "max_other_predicted_snap_share":max([max(0.0,num(x.get("predicted_snap_share"))) for x in rr if str(x.get("player_id") or "")!=pid] or [0.0]),
                }
                for f in FAMILIES:
                    val=max(0.0,num(r.get(f"pred_credit_{f}")))
                    row[f"pred_credit_{f}_share_room"]=val/max(1e-9,room_family_total[f])
                player_rows.append(row)
                pending_player.append((pid,target_share))

        # No target-week outcome enters another row from that week.
        for team,pool,pxto in pending_team:
            team_hist[team].append({"pool":pool,"pool_per_xto":pxto})
        for pid,share in pending_player:
            player_hist[pid].append(share)

    return team_rows,player_rows


def normalize_allocation_predictions(rows:Sequence[dict[str,Any]],model:RidgeModel,
                                     raw_key:str="alloc_raw",out_key:str="predicted_lb_share")->list[dict]:
    by:dict[tuple[str,str],list[dict]]=defaultdict(list)
    for r in rows:
        z=dict(r);z[raw_key]=max(0.0,model.predict(r))
        by[(str(z.get("game_id") or ""),str(z.get("team") or ""))].append(z)
    out=[]
    for _,rr in sorted(by.items()):
        s=sum(float(r[raw_key]) for r in rr)
        if s<=1e-12:
            # fallback is pregame projected snap share, then equal share.
            ss=sum(max(0.0,num(r.get("predicted_snap_share"))) for r in rr)
            for r in rr:
                r[out_key]=(max(0.0,num(r.get("predicted_snap_share")))/ss) if ss>0 else 1.0/len(rr)
        else:
            for r in rr:r[out_key]=float(r[raw_key])/s
        out.extend(rr)
    return out


def apply_combined(team_rows:Sequence[dict],player_rows:Sequence[dict],
                   team_model:RidgeModel,alloc_model:RidgeModel)->list[dict]:
    tp={}
    for r in team_rows:
        tp[(str(r.get("game_id") or ""),str(r.get("team") or ""))]=team_model.predict(r)
    alloc=normalize_allocation_predictions(player_rows,alloc_model)
    out=[]
    for r in alloc:
        z=dict(r);pool=tp[(str(r.get("game_id") or ""),str(r.get("team") or ""))]
        z["predicted_lb_pool"]=pool
        z["omega_037_xtc"]=max(0.0,pool*float(z["predicted_lb_share"]))
        out.append(z)
    return out


def count_metrics(rows:Sequence[dict],pred_key:str,actual_key:str="actual_xtc")->dict[str,Any]:
    if not rows:return {"n":0}
    err=[num(r.get(pred_key))-num(r.get(actual_key)) for r in rows]
    return {"n":len(rows),"mae":fmean(abs(e) for e in err),"rmse":sqrt(fmean(e*e for e in err)),
            "biasPredMinusActual":fmean(err)}


def team_metrics(rows:Sequence[dict],pred_key:str)->dict[str,Any]:
    return count_metrics(rows,pred_key,"actual_lb_pool")


def allocation_metrics(rows:Sequence[dict],pred_key:str)->dict[str,Any]:
    return count_metrics(rows,pred_key,"actual_lb_share")


def paired_game_bootstrap(rows:Sequence[dict],base_key:str,cand_key:str,reps:int=1000,seed:int=20260919)->dict[str,Any]:
    by=defaultdict(list)
    for r in rows:by[str(r.get("game_id") or "")].append(r)
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


def promotion_gate(*,folds:list[dict],base:dict,cand:dict,brier_improvement:float,
                   bootstrap:dict,team_pool_improvement:float,allocation_improvement:float)->dict[str,Any]:
    positive_seasons=sum(1 for f in folds if f.get("maeImprovement",0)>0)
    abs_bias_ok=abs(cand.get("biasPredMinusActual",0))<=abs(base.get("biasPredMinusActual",0))+0.05
    ci=bootstrap["ci95"]
    qualifies=bool(
        base["mae"]>cand["mae"] and base["rmse"]>cand["rmse"] and brier_improvement>0
        and ci["maeImprovement"]["low"]>0 and ci["rmseImprovement"]["low"]>0
        and positive_seasons>=3 and abs_bias_ok
        and team_pool_improvement>0 and allocation_improvement>0
    )
    return {
        "status":"NEXT_STAGE_SHADOW_SIGNAL" if qualifies else "RESEARCH_ONLY_NO_PROMOTION",
        "positiveMaeSeasons":positive_seasons,"requiredPositiveMaeSeasons":3,
        "absBiasGatePass":abs_bias_ok,
        "teamPoolMaeImprovement":team_pool_improvement,
        "allocationShareMaeImprovement":allocation_improvement,
        "requiresProspectiveValidation":True,
    }


if __name__=="__main__":
    print(f"OMEGA {VERSION} · {LINEAGE}")

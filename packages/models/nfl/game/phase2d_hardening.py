"""NFL 2.9.0 Phase 2D pre-holdout hardening primitives.

Research-only. This module has no sportsbook dependency and never opens the 2025
holdout. It adds strict-lag context, calibration diagnostics, paired block
bootstrap inference, and market-edge math that consumes an already independent
probability downstream.
"""
from __future__ import annotations

from collections import defaultdict
from math import log, log1p
from statistics import fmean
from typing import Any, Callable, Iterable, Sequence

VERSION = "0.4.2"
LINEAGE = "nfl-game-v0.4.2-base-api-compat-solver-control-2026-09-10"
HOLDOUT_SEASON = 2025
QB_METRICS = ("epa", "cpoe", "sack_rate", "explosive_pass_rate", "int_rate")
QB_HORIZONS = ("prior_season", "last4", "last8")
OL_POSITIONS = frozenset({"C", "G", "OG", "LG", "RG", "T", "OT", "LT", "RT", "OL"})
SKILL_POSITIONS = frozenset({"WR", "RB", "FB", "TE"})


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _game_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return int(float(row["season"])), int(float(row["week"])), str(row["game_id"])


def _qb_summary(rows: Sequence[dict[str, Any]]) -> dict[str, float | int | None]:
    total_db = sum(int(float(r.get("dropbacks") or 0)) for r in rows)
    out: dict[str, float | int | None] = {"games": len(rows), "dropbacks": total_db}
    for metric in QB_METRICS:
        pairs = []
        for r in rows:
            x = _num(r.get(metric)); n = int(float(r.get("dropbacks") or 0))
            if x is not None and n > 0:
                pairs.append((x, n))
        den = sum(n for _, n in pairs)
        out[metric] = sum(x * n for x, n in pairs) / den if den else None
    return out


def build_strict_lag_qb_context(
    games: Iterable[dict[str, Any]], qb_game_rows: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build QB state with no target-week roster input.

    For target game G, the candidate QB is only the team's most recent observed
    primary QB from a strictly earlier game. This cannot detect a new starter,
    intentionally trading information for provable temporal safety.
    """
    games_sorted = sorted((dict(g) for g in games), key=_game_key)
    primary_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_qb: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in qb_game_rows:
        r = dict(raw)
        if int(float(r.get("observed_primary") or 0)) == 1:
            primary_by_team[_clean(r.get("team")).upper()].append(r)
        qid = _clean(r.get("qb_gsis_id"))
        if qid:
            by_qb[qid].append(r)
    for d in (primary_by_team, by_qb):
        for rows in d.values():
            rows.sort(key=_game_key)

    out = []
    for g in games_sorted:
        season, week, gid = _game_key(g)
        if season >= HOLDOUT_SEASON:
            continue
        row = {
            "game_id": gid, "season": season, "week": week,
            "home_team": _clean(g.get("home_team")).upper(),
            "away_team": _clean(g.get("away_team")).upper(),
        }
        for side in ("home", "away"):
            team = row[f"{side}_team"]
            target = (season, week, gid)
            priors = [r for r in primary_by_team.get(team, []) if _game_key(r) < target]
            prev = priors[-1] if priors else None
            qid = _clean(prev.get("qb_gsis_id")) if prev else ""
            row[f"{side}_lag_qb_gsis_id"] = qid
            row[f"{side}_lag_qb_available"] = 1.0 if qid else 0.0
            row[f"{side}_lag_prev_primary_share"] = _num(prev.get("primary_dropback_share")) if prev else None
            hist = [r for r in by_qb.get(qid, []) if _game_key(r) < target] if qid else []
            for horizon in QB_HORIZONS:
                if horizon == "prior_season":
                    use = [r for r in hist if int(float(r["season"])) == season - 1]
                elif horizon == "last4":
                    use = hist[-4:]
                else:
                    use = hist[-8:]
                s = _qb_summary(use)
                row[f"{side}_{horizon}_lag_qb_games"] = float(s["games"])
                row[f"{side}_{horizon}_lag_qb_dropbacks"] = float(s["dropbacks"])
                for metric in QB_METRICS:
                    row[f"{side}_{horizon}_lag_qb_{metric}"] = s[metric]
        out.append(row)
    return out


def _snap_presence(rows: Sequence[dict[str, Any]], snap_field: str, positions: set[str] | None = None) -> set[str]:
    out = set()
    for r in rows:
        n = _num(r.get(snap_field))
        pos = _clean(r.get("position")).upper()
        pid = _clean(r.get("pfr_player_id"))
        if n is None or n <= 0 or not pid:
            continue
        if positions is not None and pos not in positions:
            continue
        out.add(pid)
    return out


def _weighted_retention(
    older: Sequence[dict[str, Any]], newer: Sequence[dict[str, Any]], snap_field: str, positions: set[str] | None = None
) -> float | None:
    newer_ids = _snap_presence(newer, snap_field, positions)
    den = 0.0; num = 0.0
    for r in older:
        n = _num(r.get(snap_field)); pos = _clean(r.get("position")).upper(); pid = _clean(r.get("pfr_player_id"))
        if n is None or n <= 0:
            continue
        if positions is not None and pos not in positions:
            continue
        den += n
        if pid and pid in newer_ids:
            num += n
    return num / den if den > 0 else None


def build_strict_lag_snap_context(
    games: Iterable[dict[str, Any]], snap_rows: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build continuity using only two strictly earlier snap-count games.

    For target G, continuity is measured from G-2 to G-1. Target-week roster
    membership and target-game snaps are never used. Week 1 naturally reaches
    into the previous season when two earlier franchise games are available.
    """
    games_sorted = sorted((dict(g) for g in games), key=_game_key)
    order = {str(g["game_id"]): _game_key(g) for g in games_sorted}
    by_team_game: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    meta: dict[tuple[str, str], tuple[int, int, str]] = {}
    for raw in snap_rows:
        gid = _clean(raw.get("game_id")); team = _clean(raw.get("team")).upper()
        if not gid or not team or gid not in order:
            continue
        by_team_game[(team, gid)].append(dict(raw)); meta[(team, gid)] = order[gid]
    games_by_team: dict[str, list[tuple[tuple[int, int, str], str]]] = defaultdict(list)
    for team, gid in by_team_game:
        games_by_team[team].append((meta[(team, gid)], gid))
    for v in games_by_team.values():
        v.sort()

    out = []
    for g in games_sorted:
        season, week, gid = _game_key(g)
        if season >= HOLDOUT_SEASON:
            continue
        row = {"game_id": gid, "season": season, "week": week,
               "home_team": _clean(g.get("home_team")).upper(), "away_team": _clean(g.get("away_team")).upper()}
        for side in ("home", "away"):
            team = row[f"{side}_team"]
            prior = [x for x in games_by_team.get(team, []) if x[0] < (season, week, gid)]
            older_gid = prior[-2][1] if len(prior) >= 2 else ""
            newer_gid = prior[-1][1] if len(prior) >= 1 else ""
            older = by_team_game.get((team, older_gid), [])
            newer = by_team_game.get((team, newer_gid), [])
            row[f"{side}_lag_continuity_from_game_id"] = older_gid
            row[f"{side}_lag_continuity_to_game_id"] = newer_gid
            row[f"{side}_lag_offense_snap_continuity"] = _weighted_retention(older, newer, "offense_snaps") if older and newer else None
            row[f"{side}_lag_ol_snap_continuity"] = _weighted_retention(older, newer, "offense_snaps", set(OL_POSITIONS)) if older and newer else None
            row[f"{side}_lag_skill_snap_continuity"] = _weighted_retention(older, newer, "offense_snaps", set(SKILL_POSITIONS)) if older and newer else None
            row[f"{side}_lag_defense_snap_continuity"] = _weighted_retention(older, newer, "defense_snaps") if older and newer else None
            # Combined usage retention uses both sides of the ball without double-counting position labels.
            o = row[f"{side}_lag_offense_snap_continuity"]
            d = row[f"{side}_lag_defense_snap_continuity"]
            row[f"{side}_lag_overall_snap_continuity"] = None if o is None or d is None else (o + d) / 2.0
        out.append(row)
    return out


STRICT_QB_STEMS = ("lag_qb_available", "lag_prev_primary_share")
STRICT_SNAP_STEMS = (
    "lag_offense_snap_continuity", "lag_ol_snap_continuity", "lag_skill_snap_continuity",
    "lag_defense_snap_continuity", "lag_overall_snap_continuity",
)


def strict_context_base_names() -> tuple[str, ...]:
    out = ["week1", "early_season"]
    out += [f"{s}_diff" for s in STRICT_QB_STEMS]
    for h in QB_HORIZONS:
        out += [f"{h}_lag_qb_games_diff", f"{h}_lag_qb_log_dropbacks_diff"]
        out += [f"{h}_lag_qb_{m}_diff" for m in QB_METRICS]
    out += [f"{s}_diff" for s in STRICT_SNAP_STEMS]
    return tuple(out)


def _diff(row: dict[str, Any], stem: str) -> float | None:
    h = _num(row.get("home_" + stem)); a = _num(row.get("away_" + stem))
    return None if h is None or a is None else h - a


def vectorize_strict_context(row: dict[str, Any]) -> tuple[float | None, ...]:
    week = int(float(row.get("week") or 0))
    vals: dict[str, float | None] = {"week1": 1.0 if week == 1 else 0.0, "early_season": 1.0 if 1 <= week <= 4 else 0.0}
    for s in STRICT_QB_STEMS:
        vals[f"{s}_diff"] = _diff(row, s)
    for h in QB_HORIZONS:
        vals[f"{h}_lag_qb_games_diff"] = _diff(row, f"{h}_lag_qb_games")
        hd = _num(row.get(f"home_{h}_lag_qb_dropbacks")); ad = _num(row.get(f"away_{h}_lag_qb_dropbacks"))
        vals[f"{h}_lag_qb_log_dropbacks_diff"] = None if hd is None or ad is None else log1p(max(0.0, hd)) - log1p(max(0.0, ad))
        for m in QB_METRICS:
            vals[f"{h}_lag_qb_{m}_diff"] = _diff(row, f"{h}_lag_qb_{m}")
    for s in STRICT_SNAP_STEMS:
        vals[f"{s}_diff"] = _diff(row, s)
    out: list[float | None] = []
    for n in strict_context_base_names():
        v = vals[n]; out.extend([v, 1.0 if v is None else 0.0])
    return tuple(out)


def expanded_strict_context_names() -> tuple[str, ...]:
    out = []
    for n in strict_context_base_names():
        out.extend([n, "missing__" + n])
    return tuple(out)


def combined_strict_names(base_names: Sequence[str], *, include_qb: bool = True, include_snap: bool = True) -> tuple[str, ...]:
    keep = []
    for n in expanded_strict_context_names():
        core = n[9:] if n.startswith("missing__") else n
        fam = "stage" if core in {"week1", "early_season"} else ("qb" if "qb_" in core else "snap")
        if fam == "stage" or (fam == "qb" and include_qb) or (fam == "snap" and include_snap):
            keep.append(n)
    return tuple(base_names) + tuple(keep)


def combined_strict_vector(
    base_x: Sequence[float | None], row: dict[str, Any], base_names: Sequence[str], *, include_qb: bool = True, include_snap: bool = True
) -> tuple[float | None, ...]:
    names = expanded_strict_context_names(); vals = vectorize_strict_context(row); idx = {n: i for i, n in enumerate(names)}
    selected = combined_strict_names(base_names, include_qb=include_qb, include_snap=include_snap)
    return tuple(base_x) + tuple(vals[idx[n]] for n in selected[len(base_names):])



class LBFGSLogit:
    def __init__(self,names,means,scales,intercept,coefficients,l2,iterations,gradient_norm):
        self.names=tuple(names); self.means=list(means); self.scales=list(scales); self.intercept=float(intercept); self.coefficients=list(coefficients); self.l2=float(l2); self.iterations=int(iterations); self.gradient_norm=float(gradient_norm)
    def predict(self,x):
        import math, numpy as np
        a=np.asarray([np.nan if v is None else float(v) for v in x],dtype=float); means=np.asarray(self.means); scales=np.asarray(self.scales); a=np.where(np.isnan(a),means,a)
        z=self.intercept+float(np.dot(np.asarray(self.coefficients),(a-means)/scales)); z=max(-40.0,min(40.0,z)); return 1/(1+math.exp(-z))

def fit_lbfgs_logit(xs,ys,names,*,l2:float,max_iter:int=120,tolerance:float=2e-7,memory:int=10):
    """Deterministic NumPy L-BFGS for the same standardized L2 objective as Phase2C IRLS."""
    import math, numpy as np
    X=np.asarray([[np.nan if v is None else float(v) for v in row] for row in xs],dtype=float); y=np.asarray(ys,dtype=float)
    if X.ndim!=2 or X.shape[0]!=len(y) or X.shape[1]!=len(names): raise ValueError('bad design')
    valid=np.sum(~np.isnan(X),axis=0); sums=np.nansum(X,axis=0); means=np.divide(sums,valid,out=np.zeros_like(sums),where=valid>0); X=np.where(np.isnan(X),means,X)
    scales=np.std(X,axis=0); scales=np.where(scales>1e-12,scales,1.0); X=(X-means)/scales; n=float(len(y))
    ybar=float(np.clip(np.mean(y),1e-6,1-1e-6)); b=np.zeros(X.shape[1]+1,dtype=float); b[0]=math.log(ybar/(1-ybar))
    def fg(beta):
        z=np.clip(beta[0]+X@beta[1:],-40.0,40.0); pr=1/(1+np.exp(-z)); obj=float(np.mean(np.logaddexp(0,z)-y*z)+0.5*float(l2)*np.dot(beta[1:],beta[1:])); err=pr-y
        g=np.empty_like(beta); g[0]=np.mean(err); g[1:]=(X.T@err)/n+float(l2)*beta[1:]; return obj,g
    obj,g=fg(b); sh=[]; yh=[]; rh=[]; it=0
    for it in range(1,max_iter+1):
        gn=float(np.linalg.norm(g))
        if gn<tolerance: break
        q=g.copy(); al=[]
        for s0,y0,r0 in zip(reversed(sh),reversed(yh),reversed(rh)):
            a0=r0*float(np.dot(s0,q)); al.append(a0); q-=a0*y0
        gamma=1.0
        if sh:
            sy=float(np.dot(sh[-1],yh[-1])); yy=float(np.dot(yh[-1],yh[-1])); gamma=sy/yy if sy>0 and yy>0 else 1.0
        r=gamma*q
        for s0,y0,r0,a0 in zip(sh,yh,rh,reversed(al)):
            bb=r0*float(np.dot(y0,r)); r+=s0*(a0-bb)
        d=-r; gd=float(np.dot(g,d))
        if gd>=0: d=-g; gd=-float(np.dot(g,g))
        step=1.0; accepted=False
        for _ in range(28):
            nb=b+step*d; no,ng=fg(nb)
            if no<=obj+1e-4*step*gd:
                accepted=True; break
            step*=0.5
        if not accepted: break
        s0=nb-b; y0=ng-g; sy=float(np.dot(s0,y0)); b=nb; obj=no; g=ng
        if sy>1e-12:
            sh.append(s0); yh.append(y0); rh.append(1.0/sy)
            if len(sh)>memory: sh.pop(0); yh.pop(0); rh.pop(0)
    return LBFGSLogit(names,means.tolist(),scales.tolist(),b[0],b[1:].tolist(),l2,it,float(np.linalg.norm(g)))


class CompatibleFastLogit:
    def __init__(self, names, means, scales, intercept, coefficients):
        self.names=tuple(names); self.means=list(means); self.scales=list(scales); self.intercept=float(intercept); self.coefficients=list(coefficients)
    def predict(self, x):
        import math, numpy as np
        a=np.asarray([np.nan if v is None else float(v) for v in x],dtype=float)
        means=np.asarray(self.means); scales=np.asarray(self.scales); a=np.where(np.isnan(a),means,a)
        z=self.intercept+float(np.dot(np.asarray(self.coefficients),(a-means)/scales)); z=max(-40.0,min(40.0,z))
        return 1.0/(1.0+math.exp(-z))

def fit_phase2a_compatible_fast(xs, ys, names, *, l2: float, max_iter: int=140, learning_rate: float=.12, tolerance: float=2e-5):
    """Vectorized reproduction of Phase 2A's original deterministic gradient loop."""
    import math, numpy as np
    X=np.asarray([[np.nan if v is None else float(v) for v in row] for row in xs],dtype=float); y=np.asarray(ys,dtype=float)
    valid=np.sum(~np.isnan(X),axis=0); sums=np.nansum(X,axis=0); means=np.divide(sums,valid,out=np.zeros_like(sums),where=valid>0)
    X=np.where(np.isnan(X),means,X); scales=np.std(X,axis=0); scales=np.where(scales>1e-12,scales,1.0); X=(X-means)/scales
    ybar=float(np.clip(np.mean(y),1e-6,1-1e-6)); intercept=math.log(ybar/(1-ybar)); w=np.zeros(X.shape[1],dtype=float); n=float(len(y))
    for it in range(1,max_iter+1):
        z=np.clip(intercept+X@w,-40.0,40.0); pr=1.0/(1.0+np.exp(-z)); err=pr-y
        gi=float(np.sum(err)/n); gw=(X.T@err)/n+float(l2)*w; grad_norm=math.sqrt(gi*gi+float(np.dot(gw,gw)))
        if grad_norm<tolerance: break
        step=learning_rate/math.sqrt(1.0+(it-1)/75.0); intercept-=step*gi; w-=step*gw
    return CompatibleFastLogit(names,means.tolist(),scales.tolist(),intercept,w.tolist())

def clip_prob(p: float) -> float:
    return min(1.0 - 1e-12, max(1e-12, float(p)))


def calibration_intercept_slope(ys: Sequence[int], ps: Sequence[float]) -> dict[str, float]:
    """Diagnostic logistic recalibration fit y ~ a + b*logit(p)."""
    import numpy as np
    if not ys or len(ys) != len(ps):
        raise ValueError("paired y/p required")
    x = np.asarray([log(clip_prob(p) / (1.0 - clip_prob(p))) for p in ps], dtype=float)
    y = np.asarray(ys, dtype=float)
    X = np.column_stack([np.ones(len(x)), x]); beta = np.array([0.0, 1.0], dtype=float)
    for _ in range(80):
        z = np.clip(X @ beta, -40.0, 40.0); pr = 1.0 / (1.0 + np.exp(-z)); w = np.maximum(pr * (1-pr), 1e-8)
        grad = X.T @ (pr-y); hess = X.T @ (X * w[:, None]) + np.eye(2) * 1e-10
        step = np.linalg.solve(hess, grad); beta2 = beta - step
        if float(np.linalg.norm(step)) < 1e-9:
            beta = beta2; break
        beta = beta2
    return {"intercept": float(beta[0]), "slope": float(beta[1])}


def brier_decomposition(ys: Sequence[int], ps: Sequence[float], bins: int = 10) -> dict[str, float]:
    """Approximate Murphy decomposition using deterministic equal-count bins."""
    if not ys or len(ys) != len(ps) or bins < 2:
        raise ValueError("bad Brier decomposition input")
    pairs = sorted((float(p), int(y)) for y, p in zip(ys, ps)); n = len(pairs); overall = fmean(y for _, y in pairs)
    reliability = resolution = 0.0
    for b in range(bins):
        lo = (b*n)//bins; hi = ((b+1)*n)//bins; bucket = pairs[lo:hi]
        if not bucket: continue
        pk = fmean(p for p, _ in bucket); ok = fmean(y for _, y in bucket); wk = len(bucket)/n
        reliability += wk * (pk-ok)**2; resolution += wk * (ok-overall)**2
    uncertainty = overall * (1-overall)
    return {"reliability": reliability, "resolution": resolution, "uncertainty": uncertainty,
            "reconstructedBrier": reliability - resolution + uncertainty}


def paired_block_bootstrap(records: Sequence[dict[str, Any]], *, reps: int = 5000, seed: int = 29004) -> dict[str, Any]:
    """Stratified season-week block bootstrap of base-minus-challenger loss."""
    import numpy as np
    if not records:
        raise ValueError("no records")
    seasons: dict[int, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        seasons[int(r["season"])][int(r["week"])].append(r)
    rng = np.random.default_rng(seed); bd = []; ld = []
    for _ in range(reps):
        sample = []
        for season in sorted(seasons):
            weeks = sorted(seasons[season]); picks = rng.choice(weeks, size=len(weeks), replace=True)
            for w in picks:
                sample.extend(seasons[season][int(w)])
        bd.append(fmean(float(r["base_brier_loss"]) - float(r["challenger_brier_loss"]) for r in sample))
        ld.append(fmean(float(r["base_log_loss"]) - float(r["challenger_log_loss"]) for r in sample))
    def summarize(v):
        a = np.asarray(v, dtype=float)
        return {"mean": float(np.mean(a)), "ci95Low": float(np.quantile(a, .025)), "ci95High": float(np.quantile(a, .975)),
                "positiveFraction": float(np.mean(a > 0))}
    return {"reps": reps, "seed": seed, "block": "SEASON_WEEK_STRATIFIED", "brierImprovement": summarize(bd), "logLossImprovement": summarize(ld)}


def model_metrics(rm, records: Sequence[dict[str, Any]], p_field: str) -> dict[str, Any]:
    ys = [int(r["y"]) for r in records]; ps = [float(r[p_field]) for r in records]
    m = dict(rm.metric_summary(ys, ps)); m["calibration"] = calibration_intercept_slope(ys, ps); m["brierDecomposition"] = brier_decomposition(ys, ps)
    return m


def loss_record(y: int, p_base: float, p_challenger: float) -> dict[str, float]:
    pb = clip_prob(p_base); pc = clip_prob(p_challenger); y = int(y)
    return {
        "base_brier_loss": (pb-y)**2, "challenger_brier_loss": (pc-y)**2,
        "base_log_loss": -(y*log(pb)+(1-y)*log(1-pb)),
        "challenger_log_loss": -(y*log(pc)+(1-y)*log(1-pc)),
    }


def select_columns(names: Sequence[str], vectors: Sequence[Sequence[float | None]], keep: Callable[[str], bool]) -> tuple[tuple[str, ...], list[tuple[float | None, ...]]]:
    idx = [i for i, n in enumerate(names) if keep(n)]
    return tuple(names[i] for i in idx), [tuple(row[i] for i in idx) for row in vectors]

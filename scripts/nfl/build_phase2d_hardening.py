#!/usr/bin/env python3
"""Phase 2D.2 pre-holdout hardening: base-API compatibility + solver-controlled comparisons."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from math import log
import argparse, csv, hashlib, json, os, shutil, sys


def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def readcsv(p):
    with Path(p).open(newline="", encoding="utf-8") as f: return list(csv.DictReader(f))
def writecsv(p, rows):
    p=Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with p.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n"); w.writeheader(); w.writerows(rows)
def canon(x): return (json.dumps(x,sort_keys=True,separators=(",",":"))+"\n").encode()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); ap.add_argument("--bootstrap-reps",type=int,default=5000); a=ap.parse_args()
    root=Path(a.root).expanduser().resolve(); sys.path.insert(0,str(root/"packages/models/nfl/game"))
    import research_model as rm
    import phase2c_model as pm
    import phase2d_hardening as hd

    sid=(root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT").read_text().strip()
    for ptr in (root/"data/normalized/nfl/CURRENT_PHASE2C_CONTEXT",root/"data/normalized/nfl/CURRENT_PHASE2D_SAFE_CONTEXT"):
        if not ptr.exists() or ptr.read_text().strip()!=sid: raise SystemExit(f"FAIL snapshot pointer mismatch: {ptr}")
    cdir=root/"data/normalized/nfl/phase2c_context"/sid; sdir=root/"data/normalized/nfl/phase2d_safe_context"/sid
    full_rows=readcsv(cdir/"phase2c_features.csv"); safe_rows=readcsv(sdir/"phase2d_safe_features.csv")
    if any(int(r["season"])>=2025 for r in full_rows+safe_rows): raise SystemExit("FAIL 2025 feature row admitted")
    full_by={r["game_id"]:r for r in full_rows}; safe_by={r["game_id"]:r for r in safe_rows}

    labels={}
    with (root/"data/normalized/nfl/phase1"/sid/"game_targets.csv").open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            season=int(r["game_id"][:4])
            if season>=2025: continue
            if r.get("home_win") in ("0","0.0","1","1.0"): labels[r["game_id"]]=int(float(r["home_win"]))
    allowed=set(range(2016,2025)); ex=rm.examples_from_rows(full_rows,labels,allowed_seasons=allowed,game_type="REG")
    if len(ex)<2000: raise SystemExit(f"FAIL small development sample {len(ex)}")
    if {e.game_id for e in ex}-{*safe_by}: raise SystemExit("FAIL safe context missing development game")

    p2a=json.loads((root/"data/models/nfl/phase2a"/sid/"DEVELOPMENT_VALIDATION_REPORT.json").read_text())
    p2c=json.loads((root/"data/models/nfl/phase2c"/sid/"PHASE2C_BAKEOFF.json").read_text())
    if p2a["integrity"]["holdoutEvaluated"] or p2c["integrity"]["holdoutEvaluated"]: raise SystemExit("FAIL prior holdout boundary")
    if int(p2a["integrity"]["holdoutLabelsAdmitted"]) or int(p2c["integrity"]["holdoutLabelsAdmitted"]): raise SystemExit("FAIL prior holdout labels admitted")
    base_l2=float(p2a["selectedModel"]["walkForward"]["selectedL2"])
    base_report=next(x for x in p2a["selectedModel"]["walkForward"]["candidates"] if float(x["l2"])==base_l2)["pooled"]
    p2c_full_report=p2c["metrics"]["team_plus_qb_roster"]

    base_names=rm.expanded_feature_names(); selection=(2020,2021); evaluation=(2022,2023,2024)
    l2_grid=(0.03,0.1,0.3,1.0,3.0,10.0)

    def full_design(e): return pm.combined_vector(e.x,full_by[e.game_id],base_names,include_qb=True,include_roster=True)
    full_names=pm.combined_names(base_names,include_qb=True,include_roster=True)
    def safe_design(e): return hd.combined_strict_vector(e.x,safe_by[e.game_id],base_names,include_qb=True,include_snap=True)
    safe_names=hd.combined_strict_names(base_names,include_qb=True,include_snap=True)

    context_configs=("full_targetweek","strict_lag","no_turnover","no_rush_epa","no_last4","no_qb_change_proxy")
    solver_base="solver_controlled_base"

    # Precompute every design vector once. Re-vectorizing hundreds of thousands of
    # rows inside regularization loops is pure Python overhead and can dominate build time.
    full_vectors={e.game_id:full_design(e) for e in ex}
    safe_vectors={e.game_id:safe_design(e) for e in ex}
    names_by={"full_targetweek":full_names,"strict_lag":safe_names,solver_base:tuple(base_names)}
    designs={"full_targetweek":full_vectors,"strict_lag":safe_vectors,solver_base:{e.game_id:tuple(e.x) for e in ex}}
    predicates={
        "no_turnover":lambda n:not any(s in n for s in ("off_turnover_rate","def_takeaway_rate","qb_int_rate")),
        "no_rush_epa":lambda n:not any(s in n for s in ("off_rush_epa","def_rush_epa_allowed")),
        "no_last4":lambda n:"last4_" not in n,
        "no_qb_change_proxy":lambda n:"qb_change_proxy" not in n,
    }
    for name,keep in predicates.items():
        idx=[i for i,n in enumerate(full_names) if keep(n)]
        names_by[name]=tuple(full_names[i] for i in idx)
        designs[name]={gid:tuple(v[i] for i in idx) for gid,v in full_vectors.items()}

    reg={}; selected={}
    # Solver-controlled base and every context challenger use the exact same Phase2C
    # deterministic IRLS fitter. This isolates feature value from optimizer changes.
    for name in (solver_base,)+context_configs:
        names=names_by[name]; dv=designs[name]; candidates=[]
        for lam in l2_grid:
            yy=[]; pp=[]; folds=[]
            for season in selection:
                train=[e for e in ex if e.season<season]; test=[e for e in ex if e.season==season]
                model=pm.fit_fast_logit([dv[e.game_id] for e in train],[e.y for e in train],names,l2=lam)
                ps=[model.predict(dv[e.game_id]) for e in test]; ys=[e.y for e in test]; m=rm.metric_summary(ys,ps)
                folds.append({"season":season,**m}); yy+=ys; pp+=ps
            candidates.append({"l2":lam,"pooled":rm.metric_summary(yy,pp),"folds":folds})
        candidates.sort(key=lambda x:(x["pooled"]["logLoss"],x["pooled"]["brier"],-x["l2"]))
        reg[name]=candidates; selected[name]=float(candidates[0]["l2"])

    # Reproduce the historical Phase2A OOF predictions with the original fitter itself.
    # Do not use a vectorized numerical approximation for an "exact" parity gate.
    pred_base={}
    for season in evaluation:
        train=[e for e in ex if e.season<season]; test=[e for e in ex if e.season==season]
        model=rm.fit_logistic(train,l2=base_l2)
        for e in test: pred_base[e.game_id]=model.predict_proba(e.x)
    base_eval=[e for e in ex if e.season in evaluation]
    exact_base=rm.metric_summary([e.y for e in base_eval],[pred_base[e.game_id] for e in base_eval])
    for k in ("brier","logLoss","accuracy"):
        if abs(float(exact_base[k])-float(base_report[k]))>1e-10: raise SystemExit(f"FAIL exact Phase2A prediction parity {k}: {exact_base[k]} vs {base_report[k]}")

    preds={}
    for name in (solver_base,)+context_configs:
        names=names_by[name]; dv=designs[name]; lam=selected[name]; p={}
        for season in evaluation:
            train=[e for e in ex if e.season<season]; test=[e for e in ex if e.season==season]
            model=pm.fit_fast_logit([dv[e.game_id] for e in train],[e.y for e in train],names,l2=lam)
            for e in test: p[e.game_id]=model.predict(dv[e.game_id])
        preds[name]=p

    # Verify Phase2C full challenger reproduction when its original selected lambda remains selected.
    p2c_l2=float(p2c["regularization"]["selectedByModel"]["team_plus_qb_roster"])
    if selected["full_targetweek"]==p2c_l2:
        m=rm.metric_summary([e.y for e in base_eval],[preds["full_targetweek"][e.game_id] for e in base_eval])
        for k in ("brier","logLoss","accuracy"):
            if abs(float(m[k])-float(p2c_full_report[k]))>1e-10: raise SystemExit(f"FAIL exact Phase2C reproduction parity {k}: {m[k]} vs {p2c_full_report[k]}")

    ledger=[]
    for e in base_eval:
        r={"game_id":e.game_id,"season":e.season,"week":e.week,"home_team":e.home_team,"away_team":e.away_team,"y":e.y,"p_phase2a_base":pred_base[e.game_id],"p_base":pred_base[e.game_id],"p_solver_controlled_base":preds[solver_base][e.game_id]}
        for name in context_configs: r["p_"+name]=preds[name][e.game_id]
        fr=full_by[e.game_id]
        r["any_qb_change_proxy"]=1 if any(float(fr.get(f"{s}_qb_change_proxy") or 0)==1 for s in ("home","away")) else 0
        r["any_qb_unresolved"]=1 if any(float(fr.get(f"{s}_qb_unresolved") or 0)==1 for s in ("home","away")) else 0
        vals=[]
        for s in ("home","away"):
            try: vals.append(float(fr.get(f"{s}_active_roster_return_rate")))
            except (TypeError,ValueError): pass
        r["mean_active_roster_return_rate"]=sum(vals)/len(vals) if vals else ""
        ledger.append(r)

    metrics={"phase2a_base":hd.model_metrics(rm,ledger,"p_phase2a_base"),"solver_controlled_base":hd.model_metrics(rm,ledger,"p_solver_controlled_base")}
    for name in context_configs: metrics[name]=hd.model_metrics(rm,ledger,"p_"+name)
    improvements_vs_phase2a={name:{"brier":metrics["phase2a_base"]["brier"]-metrics[name]["brier"],"logLoss":metrics["phase2a_base"]["logLoss"]-metrics[name]["logLoss"],"accuracy":metrics[name]["accuracy"]-metrics["phase2a_base"]["accuracy"]} for name in (solver_base,)+context_configs}
    improvements_vs_solver={name:{"brier":metrics["solver_controlled_base"]["brier"]-metrics[name]["brier"],"logLoss":metrics["solver_controlled_base"]["logLoss"]-metrics[name]["logLoss"],"accuracy":metrics[name]["accuracy"]-metrics["solver_controlled_base"]["accuracy"]} for name in context_configs}
    ablation_delta_vs_full={name:{"brier":metrics["full_targetweek"]["brier"]-metrics[name]["brier"],"logLoss":metrics["full_targetweek"]["logLoss"]-metrics[name]["logLoss"]} for name in ("no_turnover","no_rush_epa","no_last4","no_qb_change_proxy")}

    # Bootstrap feature value against a solver-controlled base. Historical Phase2A
    # comparisons are retained separately for continuity, but promotion logic must not
    # mistake a solver improvement for a feature improvement.
    boot={}
    for name in ("full_targetweek","strict_lag"):
        rec=[]
        for r in ledger:
            lr={"season":r["season"],"week":r["week"]}; lr.update(hd.loss_record(int(r["y"]),float(r["p_solver_controlled_base"]),float(r["p_"+name]))); rec.append(lr)
        boot["solver_controlled_base_vs_"+name]=hd.paired_block_bootstrap(rec,reps=a.bootstrap_reps,seed=29004+(0 if name=="full_targetweek" else 1))
        rec2=[]
        for r in ledger:
            lr={"season":r["season"],"week":r["week"]}; lr.update(hd.loss_record(int(r["y"]),float(r["p_phase2a_base"]),float(r["p_"+name]))); rec2.append(lr)
        boot["phase2a_base_vs_"+name]=hd.paired_block_bootstrap(rec2,reps=a.bootstrap_reps,seed=29104+(0 if name=="full_targetweek" else 1))
    rec=[]
    for r in ledger:
        lr={"season":r["season"],"week":r["week"]}; lr.update(hd.loss_record(int(r["y"]),float(r["p_strict_lag"]),float(r["p_full_targetweek"]))); rec.append(lr)
    boot["strict_lag_vs_full_targetweek"]=hd.paired_block_bootstrap(rec,reps=a.bootstrap_reps,seed=29006)

    def subgroup(label,pred):
        if not pred: return {"n":0}
        rr=[r for r in ledger if pred(r)]
        if not rr: return {"n":0}
        out={"n":len(rr)}
        for model,field in (("phase2a","p_phase2a_base"),("solver_base","p_solver_controlled_base"),("full","p_full_targetweek"),("strict","p_strict_lag")):
            out[model]=rm.metric_summary([int(r["y"]) for r in rr],[float(r[field]) for r in rr])
        return out
    rrates=sorted(float(r["mean_active_roster_return_rate"]) for r in ledger if r["mean_active_roster_return_rate"]!="")
    q25=rrates[int(.25*(len(rrates)-1))] if rrates else None; q75=rrates[int(.75*(len(rrates)-1))] if rrates else None
    groups={
        "week1":subgroup("week1",lambda r:int(r["week"])==1),
        "weeks1to4":subgroup("weeks1to4",lambda r:1<=int(r["week"])<=4),
        "week5plus":subgroup("week5plus",lambda r:int(r["week"])>=5),
        "any_qb_change_proxy":subgroup("any_qb_change_proxy",lambda r:int(r["any_qb_change_proxy"])==1),
        "any_qb_unresolved":subgroup("any_qb_unresolved",lambda r:int(r["any_qb_unresolved"])==1),
    }
    if q25 is not None:
        groups["low_roster_return_q25"]=subgroup("low",lambda r:r["mean_active_roster_return_rate"]!="" and float(r["mean_active_roster_return_rate"])<=q25)
        groups["high_roster_return_q75"]=subgroup("high",lambda r:r["mean_active_roster_return_rate"]!="" and float(r["mean_active_roster_return_rate"])>=q75)

    # Year stability.
    folds={}
    for season in evaluation:
        rr=[r for r in ledger if int(r["season"])==season]; folds[str(season)]={}
        for model,field in (("phase2a_base","p_phase2a_base"),("solver_controlled_base","p_solver_controlled_base"),("full_targetweek","p_full_targetweek"),("strict_lag","p_strict_lag")):
            folds[str(season)][model]=rm.metric_summary([int(r["y"]) for r in rr],[float(r[field]) for r in rr])

    ranked=sorted((solver_base,)+context_configs,key=lambda n:(metrics[n]["logLoss"],metrics[n]["brier"],-metrics[n]["accuracy"],n)); best=ranked[0]
    names=names_by[best]; dv=designs[best]; final=pm.fit_fast_logit([dv[e.game_id] for e in ex],[e.y for e in ex],names,l2=selected[best])
    coeff=sorted(({"feature":n,"coefficient":float(c),"abs":abs(float(c))} for n,c in zip(names,final.coefficients)),key=lambda x:(-x["abs"],x["feature"]))[:35]

    full_ci=boot["solver_controlled_base_vs_full_targetweek"]; safe_ci=boot["solver_controlled_base_vs_strict_lag"]
    robust_full=full_ci["brierImprovement"]["ci95Low"]>0 and full_ci["logLossImprovement"]["ci95Low"]>0
    robust_safe=safe_ci["brierImprovement"]["ci95Low"]>0 and safe_ci["logLossImprovement"]["ci95Low"]>0
    source_gate="WEEKLY_ROSTER_EXACT_PREGAME_TIMESTAMP_NOT_PROVEN_FOR_FULL_TARGETWEEK"
    strict_gate="STRICT_LAG_TEMPORAL_PROVENANCE_PASS"
    verdict="REVIEW_BEFORE_FREEZE_2025_REMAINS_SEALED"

    report={"reportVersion":"0.4.1","generatedAt":now(),"sourceSnapshotId":sid,"integrity":{"holdoutEvaluated":False,"holdoutLabelsAdmitted":0,"holdoutRowsRead":0,"marketFieldsAllowed":False,"oddsPapiRequests":0,"pairedEvaluationGames":len(ledger)},
        "regularization":{"selectionFolds":list(selection),"evaluationFolds":list(evaluation),"grid":list(l2_grid),"selected":selected,"search":reg},
        "metrics":metrics,"improvementsVsExactPhase2ABase":improvements_vs_phase2a,"improvementsVsSolverControlledBase":improvements_vs_solver,"yearMetrics":folds,"bootstrap":boot,"subgroups":groups,"rosterReturnQuantiles":{"q25":q25,"q75":q75},
        "ablations":{"noTurnover":metrics["no_turnover"],"noRushEpa":metrics["no_rush_epa"],"noLast4":metrics["no_last4"],"noQbChangeProxy":metrics["no_qb_change_proxy"],"deltaVsFullTargetWeek":ablation_delta_vs_full},
        "bestDevelopmentChallenger":best,"robustFullTargetWeek":robust_full,"robustStrictLag":robust_safe,"sourceTimingGate":source_gate,"strictLagTimingGate":strict_gate,"freezeVerdict":verdict,"topStandardizedCoefficients":coeff,
        "notes":["2022-2024 remain development folds, not a final holdout.","Historical Phase2A parity is regenerated with the original Phase2A fitter.","Feature promotion comparisons use a solver-controlled base fit with the same Phase2C IRLS algorithm and L2 selection discipline as context challengers.","Bootstrap resamples season-week blocks and compares paired per-game proper-score losses.","Calibration intercept/slope are diagnostics only and are not applied to probabilities.","Strict-lag challenger never reads target-week roster state.","Market comparison remains physically downstream; this build fits no market-derived feature."]}
    spec={"phase":"NFL_2.9.0_PHASE2D2","status":"PREHOLDOUT_HARDENING_NOT_PRODUCTION","sourceSnapshotId":sid,"holdoutSeason":2025,"holdoutEvaluated":False,"marketFieldsAllowed":False,"selectionFolds":list(selection),"evaluationFolds":list(evaluation),"l2Grid":list(l2_grid),"featureLineage":hd.LINEAGE,"sourceTimingGate":source_gate,"strictLagTimingGate":strict_gate,"freezeVerdict":verdict}
    specsha=hashlib.sha256(canon(spec)).hexdigest()

    out=root/"data/models/nfl/phase2d"/sid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable Phase2D output: {out}")
    st=out.parent/("."+sid+".staging"); st.mkdir(parents=True,exist_ok=False)
    try:
        writecsv(st/"PHASE2D_OOF_LEDGER.csv",ledger)
        (st/"PHASE2D_HARDENING.json").write_text(json.dumps(report,indent=2)+"\n")
        (st/"PHASE2D_SPEC.json").write_bytes(canon(spec)); (st/"PHASE2D_SPEC.sha256").write_text(specsha+"  PHASE2D_SPEC.json\n")
        md=["# MODEL NFL 2.9.0 Phase 2D.2 — Base API Compatibility + Solver-Control Hardening","","**2025 HOLDOUT REMAINS SEALED. NOT PRODUCTION.**","",f"Source snapshot: `{sid}`","",
            "## Main paired performance (2022–2024)","","| Model | N | Brier | Log loss | Accuracy | Cal intercept | Cal slope |","|---|---:|---:|---:|---:|---:|---:|"]
        for n in ("phase2a_base","solver_controlled_base","full_targetweek","strict_lag","no_turnover","no_rush_epa","no_last4","no_qb_change_proxy"):
            m=metrics[n]; c=m["calibration"]; md.append(f"| {n} | {m['n']} | {m['brier']:.5f} | {m['logLoss']:.5f} | {m['accuracy']:.3f} | {c['intercept']:+.3f} | {c['slope']:.3f} |")
        md += ["","## Solver-control gate","","The historical Phase2A baseline is preserved for continuity, but feature-addition claims are judged against `solver_controlled_base`, which uses the same IRLS fitter and 2020–2021 L2-selection process as the context challengers.","",f"- Historical Phase2A Brier: **{metrics['phase2a_base']['brier']:.5f}** · solver-controlled base: **{metrics['solver_controlled_base']['brier']:.5f}**.",f"- Historical Phase2A log loss: **{metrics['phase2a_base']['logLoss']:.5f}** · solver-controlled base: **{metrics['solver_controlled_base']['logLoss']:.5f}**.","","## Paired season-week block bootstrap vs solver-controlled base","",f"- Full target-week — Brier Δ **{full_ci['brierImprovement']['mean']:+.5f}** (95% CI {full_ci['brierImprovement']['ci95Low']:+.5f} to {full_ci['brierImprovement']['ci95High']:+.5f}); log-loss Δ **{full_ci['logLossImprovement']['mean']:+.5f}** (95% CI {full_ci['logLossImprovement']['ci95Low']:+.5f} to {full_ci['logLossImprovement']['ci95High']:+.5f}).",f"- Strict-lag — Brier Δ **{safe_ci['brierImprovement']['mean']:+.5f}** (95% CI {safe_ci['brierImprovement']['ci95Low']:+.5f} to {safe_ci['brierImprovement']['ci95High']:+.5f}); log-loss Δ **{safe_ci['logLossImprovement']['mean']:+.5f}** (95% CI {safe_ci['logLossImprovement']['ci95Low']:+.5f} to {safe_ci['logLossImprovement']['ci95High']:+.5f}).",f"- Robust full target-week feature improvement: **{str(robust_full).upper()}**",f"- Robust strict-lag feature improvement: **{str(robust_safe).upper()}**","",
            "## Year-by-year","","| Season | Phase2A Brier | Solver-base Brier | Full Brier | Strict Brier | Phase2A LL | Solver-base LL | Full LL | Strict LL |","|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for s in evaluation:
            x=folds[str(s)]; md.append(f"| {s} | {x['phase2a_base']['brier']:.5f} | {x['solver_controlled_base']['brier']:.5f} | {x['full_targetweek']['brier']:.5f} | {x['strict_lag']['brier']:.5f} | {x['phase2a_base']['logLoss']:.5f} | {x['solver_controlled_base']['logLoss']:.5f} | {x['full_targetweek']['logLoss']:.5f} | {x['strict_lag']['logLoss']:.5f} |")
        md += ["","## Ablation questions","",f"- Remove turnover/takeaway/QB-INT features: Brier **{metrics['no_turnover']['brier']:.5f}**, log loss **{metrics['no_turnover']['logLoss']:.5f}**.",f"- Remove rushing-EPA features: Brier **{metrics['no_rush_epa']['brier']:.5f}**, log loss **{metrics['no_rush_epa']['logLoss']:.5f}**.",f"- Remove all last-4 features: Brier **{metrics['no_last4']['brier']:.5f}**, log loss **{metrics['no_last4']['logLoss']:.5f}**.",f"- Remove QB-change-proxy features: Brier **{metrics['no_qb_change_proxy']['brier']:.5f}**, log loss **{metrics['no_qb_change_proxy']['logLoss']:.5f}**.","",
            "## Temporal provenance","",f"- Full target-week context: **{source_gate}**",f"- Strict-lag challenger: **{strict_gate}**","- Strict-lag QB uses only the previous observed primary QB; it cannot know a target-week starter change.","- Strict-lag personnel continuity measures G-2 → G-1 snap retention and never reads the target-week roster.","",
            "## Subgroup diagnostics","", "These are diagnostics, not separately tuned betting systems.",""]
        for key in ("week1","weeks1to4","week5plus","any_qb_change_proxy","any_qb_unresolved","low_roster_return_q25","high_roster_return_q75"):
            if key in groups and groups[key].get("n",0):
                g=groups[key]; md.append(f"- `{key}` N={g['n']} · Phase2A {g['phase2a']['brier']:.5f} · solver-base {g['solver_base']['brier']:.5f} · full {g['full']['brier']:.5f} · strict {g['strict']['brier']:.5f}")
        md += ["",f"## Top standardized coefficients — `{best}`",""]
        for c in coeff[:18]: md.append(f"- `{c['feature']}`: {c['coefficient']:+.4f}")
        md += ["","## Integrity / next gate","","- 2025 labels admitted: **0**","- 2025 evaluated: **NO**","- Sportsbook/market fields in fitter: **DISALLOWED**","- OddsPapi requests: **0**",f"- Freeze verdict: **{verdict}**","","Do **not** open 2025 until this report is reviewed and a feature/source specification is explicitly frozen.",""]
        (st/"PHASE2D_HARDENING.md").write_text("\n".join(md))
        edge=["# NFL Market Edge Readiness — Phase 2D.2","","No market result is used to fit or select the independent model in Phase 2D.","","The build now persists an immutable 2022–2024 OOF probability ledger. Once the independent candidate is frozen and 2025 is evaluated once, live market comparison can remain downstream:","","`independent P(win) -> sharp two-way no-vig probability -> probability edge -> executable EV -> Trust gates`","","The included `market_edge.py` implements only downstream odds conversion, no-vig normalization, and EV math. It is intentionally not imported by the model fitter.","","For live 2026 deployment, market joins should use canonical NFL game identity, current Pinnacle/Circa sharp consensus when available, FanDuel executable price, freshness, verified starting QB, availability/inactive state, and model uncertainty. A large model-market disagreement is an investigation trigger until Trust gates pass.","","Actual market-edge backtesting is **not run here**; doing so before the independent feature specification is frozen would encourage market-aware model tuning.",""]
        (st/"EDGE_READINESS.md").write_text("\n".join(edge))
        os.replace(st,out); (root/"data/models/nfl/CURRENT_PHASE2D").write_text(sid+"\n")
    except Exception:
        shutil.rmtree(st,ignore_errors=True); raise
    print("MODEL NFL 2.9.0 PHASE 2D.2 — BASE API COMPAT + SOLVER-CONTROL HARDENING")
    print(f"PASS exact paired evaluation games: {len(ledger)}")
    print(f"PASS exact Phase2A parity via original fitter · Brier {metrics['phase2a_base']['brier']:.8f}")
    print(f"PASS solver-controlled base λ: {selected[solver_base]:g}")
    print(f"PASS expanded L2 search: {l2_grid} · selection 2020-2021 only")
    print(f"PASS full target-week λ: {selected['full_targetweek']:g} · strict-lag λ: {selected['strict_lag']:g}")
    print(f"PASS full bootstrap robust: {robust_full} · strict-lag robust: {robust_safe}")
    print("PASS OOF ledger persisted · 2022-2024 development only")
    print("PASS 2025 holdout: NOT READ / NOT EVALUATED / 0 labels admitted")
    print("PASS market fields disallowed · OddsPapi requests 0")
    print(f"REPORT: {out/'PHASE2D_HARDENING.md'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

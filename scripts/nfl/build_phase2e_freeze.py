#!/usr/bin/env python3
"""Build NFL Phase 2E safe freeze candidate. 2025 is never read/evaluated."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
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
    import phase2e_freeze as pe

    sid=(root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT").read_text().strip()
    required_ptrs=(
        root/"data/normalized/nfl/CURRENT_PHASE2C_CONTEXT",
        root/"data/normalized/nfl/CURRENT_PHASE2D_SAFE_CONTEXT",
        root/"data/models/nfl/CURRENT_PHASE2D",
    )
    for ptr in required_ptrs:
        if not ptr.exists() or ptr.read_text().strip()!=sid: raise SystemExit(f"FAIL snapshot pointer mismatch: {ptr}")

    p2d_dir=root/"data/models/nfl/phase2d"/sid
    p2d=json.loads((p2d_dir/"PHASE2D_HARDENING.json").read_text())
    if p2d["integrity"]["holdoutEvaluated"] or int(p2d["integrity"]["holdoutLabelsAdmitted"]): raise SystemExit("FAIL Phase2D holdout boundary")
    if p2d["integrity"]["marketFieldsAllowed"] or int(p2d["integrity"]["oddsPapiRequests"]): raise SystemExit("FAIL Phase2D market isolation")
    d2ledger=readcsv(p2d_dir/"PHASE2D_OOF_LEDGER.csv")
    if any(int(r["season"])>=2025 for r in d2ledger): raise SystemExit("FAIL 2025 row in Phase2D ledger")

    cdir=root/"data/normalized/nfl/phase2c_context"/sid; sdir=root/"data/normalized/nfl/phase2d_safe_context"/sid
    full_rows=readcsv(cdir/"phase2c_features.csv"); safe_rows=readcsv(sdir/"phase2d_safe_features.csv")
    if any(int(r["season"])>=2025 for r in full_rows+safe_rows): raise SystemExit("FAIL 2025 context row admitted")
    full_by={r["game_id"]:r for r in full_rows}; safe_by={r["game_id"]:r for r in safe_rows}

    labels={}
    with (root/"data/normalized/nfl/phase1"/sid/"game_targets.csv").open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            season=int(r["game_id"][:4])
            if season>=2025: continue
            if r.get("home_win") in ("0","0.0","1","1.0"): labels[r["game_id"]]=int(float(r["home_win"]))
    allowed=set(range(2016,2025)); ex=rm.examples_from_rows(full_rows,labels,allowed_seasons=allowed,game_type="REG")
    if len(ex)<2000: raise SystemExit(f"FAIL small development sample {len(ex)}")
    if {e.game_id for e in ex}-{*safe_by}: raise SystemExit("FAIL strict context missing development game")

    base_names=rm.expanded_feature_names()
    full_names=pm.combined_names(base_names,include_qb=True,include_roster=True)
    safe_names=hd.combined_strict_names(base_names,include_qb=True,include_snap=True)
    full_raw={e.game_id:pm.combined_vector(e.x,full_by[e.game_id],base_names,include_qb=True,include_roster=True) for e in ex}
    safe_raw={e.game_id:hd.combined_strict_vector(e.x,safe_by[e.game_id],base_names,include_qb=True,include_snap=True) for e in ex}
    base_vectors={e.game_id:tuple(e.x) for e in ex}

    # Preserve the solver-controlled base lambda chosen before this phase.
    base_l2=float(p2d["regularization"]["selected"]["solver_controlled_base"])
    selection=pe.SELECTION_SEASONS; evaluation=pe.EVALUATION_SEASONS

    variants={}; names_by={}; designs={}
    for prefix,names,raw in (("safe",safe_names,safe_raw),("full",full_names,full_raw)):
        for no_to in (False,True):
            for no_rush in (False,True):
                name=pe.variant_name(prefix,no_to,no_rush)
                idx=[i for i,n in enumerate(names) if pe.candidate_keep(n,no_turnover=no_to,no_rush_epa=no_rush)]
                names_by[name]=tuple(names[i] for i in idx)
                designs[name]={gid:tuple(v[i] for i in idx) for gid,v in raw.items()}
                variants[name]={"prefix":prefix,"noTurnover":no_to,"noRushEpa":no_rush,"featureCount":len(idx)}

    # Candidate L2 selection is made entirely on 2018-2021 OOF scores.
    reg={}; selected={}; selection_preds={}
    for name in variants:
        candidates=[]
        for lam in pe.L2_GRID:
            ys=[]; ps=[]; folds=[]
            for season in selection:
                train=[e for e in ex if e.season<season]; test=[e for e in ex if e.season==season]
                m=pm.fit_fast_logit([designs[name][e.game_id] for e in train],[e.y for e in train],names_by[name],l2=lam)
                p=[m.predict(designs[name][e.game_id]) for e in test]; y=[e.y for e in test]
                folds.append({"season":season,**rm.metric_summary(y,p)}); ys+=y; ps+=p
            candidates.append({"l2":lam,"pooled":rm.metric_summary(ys,ps),"folds":folds})
        candidates.sort(key=lambda x:(x["pooled"]["logLoss"],x["pooled"]["brier"],-x["l2"]))
        reg[name]=candidates; selected[name]=float(candidates[0]["l2"])

        pmap={}
        lam=selected[name]
        for season in selection:
            train=[e for e in ex if e.season<season]; test=[e for e in ex if e.season==season]
            m=pm.fit_fast_logit([designs[name][e.game_id] for e in train],[e.y for e in train],names_by[name],l2=lam)
            for e in test: pmap[e.game_id]=m.predict(designs[name][e.game_id])
        selection_preds[name]=pmap

    # Choose one SAFE and one provenance-gated FULL variant using selection years only.
    def selection_metric(name):
        rows=[e for e in ex if e.season in selection]
        return rm.metric_summary([e.y for e in rows],[selection_preds[name][e.game_id] for e in rows])
    sel_metrics={n:selection_metric(n) for n in variants}
    safe_candidates=[n for n in variants if variants[n]["prefix"]=="safe"]
    full_candidates=[n for n in variants if variants[n]["prefix"]=="full"]
    safe_candidates.sort(key=lambda n:(sel_metrics[n]["logLoss"],sel_metrics[n]["brier"],variants[n]["featureCount"]))
    full_candidates.sort(key=lambda n:(sel_metrics[n]["logLoss"],sel_metrics[n]["brier"],variants[n]["featureCount"]))
    selected_safe=safe_candidates[0]; selected_full=full_candidates[0]

    # Fixed-lambda solver base OOF on selection years for stage-weight selection.
    sel_base={}
    for season in selection:
        train=[e for e in ex if e.season<season]; test=[e for e in ex if e.season==season]
        m=pm.fit_fast_logit([base_vectors[e.game_id] for e in train],[e.y for e in train],base_names,l2=base_l2)
        for e in test: sel_base[e.game_id]=m.predict(base_vectors[e.game_id])
    sel_rows=[]
    for e in ex:
        if e.season in selection:
            sel_rows.append({"game_id":e.game_id,"season":e.season,"week":e.week,"y":e.y,"p_base":sel_base[e.game_id],"p_safe":selection_preds[selected_safe][e.game_id],"p_full":selection_preds[selected_full][e.game_id]})
    safe_weights=pe.select_stage_weights(sel_rows,base_field="p_base",context_field="p_safe")
    full_weights=pe.select_stage_weights(sel_rows,base_field="p_base",context_field="p_full")

    # Evaluation OOF predictions, locked before looking at 2022-2024 in this build.
    eval_preds={}
    for name in (selected_safe,selected_full):
        pmap={}; lam=selected[name]
        for season in evaluation:
            train=[e for e in ex if e.season<season]; test=[e for e in ex if e.season==season]
            m=pm.fit_fast_logit([designs[name][e.game_id] for e in train],[e.y for e in train],names_by[name],l2=lam)
            for e in test: pmap[e.game_id]=m.predict(designs[name][e.game_id])
        eval_preds[name]=pmap

    d2_by={r["game_id"]:r for r in d2ledger}
    eval_ex=[e for e in ex if e.season in evaluation]
    if len(eval_ex)!=len(d2ledger): raise SystemExit(f"FAIL Phase2D paired eval count {len(eval_ex)} vs {len(d2ledger)}")
    ledger=[]
    for e in eval_ex:
        if e.game_id not in d2_by: raise SystemExit(f"FAIL missing Phase2D OOF row {e.game_id}")
        base=float(d2_by[e.game_id]["p_solver_controlled_base"])
        ps=eval_preds[selected_safe][e.game_id]; pf=eval_preds[selected_full][e.game_id]
        sw=float(safe_weights[pe.season_stage(e.week)]["selected"]["contextWeight"])
        fw=float(full_weights[pe.season_stage(e.week)]["selected"]["contextWeight"])
        ledger.append({"game_id":e.game_id,"season":e.season,"week":e.week,"home_team":e.home_team,"away_team":e.away_team,"y":e.y,
            "p_solver_base":base,"p_safe_context":ps,"p_full_context":pf,
            "p_safe_stage_blend":pe.blend_probability(base,ps,sw),"p_full_stage_blend":pe.blend_probability(base,pf,fw),
            "safe_context_weight":sw,"full_context_weight":fw,"stage":pe.season_stage(e.week)})

    def metrics(field): return hd.model_metrics(rm,ledger,field)
    metric={k:metrics(k) for k in ("p_solver_base","p_safe_context","p_full_context","p_safe_stage_blend","p_full_stage_blend")}
    year={}
    for season in evaluation:
        rr=[r for r in ledger if int(r["season"])==season]
        year[str(season)]={k:hd.model_metrics(rm,rr,k) for k in metric}
    stage={}
    for st in ("week1","weeks2to4","week5plus"):
        rr=[r for r in ledger if r["stage"]==st]
        stage[st]={k:hd.model_metrics(rm,rr,k) for k in metric}

    def boot(challenger):
        rec=[]
        for r in ledger:
            x=hd.loss_record(int(r["y"]),float(r["p_solver_base"]),float(r[challenger])); x.update({"season":int(r["season"]),"week":int(r["week"])}); rec.append(x)
        return hd.paired_block_bootstrap(rec,reps=a.bootstrap_reps,seed=29005 + len(challenger))
    bootstrap={k:boot(k) for k in ("p_safe_context","p_full_context","p_safe_stage_blend","p_full_stage_blend")}
    def robust(b): return b["brierImprovement"]["ci95Low"]>0 and b["logLossImprovement"]["ci95Low"]>0
    robust_safe=robust(bootstrap["p_safe_stage_blend"]); robust_full=robust(bootstrap["p_full_stage_blend"])

    # Coefficients for the selected SAFE context fit through 2024; still not a holdout fit.
    train=[e for e in ex if e.season<=2024]
    final_model=pm.fit_fast_logit([designs[selected_safe][e.game_id] for e in train],[e.y for e in train],names_by[selected_safe],l2=selected[selected_safe])
    coeff=sorted(({"feature":n,"coefficient":float(c)} for n,c in zip(final_model.names,final_model.coefficients)),key=lambda x:abs(x["coefficient"]),reverse=True)[:24]

    if robust_safe:
        freeze_verdict="SAFE_STAGE_BLEND_READY_FOR_EXPLICIT_SPEC_FREEZE_REVIEW"
    elif robust_full:
        freeze_verdict="TARGET_WEEK_SIGNAL_ROBUST_BUT_SAFE_PROVENANCE_CANDIDATE_NOT_ROBUST"
    else:
        freeze_verdict="NO_ROBUST_CONTEXT_CANDIDATE_DO_NOT_OPEN_HOLDOUT"

    report={"reportVersion":"0.5.0","generatedAt":now(),"sourceSnapshotId":sid,
        "integrity":{"holdoutEvaluated":False,"holdoutLabelsAdmitted":0,"holdoutRowsRead":0,"marketFieldsAllowed":False,"oddsPapiRequests":0,"pairedEvaluationGames":len(ledger)},
        "developmentDiscipline":{"hypothesisOrigin":"Phase2D findings","candidateSelectionSeasons":list(selection),"evaluationSeasons":list(evaluation),"holdoutSeason":2025,"baseL2FrozenFromPhase2D":base_l2,"l2Grid":list(pe.L2_GRID),"blendGrid":list(pe.BLEND_GRID)},
        "selectedSafeVariant":selected_safe,"selectedFullVariant":selected_full,"selectedL2":selected,"selectionMetrics":sel_metrics,"regularization":reg,
        "safeStageWeights":safe_weights,"fullStageWeights":full_weights,"metrics":metric,"yearMetrics":year,"stageMetrics":stage,"bootstrap":bootstrap,
        "robustSafeStageBlend":robust_safe,"robustFullStageBlend":robust_full,"freezeVerdict":freeze_verdict,
        "sourcePolicy":{"safe":"STRICT_LAG_TEMPORAL_PROVENANCE_PASS","full":"WEEKLY_ROSTER_EXACT_PREGAME_TIMESTAMP_NOT_PROVEN","productionEligibility":"SAFE_ONLY_UNTIL_EQUIVALENT_TIMESTAMPED_LIVE/HISTORICAL_AVAILABILITY_SOURCE_EXISTS"},
        "topSafeStandardizedCoefficients":coeff,
        "notes":["All candidate feature-family and stage-weight choices are made from 2018-2021 OOF predictions only.","2022-2024 are evaluation-only within Phase2E; 2025 remains untouched.","All last-4 features are removed in every Phase2E context candidate because Phase2D identified the horizon as a pre-holdout hypothesis to test.","Target-week context remains an information upper bound only until historical timing provenance is resolved.","Market information is not loaded, fitted, or used for candidate selection."]}
    spec={"phase":"NFL_2.9.0_PHASE2E","status":"PREHOLDOUT_SAFE_FREEZE_CANDIDATE","sourceSnapshotId":sid,"holdoutSeason":2025,"holdoutEvaluated":False,"marketFieldsAllowed":False,
        "selectedSafeVariant":selected_safe,"selectedSafeL2":selected[selected_safe],"safeStageWeights":{k:v["selected"]["contextWeight"] for k,v in safe_weights.items()},"selectedFullVariant":selected_full,"selectedFullL2":selected[selected_full],"fullSourceGate":"NOT_PRODUCTION_ELIGIBLE","freezeVerdict":freeze_verdict,"lineage":pe.LINEAGE}
    specsha=hashlib.sha256(canon(spec)).hexdigest()

    out=root/"data/models/nfl/phase2e"/sid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable Phase2E output: {out}")
    stage_dir=out.parent/("."+sid+".staging"); stage_dir.mkdir(parents=True,exist_ok=False)
    try:
        writecsv(stage_dir/"PHASE2E_OOF_LEDGER.csv",ledger)
        (stage_dir/"PHASE2E_FREEZE_REVIEW.json").write_text(json.dumps(report,indent=2)+"\n")
        (stage_dir/"PHASE2E_SPEC.json").write_bytes(canon(spec)); (stage_dir/"PHASE2E_SPEC.sha256").write_text(specsha+"  PHASE2E_SPEC.json\n")
        md=["# MODEL NFL 2.9.0 Phase 2E — Safe Freeze Candidate","","**2025 HOLDOUT REMAINS SEALED. NOT PRODUCTION.**","",f"Source snapshot: `{sid}`","",
            "## Why this phase exists","","Phase 2D showed that target-week QB/roster context was robust, strict-lag context was not yet robust, and removing the last-4 horizon improved the strongest context challenger. Phase 2E tests whether a provenance-safe, no-last4 architecture can survive after feature-family and season-stage choices are locked on 2018–2021 only.","",
            "## Locked selection choices","",f"- SAFE variant selected on 2018–2021 only: **`{selected_safe}`** · λ **{selected[selected_safe]:g}**",f"- FULL information-upper-bound variant: **`{selected_full}`** · λ **{selected[selected_full]:g}**",f"- Solver-controlled base λ frozen from Phase 2D: **{base_l2:g}**","",
            "### SAFE stage blend weights (chosen on 2018–2021 OOF only)",""]
        for st in ("week1","weeks2to4","week5plus"):
            s=safe_weights[st]["selected"]; md.append(f"- `{st}`: context weight **{s['contextWeight']:.2f}** · selection Brier {s['brier']:.5f} · log loss {s['logLoss']:.5f} · N={s['n']}")
        md += ["","### FULL upper-bound stage blend weights (not production eligible)",""]
        for st in ("week1","weeks2to4","week5plus"):
            s=full_weights[st]["selected"]; md.append(f"- `{st}`: context weight **{s['contextWeight']:.2f}** · selection Brier {s['brier']:.5f} · log loss {s['logLoss']:.5f} · N={s['n']}")
        md += ["","## Paired evaluation performance (2022–2024)","","| Model | N | Brier | Log loss | Accuracy | Cal intercept | Cal slope |","|---|---:|---:|---:|---:|---:|---:|"]
        labels_map=(("p_solver_base","solver_base"),("p_safe_context","safe_context"),("p_safe_stage_blend","safe_stage_blend"),("p_full_context","full_context_upper_bound"),("p_full_stage_blend","full_stage_blend_upper_bound"))
        for field,label in labels_map:
            m=metric[field]; c=m["calibration"]; md.append(f"| {label} | {m['n']} | {m['brier']:.5f} | {m['logLoss']:.5f} | {m['accuracy']:.3f} | {c['intercept']:+.3f} | {c['slope']:.3f} |")
        md += ["","## Bootstrap vs solver-controlled base",""]
        for field,label in (("p_safe_context","SAFE context"),("p_safe_stage_blend","SAFE stage blend"),("p_full_context","FULL context upper bound"),("p_full_stage_blend","FULL stage blend upper bound")):
            b=bootstrap[field]; bi=b["brierImprovement"]; li=b["logLossImprovement"]; md.append(f"- {label}: Brier Δ **{bi['mean']:+.5f}** (95% CI {bi['ci95Low']:+.5f} to {bi['ci95High']:+.5f}); log-loss Δ **{li['mean']:+.5f}** (95% CI {li['ci95Low']:+.5f} to {li['ci95High']:+.5f}).")
        md += ["",f"- Robust SAFE stage blend: **{str(robust_safe).upper()}**",f"- Robust FULL stage blend: **{str(robust_full).upper()}**","","## Season-stage behavior (2022–2024)",""]
        for st in ("week1","weeks2to4","week5plus"):
            x=stage[st]; md.append(f"- `{st}` N={x['p_solver_base']['n']} · base {x['p_solver_base']['brier']:.5f} · SAFE context {x['p_safe_context']['brier']:.5f} · SAFE blend {x['p_safe_stage_blend']['brier']:.5f} · FULL upper bound {x['p_full_context']['brier']:.5f}")
        md += ["","## Year-by-year SAFE candidate",""]
        for season in evaluation:
            x=year[str(season)]; md.append(f"- {season}: base Brier {x['p_solver_base']['brier']:.5f} / LL {x['p_solver_base']['logLoss']:.5f} · SAFE blend Brier {x['p_safe_stage_blend']['brier']:.5f} / LL {x['p_safe_stage_blend']['logLoss']:.5f}")
        md += ["","## Temporal provenance","","- SAFE branch: **STRICT_LAG_TEMPORAL_PROVENANCE_PASS**","- FULL branch: **WEEKLY_ROSTER_EXACT_PREGAME_TIMESTAMP_NOT_PROVEN**","- FULL branch remains an information upper bound and cannot become the historical production specification from this evidence.","",
            "## Top standardized coefficients — selected SAFE context",""]
        for c in coeff[:18]: md.append(f"- `{c['feature']}`: {c['coefficient']:+.4f}")
        md += ["","## Integrity / freeze gate","","- 2025 labels admitted: **0**","- 2025 evaluated: **NO**","- Sportsbook/market fields: **DISALLOWED**","- OddsPapi requests: **0**",f"- Freeze verdict: **{freeze_verdict}**","","Do **not** open 2025 automatically. Review this report and explicitly freeze a source/feature/stage specification first.",""]
        (stage_dir/"PHASE2E_FREEZE_REVIEW.md").write_text("\n".join(md))
        edge=["# NFL Edge Exposure Contract — Phase 2E","","This phase does not backtest or tune against sportsbook prices.","","The independent output bundle for a future live game should expose:","","- `p_primary`: SAFE stage-blend probability if Phase 2E survives the holdout.","- `p_benchmark`: solver-controlled base probability.","- `p_context_safe`: strict-lag/no-last4 context probability.","- `p_information_upper_bound`: target-week context probability, diagnostic only until source timing is proven.","- `stage` and the locked context weight used for that stage.","","Only after the independent specification is frozen and the 2025 holdout is evaluated once should historical/live market data be joined downstream. The first Trust layer should expose model-vs-market edge, executable EV, benchmark direction agreement, model disagreement, source freshness, verified starting QB, and availability status. No market field is permitted to feed back into `p_primary`.",""]
        (stage_dir/"EDGE_EXPOSURE_CONTRACT.md").write_text("\n".join(edge))
        os.replace(stage_dir,out); (root/"data/models/nfl/CURRENT_PHASE2E").write_text(sid+"\n")
    except Exception:
        shutil.rmtree(stage_dir,ignore_errors=True); raise

    print("MODEL NFL 2.9.0 PHASE 2E — SAFE FREEZE CANDIDATE")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS candidate selection: {selection} only")
    print(f"PASS paired evaluation: {evaluation} · N={len(ledger)}")
    print(f"PASS selected SAFE: {selected_safe} · λ {selected[selected_safe]:g}")
    print("PASS SAFE stage weights: "+" · ".join(f"{k}={safe_weights[k]['selected']['contextWeight']:.2f}" for k in ("week1","weeks2to4","week5plus")))
    print(f"PASS robust SAFE stage blend: {robust_safe}")
    print(f"PASS robust FULL upper bound: {robust_full} · source timing still gated")
    print("PASS 2025 holdout: NOT READ / NOT EVALUATED / 0 labels admitted")
    print("PASS market fields disallowed · OddsPapi requests 0")
    print(f"VERDICT: {freeze_verdict}")
    print(f"REPORT: {out/'PHASE2E_FREEZE_REVIEW.md'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

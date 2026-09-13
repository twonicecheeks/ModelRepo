#!/usr/bin/env python3
"""Score the frozen Phase 2F blind 2025 prediction ledger exactly once."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import argparse,csv,hashlib,json,os,shutil,sys

def now():return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def readcsv(p):
    with Path(p).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL");ap.add_argument("--bootstrap-reps",type=int,default=10000);a=ap.parse_args();root=Path(a.root).expanduser().resolve();sys.path.insert(0,str(root/"packages/models/nfl/game"))
    import research_model as rm, phase2d_hardening as hd, phase2f_holdout as p2f
    sid=(root/"data/models/nfl/CURRENT_PHASE2F_FROZEN").read_text().strip(); bptr=root/"data/models/nfl/CURRENT_PHASE2F_BLIND"
    if not bptr.exists() or bptr.read_text().strip()!=sid:raise SystemExit("FAIL blind prediction pointer mismatch")
    frozen=root/"data/models/nfl/frozen_phase2f"/sid; blind=root/"data/models/nfl/phase2f_blind_2025"/sid
    spec=frozen/"NFL_PHASE2F_FROZEN_SPEC.json"; pred=blind/"PHASE2F_2025_BLIND_PREDICTIONS.csv"
    if (frozen/"NFL_PHASE2F_FROZEN_SPEC.sha256").read_text().strip()!=sha(spec):raise SystemExit("FAIL frozen spec hash")
    if (blind/"PHASE2F_2025_BLIND_PREDICTIONS.sha256").read_text().strip()!=sha(pred):raise SystemExit("FAIL blind prediction hash")
    out=root/"data/models/nfl/phase2f_holdout_2025"/sid; consumed=root/"data/models/nfl/HOLDOUT_2025_CONSUMED.json"
    if consumed.exists() or out.exists():raise SystemExit("FAIL 2025 holdout is already consumed/scored; Phase2F refuses re-evaluation")
    rows=readcsv(pred); targets={}
    p1=root/"data/normalized/nfl/phase1"/sid
    with (p1/"game_targets.csv").open(newline="",encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not str(r["game_id"]).startswith("2025_"):continue
            if r.get("home_win") in ("0","0.0","1","1.0"):targets[r["game_id"]]=int(float(r["home_win"]))
    scored=[]
    for r in rows:
        gid=r["game_id"];y=targets.get(gid)
        if y not in (0,1):continue
        x=dict(r);x["y"]=y;scored.append(x)
    if len(scored)<260:raise SystemExit(f"FAIL too few complete 2025 binary labels: {len(scored)}")
    def metrics(field):return hd.model_metrics(rm,scored,field)
    mb=metrics("p_benchmark");mc=metrics("p_context_safe");mp=metrics("p_primary")
    loss=[]
    for r in scored:
        q={"season":2025,"week":int(r["week"])};q.update(hd.loss_record(int(r["y"]),float(r["p_benchmark"]),float(r["p_primary"])));loss.append(q)
    boot=hd.paired_block_bootstrap(loss,reps=a.bootstrap_reps,seed=29025);bi=boot["brierImprovement"];li=boot["logLossImprovement"]
    v=p2f.verdict(mb["brier"],mp["brier"],mb["logLoss"],mp["logLoss"],bi["ci95Low"],li["ci95Low"])
    stages={}
    for st in ("week1","weeks2to4","week5plus"):
        rr=[r for r in scored if r["stage"]==st];stages[st]={"benchmark":hd.model_metrics(rm,rr,"p_benchmark"),"primary":hd.model_metrics(rm,rr,"p_primary")} if rr else None
    report={"schemaVersion":"NFL_PHASE2F_HOLDOUT_SCORE_1.0","scoredAt":now(),"sourceSnapshotId":sid,"holdoutSeason":2025,"frozenSpecSha256":sha(spec),"blindPredictionSha256":sha(pred),"n":len(scored),"benchmark":mb,"contextSafe":mc,"primary":mp,"pairedWeekBootstrap":boot,"stageMetrics":stages,"verdict":v,"marketFieldsAllowed":False,"oddsPapiRequests":0,"fitOn2025":False,"postHoldoutRule":"2025 CONSUMED FOREVER; never reuse for tuning"}
    stage=out.parent/("."+sid+".score.staging");stage.mkdir(parents=True,exist_ok=False)
    try:
        (stage/"PHASE2F_2025_HOLDOUT_SCORE.json").write_text(json.dumps(report,indent=2)+"\n")
        bimp=mb["brier"]-mp["brier"];limp=mb["logLoss"]-mp["logLoss"]
        md=["# MODEL NFL 2.9.0 Phase 2F — One-Shot 2025 Holdout Score","","**2025 IS NOW CONSUMED. This result may never be used for another tuning loop.**","",f"- Scored games: **{len(scored)}**",f"- Frozen spec SHA256: `{sha(spec)}`",f"- Blind prediction SHA256: `{sha(pred)}`","- 2025 fit rows: **0**","- Market fields: **DISALLOWED**","- OddsPapi requests: **0**","",
            "## Proper-score result","","| Model | Brier | Log loss | Accuracy | Cal intercept | Cal slope |","|---|---:|---:|---:|---:|---:|",
            f"| frozen solver benchmark | {mb['brier']:.5f} | {mb['logLoss']:.5f} | {mb['accuracy']:.3f} | {mb['calibration']['intercept']:+.3f} | {mb['calibration']['slope']:.3f} |",
            f"| SAFE context | {mc['brier']:.5f} | {mc['logLoss']:.5f} | {mc['accuracy']:.3f} | {mc['calibration']['intercept']:+.3f} | {mc['calibration']['slope']:.3f} |",
            f"| **frozen primary stage blend** | **{mp['brier']:.5f}** | **{mp['logLoss']:.5f}** | **{mp['accuracy']:.3f}** | **{mp['calibration']['intercept']:+.3f}** | **{mp['calibration']['slope']:.3f}** |","",
            f"- Brier improvement vs benchmark: **{bimp:+.5f}**",f"- Log-loss improvement vs benchmark: **{limp:+.5f}**",f"- Paired week-bootstrap Brier Δ: **{bi['mean']:+.5f}** (95% CI {bi['ci95Low']:+.5f} to {bi['ci95High']:+.5f})",f"- Paired week-bootstrap log-loss Δ: **{li['mean']:+.5f}** (95% CI {li['ci95Low']:+.5f} to {li['ci95High']:+.5f})","",
            "## Stage diagnostics",""]
        for st in ("week1","weeks2to4","week5plus"):
            x=stages[st]
            if x:md.append(f"- `{st}` N={x['primary']['n']} · benchmark Brier {x['benchmark']['brier']:.5f} · primary {x['primary']['brier']:.5f} · benchmark LL {x['benchmark']['logLoss']:.5f} · primary {x['primary']['logLoss']:.5f}")
        md += ["",f"## Precommitted verdict: **{v}**","","- STRONG_PASS requires both proper scores to improve and both weekly-bootstrap lower bounds >0.","- DIRECTIONAL_PASS requires both proper-score point estimates to improve.","- MIXED means one proper score improved and the other did not.","- FAIL_BOTH means both worsened.","","Regardless of verdict, **2025 may not be used to retune this architecture.** Any future model change must be judged with pre-2025 development discipline plus prospective 2026 tracking/new untouched data.",""]
        (stage/"PHASE2F_2025_HOLDOUT_SCORE.md").write_text("\n".join(md));os.replace(stage,out)
        marker={"consumedAt":now(),"sourceSnapshotId":sid,"frozenSpecSha256":sha(spec),"blindPredictionSha256":sha(pred),"scoreReportSha256":sha(out/"PHASE2F_2025_HOLDOUT_SCORE.json"),"verdict":v,"rule":"DO_NOT_REUSE_2025_FOR_TUNING"};tmp=consumed.with_name(".HOLDOUT_2025_CONSUMED.tmp");tmp.write_text(json.dumps(marker,indent=2)+"\n");os.replace(tmp,consumed);(root/"data/models/nfl/CURRENT_PHASE2F_HOLDOUT").write_text(sid+"\n")
    except Exception:shutil.rmtree(stage,ignore_errors=True);raise
    print("MODEL NFL 2.9.0 PHASE 2F — ONE-SHOT 2025 HOLDOUT")
    print(f"PASS scored immutable blind ledger: {len(scored)} games")
    print(f"PASS benchmark Brier {mb['brier']:.5f} · primary {mp['brier']:.5f} · Δ {bimp:+.5f}")
    print(f"PASS benchmark LogLoss {mb['logLoss']:.5f} · primary {mp['logLoss']:.5f} · Δ {limp:+.5f}")
    print(f"VERDICT: {v}")
    print("2025 HOLDOUT STATUS: CONSUMED FOREVER — NO RETUNING")
    print(f"REPORT: {out/'PHASE2F_2025_HOLDOUT_SCORE.md'}")
    return 0
if __name__=="__main__":raise SystemExit(main())

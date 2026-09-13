#!/usr/bin/env python3
"""OMEGA 0.14 — permanently seal the completed 2025 STRONG_PASS holdout.

This is archival/integrity work only. It does not fit, predict, score, or inspect
new outcomes. It hashes the already-completed 0.13.1 artifacts and records the
post-holdout boundary before productionization begins.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, shutil

SCHEMA="OMEGA_TACKLE_POST_HOLDOUT_SEAL_0.14"
SID="20260910T205221Z_58d8156a"
FROZEN_SPEC_SHA="c2ca80b6a144c3aa86bc41bdb82f6f5618ffa279a38f4c6d358025ed7fbd69fb"
BLIND_SHA="59c1a1726bb705661babe3f51fc408e389a25bece6a18df0fdf79065b08d036e"
EXPECTED={
    "modelMae":1.65709,"benchmarkMae":1.76697,"maeImprovement":0.10989,
    "modelRmse":2.18514,"benchmarkRmse":2.36137,"rmseImprovement":0.17623,
    "maeCiLo":0.09154,"maeCiHi":0.12826,"rmseCiLo":0.15410,"rmseCiHi":0.19805,
}

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(p:Path):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def r5(x): return round(float(x)+0.0,5)
def check5(name,got,want):
    if r5(got)!=r5(want): raise SystemExit(f"FAIL holdout metric drift {name}: {got} != {want} (5dp contract)")
def atomic_text(path:Path,text:str):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name("."+path.name+".tmp"); tmp.write_text(text,encoding="utf-8"); os.replace(tmp,path)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); a=ap.parse_args()
    root=Path(a.root).expanduser().resolve()
    hold=root/"data/models/nfl/omega_tackle_013_holdout_2025"/SID
    report=hold/"OMEGA_0.13_HOLDOUT_SCORE.json"; md=hold/"OMEGA_0.13_HOLDOUT_SCORE.md"; scored=hold/"OMEGA_2025_HOLDOUT_SCORED.csv"; scored_sha=hold/"OMEGA_2025_HOLDOUT_SCORED.sha256"; manifest=hold/"OMEGA_OUTPUT_MANIFEST.json"
    consumed=root/"data/models/nfl/OMEGA_TACKLE_2025_CONSUMED.json"; resolved=root/"data/models/nfl/OMEGA_TACKLE_2025_SCORING_RECOVERY_RESOLVED.json"
    frozen=root/"data/models/nfl/omega_tackle_frozen"/SID/"OMEGA_TACKLE_FROZEN_SPEC.json"
    blind=root/"data/models/nfl/omega_tackle_012_blind_2025"/SID/"OMEGA_2025_BLIND_PREDICTIONS.csv"
    for p in (report,md,scored,scored_sha,manifest,consumed,resolved,frozen,blind):
        if not p.exists(): raise SystemExit(f"FAIL required post-holdout artifact missing: {p}")
    if sha(frozen)!=FROZEN_SPEC_SHA: raise SystemExit("FAIL frozen spec hash drift")
    if sha(blind)!=BLIND_SHA: raise SystemExit("FAIL blind ledger hash drift")
    if scored_sha.read_text(encoding="utf-8").strip()!=sha(scored): raise SystemExit("FAIL scored ledger sidecar hash mismatch")
    j=json.loads(report.read_text(encoding="utf-8")); c=json.loads(consumed.read_text(encoding="utf-8")); rr=json.loads(resolved.read_text(encoding="utf-8"))
    if j.get("precommittedVerdict")!="STRONG_PASS" or c.get("verdict")!="STRONG_PASS" or rr.get("verdict")!="STRONG_PASS": raise SystemExit("FAIL STRONG_PASS state not consistent across completed artifacts")
    if c.get("status")!="CONSUMED_FOREVER_FOR_OMEGA_TACKLE_TUNING": raise SystemExit("FAIL OMEGA 2025 is not permanently consumed")
    if j.get("frozenSpecSha256")!=FROZEN_SPEC_SHA or j.get("blindPredictionSha256")!=BLIND_SHA: raise SystemExit("FAIL report lineage hash drift")
    if int(j.get("coverage",{}).get("rows") or 0)!=10524 or int(j.get("coverage",{}).get("games") or 0)!=272 or int(j.get("coverage",{}).get("weeks") or 0)!=18: raise SystemExit("FAIL completed holdout coverage drift")
    ov=j["overall"]; boot=j["pairedGameClusterBootstrap"]
    check5("OMEGA MAE",ov["model"]["mae"],EXPECTED["modelMae"]); check5("benchmark MAE",ov["benchmark"]["mae"],EXPECTED["benchmarkMae"]); check5("MAE delta",ov["maeImprovement"],EXPECTED["maeImprovement"])
    check5("OMEGA RMSE",ov["model"]["rmse"],EXPECTED["modelRmse"]); check5("benchmark RMSE",ov["benchmark"]["rmse"],EXPECTED["benchmarkRmse"]); check5("RMSE delta",ov["rmseImprovement"],EXPECTED["rmseImprovement"])
    check5("MAE CI lo",boot["maeImprovementCI95"][0],EXPECTED["maeCiLo"]); check5("MAE CI hi",boot["maeImprovementCI95"][1],EXPECTED["maeCiHi"]); check5("RMSE CI lo",boot["rmseImprovementCI95"][0],EXPECTED["rmseCiLo"]); check5("RMSE CI hi",boot["rmseImprovementCI95"][1],EXPECTED["rmseCiHi"])
    if int(boot.get("reps") or 0)!=10000 or int(boot.get("seed") or 0)!=290013 or boot.get("cluster")!="game_id": raise SystemExit("FAIL bootstrap contract drift")
    if boot["maeImprovementCI95"][0] <= 0 or boot["rmseImprovementCI95"][0] <= 0: raise SystemExit("FAIL STRONG_PASS CI condition no longer holds")
    out=root/"data/models/nfl/omega_tackle_014_post_holdout_seal"/SID
    if out.exists():
        seal=out/"OMEGA_0.14_POST_HOLDOUT_SEAL.json"; side=out/"OMEGA_0.14_POST_HOLDOUT_SEAL.sha256"
        if seal.exists() and side.exists() and side.read_text().strip()==sha(seal):
            atomic_text(root/"data/models/nfl/CURRENT_OMEGA_TACKLE_POST_HOLDOUT_SEAL",SID+"\n")
            print(f"PASS existing immutable OMEGA 0.14 post-holdout seal verified: {out}"); return 0
        raise SystemExit(f"FAIL corrupt/incomplete existing OMEGA 0.14 seal: {out}")
    st=out.parent/("."+SID+".staging"); st.mkdir(parents=True,exist_ok=False)
    try:
        files={p.name:{"sha256":sha(p),"bytes":p.stat().st_size} for p in (report,md,scored,scored_sha,manifest,consumed,resolved)}
        seal_obj={
            "schemaVersion":SCHEMA,"sealedAt":now(),"sourceSnapshotId":SID,
            "status":"POST_HOLDOUT_STRONG_PASS_SEALED_PRODUCTIONIZATION_ONLY",
            "frozenSpecSha256":FROZEN_SPEC_SHA,"blindPredictionSha256":BLIND_SHA,
            "holdoutVerdict":"STRONG_PASS","holdoutRows":10524,"holdoutGames":272,"holdoutWeeks":18,
            "metrics":{"omegaMAE":ov["model"]["mae"],"benchmarkMAE":ov["benchmark"]["mae"],"maeImprovement":ov["maeImprovement"],"omegaRMSE":ov["model"]["rmse"],"benchmarkRMSE":ov["benchmark"]["rmse"],"rmseImprovement":ov["rmseImprovement"],"maeCI95":boot["maeImprovementCI95"],"rmseCI95":boot["rmseImprovementCI95"]},
            "bootstrap":{"cluster":"game_id","reps":10000,"seed":290013},
            "artifacts":files,
            "permanentRules":[
                "OMEGA 2025 is consumed forever for tackle-model tuning.",
                "Do not select features, transforms, hyperparameters, subgroups, thresholds, or market rules from 2025 outcomes.",
                "Future work is productionization, distribution/market validation, or genuinely prospective research.",
                "Sportsbook prices remain downstream of the independent OMEGA-I prediction path."
            ]
        }
        sp=st/"OMEGA_0.14_POST_HOLDOUT_SEAL.json"; sp.write_text(json.dumps(seal_obj,indent=2)+"\n",encoding="utf-8")
        (st/"OMEGA_0.14_POST_HOLDOUT_SEAL.md").write_text(
            "# OMEGA 0.14 — Post-Holdout Production Gate\n\n"
            "**2025 OMEGA tackle holdout: STRONG_PASS and CONSUMED FOREVER.**\n\n"
            f"- Frozen spec SHA256: `{FROZEN_SPEC_SHA}`\n- Blind ledger SHA256: `{BLIND_SHA}`\n"
            f"- Rows / games / weeks: **10524 / 272 / 18**\n"
            f"- OMEGA MAE **{ov['model']['mae']:.5f}** vs benchmark **{ov['benchmark']['mae']:.5f}** · Δ **{ov['maeImprovement']:+.5f}**\n"
            f"- OMEGA RMSE **{ov['model']['rmse']:.5f}** vs benchmark **{ov['benchmark']['rmse']:.5f}** · Δ **{ov['rmseImprovement']:+.5f}**\n"
            f"- MAE 95% CI **[{boot['maeImprovementCI95'][0]:+.5f}, {boot['maeImprovementCI95'][1]:+.5f}]**\n"
            f"- RMSE 95% CI **[{boot['rmseImprovementCI95'][0]:+.5f}, {boot['rmseImprovementCI95'][1]:+.5f}]**\n\n"
            "Historical football-only mechanism search remains closed. Productionization may proceed; sportsbook-edge claims may not.\n",encoding="utf-8")
        (st/"OMEGA_0.14_POST_HOLDOUT_SEAL.sha256").write_text(sha(sp)+"\n",encoding="utf-8")
        os.replace(st,out)
    except Exception:
        shutil.rmtree(st,ignore_errors=True); raise
    atomic_text(root/"data/models/nfl/CURRENT_OMEGA_TACKLE_POST_HOLDOUT_SEAL",SID+"\n")
    print("OMEGA 0.14 — POST-HOLDOUT SEAL")
    print("PASS 2025 STRONG_PASS result permanently sealed")
    print(f"PASS OMEGA MAE {ov['model']['mae']:.5f} vs {ov['benchmark']['mae']:.5f} · Δ {ov['maeImprovement']:+.5f}")
    print(f"PASS OMEGA RMSE {ov['model']['rmse']:.5f} vs {ov['benchmark']['rmse']:.5f} · Δ {ov['rmseImprovement']:+.5f}")
    print("PASS 2025 remains CONSUMED FOREVER — productionization only")
    print(f"SEAL: {out/'OMEGA_0.14_POST_HOLDOUT_SEAL.json'}")
    return 0
if __name__=="__main__": raise SystemExit(main())

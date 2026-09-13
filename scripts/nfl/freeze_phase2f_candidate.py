#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, sys

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canon(x): return (json.dumps(x,sort_keys=True,separators=(",",":"))+"\n").encode()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); a=ap.parse_args()
    root=Path(a.root).expanduser().resolve(); sys.path.insert(0,str(root/"packages/models/nfl/game"))
    import phase2f_holdout as p2f
    sid=(root/"data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT").read_text().strip()
    p2e_ptr=root/"data/models/nfl/CURRENT_PHASE2E"
    if not p2e_ptr.exists() or p2e_ptr.read_text().strip()!=sid: raise SystemExit("FAIL Phase2E pointer mismatch")
    p2e_dir=root/"data/models/nfl/phase2e"/sid
    review=json.loads((p2e_dir/"PHASE2E_FREEZE_REVIEW.json").read_text())
    if review.get("freezeVerdict")!="SAFE_STAGE_BLEND_READY_FOR_EXPLICIT_SPEC_FREEZE_REVIEW": raise SystemExit("FAIL Phase2E freeze verdict")
    integ=review.get("integrity",{})
    if integ.get("holdoutEvaluated") or int(integ.get("holdoutLabelsAdmitted",-1))!=0 or integ.get("marketFieldsAllowed") is not False or int(integ.get("oddsPapiRequests",-1))!=0:
        raise SystemExit("FAIL Phase2E integrity boundary")
    if review.get("selectedSafeVariant")!=p2f.SAFE_VARIANT: raise SystemExit(f"FAIL selected SAFE drift: {review.get('selectedSafeVariant')}")
    if abs(float(review["selectedL2"][p2f.SAFE_VARIANT])-p2f.SAFE_L2)>1e-12: raise SystemExit("FAIL SAFE lambda drift")
    weights={k:float(review["safeStageWeights"][k]["selected"]["contextWeight"]) for k in p2f.STAGE_WEIGHTS}
    if any(abs(weights[k]-p2f.STAGE_WEIGHTS[k])>1e-12 for k in weights): raise SystemExit(f"FAIL stage-weight drift: {weights}")
    if review.get("robustSafeStageBlend") is not True: raise SystemExit("FAIL SAFE stage blend not robust")

    out=root/"data/models/nfl/frozen_phase2f"/sid
    if out.exists():
        spec=out/"NFL_PHASE2F_FROZEN_SPEC.json"; h=out/"NFL_PHASE2F_FROZEN_SPEC.sha256"
        if not spec.exists() or not h.exists() or h.read_text().strip()!=sha(spec): raise SystemExit("FAIL existing frozen spec integrity")
        (root/"data/models/nfl/CURRENT_PHASE2F_FROZEN").write_text(sid+"\n")
        print(f"PASS existing immutable Phase2F freeze verified: {out}"); return 0
    out.parent.mkdir(parents=True,exist_ok=True); stage=out.parent/("."+sid+".freeze.staging"); stage.mkdir(parents=True,exist_ok=False)
    source_files={
        "phase2eReviewJson": p2e_dir/"PHASE2E_FREEZE_REVIEW.json",
        "phase2eSpecJson": p2e_dir/"PHASE2E_SPEC.json",
        "phase2eOofLedger": p2e_dir/"PHASE2E_OOF_LEDGER.csv",
        "researchModel": root/"packages/models/nfl/game/research_model.py",
        "phase2cModel": root/"packages/models/nfl/game/phase2c_model.py",
        "phase2dHardening": root/"packages/models/nfl/game/phase2d_hardening.py",
        "phase2eFreeze": root/"packages/models/nfl/game/phase2e_freeze.py",
        "phase2fHoldout": root/"packages/models/nfl/game/phase2f_holdout.py",
    }
    for k,p in source_files.items():
        if not p.exists(): raise SystemExit(f"FAIL freeze source missing: {k} {p}")
    spec={
        "schemaVersion":"NFL_PHASE2F_FROZEN_SPEC_1.0","frozenAt":now(),"sourceSnapshotId":sid,
        "lineage":p2f.LINEAGE,"holdoutSeason":p2f.HOLDOUT_SEASON,"trainingSeasons":list(p2f.TRAIN_SEASONS),
        "modelClass":"STANDARDIZED_L2_LOGISTIC_STAGE_BLEND",
        "primaryBranch":"STRICT_LAG_SAFE",
        "safeVariant":p2f.SAFE_VARIANT,"safeL2":p2f.SAFE_L2,"baseL2":p2f.BASE_L2,
        "stageWeights":p2f.STAGE_WEIGHTS,
        "featurePolicy":{"removeLast4":True,"removeTurnoverTakeawayQbInt":True,"removeRushEpa":True,
                         "strictLagQb":"previous observed primary QB only; current target game excluded",
                         "strictLagPersonnel":"G-2 to G-1 snap retention; target-week roster forbidden"},
        "fitPolicy":"Fit final base and SAFE coefficient sets on 2016-2024 REG only after specification freeze. Never fit 2025.",
        "holdoutProtocol":{"blindPredictionFirst":True,"scoreLabelsOnce":True,"marketsForbidden":True,"oddsPapiRequests":0,
            "verdictPolicy":{"STRONG_PASS":"Brier and log loss both improve vs frozen solver base and both paired week-bootstrap 95% CI lower bounds > 0",
                             "DIRECTIONAL_PASS":"Brier and log loss both improve vs frozen solver base but strong-bootstrap criterion is not met",
                             "FAIL_BOTH":"Brier and log loss both worsen vs frozen solver base",
                             "MIXED":"all other outcomes"},
            "postHoldoutRule":"2025 becomes consumed forever after scoring; no feature, lambda, transformation, or threshold may be selected by reusing 2025."},
        "marketBoundary":"No market field may enter p_primary. Market/CLV research begins only after this one-shot holdout score.",
        "phase2eLockedEvidence":{"selectedSafeVariant":review["selectedSafeVariant"],"robustSafeStageBlend":review["robustSafeStageBlend"],
                                  "safeStageWeights":weights,"evaluationSeasons":review["developmentDiscipline"]["evaluationSeasons"]},
        "sourceHashes":{k:sha(p) for k,p in source_files.items()},
    }
    b=canon(spec); spec_path=stage/"NFL_PHASE2F_FROZEN_SPEC.json"; spec_path.write_bytes(b); digest=hashlib.sha256(b).hexdigest(); (stage/"NFL_PHASE2F_FROZEN_SPEC.sha256").write_text(digest+"\n")
    md=["# MODEL NFL 2.9.0 Phase 2F — Explicit Frozen Specification","","**2025 has not been scored. This file is the pre-holdout contract.**","",
        f"- Source snapshot: `{sid}`",f"- Frozen lineage: `{p2f.LINEAGE}`",f"- SAFE variant: `{p2f.SAFE_VARIANT}`",f"- SAFE λ: **{p2f.SAFE_L2}**",f"- Base λ: **{p2f.BASE_L2}**",
        f"- Stage weights: Week 1 **{p2f.STAGE_WEIGHTS['week1']:.2f}** · Weeks 2–4 **{p2f.STAGE_WEIGHTS['weeks2to4']:.2f}** · Week 5+ **{p2f.STAGE_WEIGHTS['week5plus']:.2f}**","",
        "## Locked feature/source rules","","- Strict-lag QB only; no target-week roster.","- Personnel continuity is G-2 → G-1 only.","- Remove all last-4 features.","- Remove turnover/takeaway/QB interception-rate features.","- Remove rushing-EPA features.","- Sportsbook/market inputs are forbidden.","- Final coefficients may fit 2016–2024 REG only; 2025 is never fit.","",
        "## One-shot holdout verdict","","- STRONG_PASS: both proper scores improve and both paired week-bootstrap lower bounds are >0.","- DIRECTIONAL_PASS: both proper scores improve, without strong-bootstrap support.","- FAIL_BOTH: both proper scores worsen.","- MIXED: all other outcomes.","","After scoring, 2025 is permanently consumed and cannot be reused for tuning.","",f"Frozen spec SHA256: `{digest}`",""]
    (stage/"NFL_PHASE2F_FROZEN_SPEC.md").write_text("\n".join(md))
    os.replace(stage,out); (root/"data/models/nfl/CURRENT_PHASE2F_FROZEN").write_text(sid+"\n")
    print("MODEL NFL 2.9.0 PHASE 2F — EXPLICIT SPEC FREEZE")
    print(f"PASS frozen snapshot: {sid}")
    print(f"PASS frozen SAFE variant: {p2f.SAFE_VARIANT} · λ {p2f.SAFE_L2}")
    print("PASS stage weights: week1=0.00 · weeks2to4=1.00 · week5plus=0.75")
    print("PASS 2025 scored: NO · market inputs: DISALLOWED")
    print(f"PASS frozen spec sha256: {digest}")
    print(f"SPEC: {out/'NFL_PHASE2F_FROZEN_SPEC.md'}")
    return 0
if __name__=="__main__": raise SystemExit(main())

#!/usr/bin/env python3
"""NFL QB Model 0.2.4.2 — verified-starter slate batch scorer.

Thin orchestration over the existing immutable 0.2.4 single-QB scorer.
It does not alter QB model logic, features, coefficients, residual calibration,
or market policy. Every target row must already contain an externally verified
starter identity.

Manifest CSV columns:
  game_id,team,qb_gsis_id,qb_name,identity_source

Allowed identity_source values are inherited from 0.2.4:
  DIRECT_SPORTSBOOK_MARKET
  OFFICIAL_STARTER_ANNOUNCEMENT
  USER_VERIFIED_EXTERNAL

The batch runner sequentially invokes the exact 0.2.4 scorer, validates each
immutable output, and emits one consolidated projection board.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse,csv,json,subprocess,sys,uuid

REQUIRED=("game_id","team","qb_gsis_id","qb_name","identity_source")
ALLOWED={"DIRECT_SPORTSBOOK_MARKET","OFFICIAL_STARTER_ANNOUNCEMENT","USER_VERIFIED_EXTERNAL"}

def read_manifest(path:Path):
    with path.open(newline="",encoding="utf-8-sig") as f:
        rd=csv.DictReader(f)
        fields=set(rd.fieldnames or [])
        miss=[x for x in REQUIRED if x not in fields]
        if miss:raise ValueError("manifest missing columns: "+", ".join(miss))
        rows=[]
        for i,r in enumerate(rd,2):
            x={k:str(r.get(k) or "").strip() for k in REQUIRED}
            if not all(x.values()):raise ValueError(f"manifest row {i} has blank required field")
            x["identity_source"]=x["identity_source"].upper()
            if x["identity_source"] not in ALLOWED:
                raise ValueError(f"manifest row {i} invalid identity_source {x['identity_source']}")
            rows.append(x)
    if not rows:raise ValueError("manifest contains no targets")
    keys=[(r["game_id"],r["team"]) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError("duplicate game_id/team target in manifest")
    ids=[(r["game_id"],r["qb_gsis_id"]) for r in rows]
    if len(ids)!=len(set(ids)):raise ValueError("duplicate game_id/QB target in manifest")
    return rows

def write_csv(path:Path,rows):
    fields=[
      "game_id","team","opponent","qb_name","qb_gsis_id","identity_source",
      "projection_passing_yards","predictive_p50","central80_low","central80_high",
      "central90_low","central90_high","last4_baseline","qb_prior_games",
      "team_prior_games","defense_prior_games","run_id","score_path"
    ]
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser(description="Batch-score verified Week-2 QBs with frozen QB 0.2.4")
    ap.add_argument("--code-root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--data-root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--manifest",required=True)
    ap.add_argument("--python",default="")
    args=ap.parse_args()
    code_root=Path(args.code_root).expanduser().resolve()
    data_root=Path(args.data_root).expanduser().resolve()
    manifest=Path(args.manifest).expanduser().resolve()
    if not manifest.exists():raise FileNotFoundError(manifest)
    rows=read_manifest(manifest)
    scorer=code_root/"scripts/nfl/score_nfl_qb_passing_yards_asof_024.py"
    if not scorer.exists():raise FileNotFoundError(scorer)
    py=args.python.strip() or sys.executable
    pointer=data_root/"data/prospective/nfl/CURRENT_QB_PASSING_YARDS_024"

    out=[]
    print(f"QB 0.2.4.2 — VERIFIED-STARTER SLATE BATCH · targets {len(rows)}")
    for idx,r in enumerate(rows,1):
        cmd=[
          py,str(scorer),"--root",str(data_root),
          "--game-id",r["game_id"],"--team",r["team"],
          "--qb-gsis-id",r["qb_gsis_id"],"--qb-name",r["qb_name"],
          "--identity-source",r["identity_source"],
        ]
        if shared_source_manifest is not None:
            cmd.extend(["--source-manifest",str(shared_source_manifest)])
        print(f"\n===== QB {idx}/{len(rows)} · {r['game_id']} · {r['team']} · {r['qb_name']} =====")
        cp=subprocess.run(cmd,text=True)
        if cp.returncode!=0:raise SystemExit(cp.returncode)
        if not pointer.exists():raise FileNotFoundError("0.2.4 score pointer missing after successful scorer run")
        score_dir=data_root/pointer.read_text().strip()
        score_path=score_dir/"NFL_QB_PASSING_YARDS_ASOF_SCORE.json"
        score=json.loads(score_path.read_text())
        if shared_source_manifest is None:
            rel=str(score.get("sourceProspectiveManifest") or "").strip()
            if not rel: raise ValueError("first QB score did not expose prospective source manifest")
            shared_source_manifest=(data_root/rel).resolve()
            if not shared_source_manifest.exists(): raise FileNotFoundError(shared_source_manifest)
            print(f"PASS shared immutable prospective source: {shared_source_manifest}")
        target=score.get("target") or {}
        if str(target.get("game_id"))!=r["game_id"] or str(target.get("team"))!=r["team"] or str(target.get("qb_gsis_id"))!=r["qb_gsis_id"]:
            raise ValueError("batch scorer pointer target mismatch")
        if score.get("status")!="PROSPECTIVE_SHADOW_SCORE_FROZEN_0.2.1":
            raise ValueError("unexpected QB score status")
        if score.get("coefficientRefitPerformed") is not False or score.get("candidateReselectionPerformed") is not False:
            raise ValueError("mutated QB score rejected")
        if int(score.get("targetOrLater2026OutcomeRowsAdmitted") or 0)!=0 or int(score.get("marketPriceFieldsAdmitted") or 0)!=0:
            raise ValueError("QB leakage/market-contamination invariant failed")
        dist=score["frozenPredictiveDistribution"];q=dist["predictiveQuantiles"]
        out.append({
          "game_id":target["game_id"],"team":target["team"],"opponent":target["opponent"],
          "qb_name":target.get("qb_name") or r["qb_name"],"qb_gsis_id":target["qb_gsis_id"],
          "identity_source":target["identitySource"],
          "projection_passing_yards":score["projectionPassingYards"],
          "predictive_p50":q["p50"],
          "central80_low":dist["central80"][0],"central80_high":dist["central80"][1],
          "central90_low":dist["central90"][0],"central90_high":dist["central90"][1],
          "last4_baseline":score["baselineLast4PassingYards"],
          "qb_prior_games":score["qbPriorGames"],"team_prior_games":score["teamPriorGames"],
          "defense_prior_games":score["defensePriorGames"],"run_id":score["runId"],
          "score_path":str(score_path.relative_to(data_root)),
        })

    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    od=data_root/"data/prospective/nfl/qb_passing_yards_slate_0242"/run_id;od.mkdir(parents=True,exist_ok=False)
    csvp=od/"NFL_QB_PASSING_YARDS_SLATE_PROJECTIONS.csv";write_csv(csvp,out)
    report={
      "version":"0.2.4.2","createdAt":datetime.now(timezone.utc).isoformat(),"runId":run_id,
      "targets":len(out),"manifest":str(manifest),"codeRoot":str(code_root),"dataRoot":str(data_root),
      "sharedProspectiveSourceManifest":str(shared_source_manifest) if shared_source_manifest else None,
      "decisionModel":"FROZEN_MODEL_A_DIRECT_0.2.1","marketDependency":False,
      "coefficientRefitPerformed":False,"candidateReselectionPerformed":False,
      "targetOrLater2026OutcomeRowsAdmitted":0,"oddsPapiRequests":0,"frozenOmegaMutation":False,
      "rows":out,
    }
    jp=od/"NFL_QB_PASSING_YARDS_SLATE_AUDIT.json";jp.write_text(json.dumps(report,indent=2)+"\n")
    ptr=data_root/"data/prospective/nfl/CURRENT_QB_PASSING_YARDS_SLATE_0242";ptr.write_text(str(od.relative_to(data_root))+"\n")
    print("\nNFL QB MODEL 0.2.4.2 — SLATE PROJECTION BOARD")
    for r in out:
        print(f"  {r['game_id']} · {r['qb_name']} ({r['team']}) · {float(r['projection_passing_yards']):.1f} yd · p50 {float(r['predictive_p50']):.1f} · C80 [{float(r['central80_low']):.1f},{float(r['central80_high']):.1f}]")
    print("PASS market fields 0 · target/same-week outcomes 0 · refits 0 · one shared prospective source snapshot")
    print(f"BOARD: {csvp}")
    print(f"AUDIT: {jp}")
    return 0

if __name__=="__main__":raise SystemExit(main())

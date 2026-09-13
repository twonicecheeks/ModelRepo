#!/usr/bin/env python3
"""Build OMEGA 0.2.2 exposure-role challenger.

Single mechanism under test: H012 exposure/role prediction. The 0.2 tackle-rate
component and 0.2 team defensive-snap model are held fixed for 2024 comparison.
No xTO coupling, market data, settlement assumptions, or 2025 outcomes are used.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, os, random, shutil, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

SCHEMA = "OMEGA_TACKLE_EXPOSURE_ROLE_CHALLENGER_0.2.2"
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 290022


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        x = float(v)
        return default if math.isnan(x) else x
    except (TypeError, ValueError):
        return default


def metrics(rows: Sequence[dict[str, Any]], actual: str, pred: str) -> dict[str, Any]:
    if not rows:
        return {"n":0,"mae":0.0,"rmse":0.0,"bias":0.0,"actualMean":0.0,"predictedMean":0.0}
    y=[num(r.get(actual)) for r in rows]; p=[num(r.get(pred)) for r in rows]
    return {
        "n":len(rows),
        "mae":fmean(abs(a-b) for a,b in zip(y,p)),
        "rmse":math.sqrt(fmean((a-b)**2 for a,b in zip(y,p))),
        "bias":fmean(b-a for a,b in zip(y,p)),
        "actualMean":fmean(y),
        "predictedMean":fmean(p),
    }


def compare(rows: Sequence[dict[str, Any]], actual: str, challenger: str, baseline: str) -> dict[str, Any]:
    c=metrics(rows,actual,challenger); b=metrics(rows,actual,baseline)
    return {
        "challenger":c,"baseline":b,
        "maeImprovement":b["mae"]-c["mae"],
        "maeImprovementPct":100.0*(b["mae"]-c["mae"])/b["mae"] if b["mae"] else None,
        "rmseImprovement":b["rmse"]-c["rmse"],
    }


def percentile(xs: Sequence[float], p: float) -> float:
    z=sorted(xs)
    if not z: return 0.0
    q=max(0.0,min(1.0,p))*(len(z)-1); lo=int(math.floor(q)); hi=int(math.ceil(q))
    if lo==hi: return z[lo]
    w=q-lo
    return z[lo]*(1-w)+z[hi]*w


def cluster_bootstrap(rows: Sequence[dict[str, Any]], *, actual: str, challenger: str, baseline: str,
                      reps: int=BOOTSTRAP_REPS, seed: int=BOOTSTRAP_SEED) -> dict[str, Any]:
    by: dict[str,list[tuple[float,float,float]]] = defaultdict(list)
    for r in rows:
        by[str(r.get("game_id") or "")].append((num(r.get(actual)),num(r.get(challenger)),num(r.get(baseline))))
    keys=sorted(k for k in by if k)
    rng=random.Random(seed); ds=[]
    for _ in range(reps):
        ec=eb=0.0; n=0
        for _j in range(len(keys)):
            k=keys[rng.randrange(len(keys))]
            for a,c,b in by[k]:
                ec += abs(a-c); eb += abs(a-b); n += 1
        ds.append((eb-ec)/n)
    point=compare(rows,actual,challenger,baseline)
    return {
        "cluster":"game_id","clusters":len(keys),"reps":reps,"seed":seed,
        "maeImprovementPoint":point["maeImprovement"],
        "maeImprovementCI95":[percentile(ds,.025),percentile(ds,.975)],
        "probabilityPositive":sum(x>0 for x in ds)/len(ds),
    }


def history_band(n: int) -> str:
    if n==0: return "0_COLD"
    if n==1: return "1_PRIOR_GAME"
    if n<=4: return "2-4_PRIOR_GAMES"
    if n<=8: return "5-8_PRIOR_GAMES"
    return "9+_PRIOR_GAMES"


def role_band(v: float) -> str:
    if v<.35: return "LOW_<35%"
    if v<.65: return "ROTATIONAL_35-65%"
    if v<.85: return "STARTER_65-85%"
    return "EVERY_DOWN_85%+"


def slice_compare(rows: Sequence[dict[str,Any]], field: str, actual: str, challenger: str, baseline: str) -> dict[str,Any]:
    g: dict[str,list[dict[str,Any]]] = defaultdict(list)
    for r in rows: g[str(r.get(field) or "UNK")].append(r)
    return {k:compare(v,actual,challenger,baseline) for k,v in sorted(g.items())}


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); args=ap.parse_args()
    root=Path(args.root).resolve()
    sys.path.insert(0,str(root/"packages/models/nfl/omega"))
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er

    fptr=root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION"
    eptr=root/"data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE"
    bptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BASELINE"
    dptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_DIAGNOSTICS"
    for p in (fptr,eptr,bptr,dptr):
        if not p.exists(): raise SystemExit(f"FAIL prerequisite pointer missing: {p}")
    sid=fptr.read_text(encoding="utf-8").strip()
    if any(p.read_text(encoding="utf-8").strip()!=sid for p in (eptr,bptr,dptr)):
        raise SystemExit("FAIL OMEGA source snapshot pointers disagree")

    foundation=root/"data/normalized/nfl/omega_tackle"/sid
    exposure=root/"data/normalized/nfl/omega_tackle_exposure"/sid
    base=root/"data/models/nfl/omega_tackle_02"/sid
    diag=root/"data/models/nfl/omega_tackle_021_diagnostics"/sid
    required=[
        foundation/"OMEGA_TACKLE_FOUNDATION_AUDIT.json",
        exposure/"OMEGA_TACKLE_EXPOSURE_AUDIT.json",
        exposure/"omega_tackle_exposure_player_games.csv",
        base/"OMEGA_0.2_AUDIT.json",
        base/"omega_2024_player_validation.csv",
        diag/"OMEGA_0.2.1_DIAGNOSTICS.json",
    ]
    for p in required:
        if not p.exists(): raise SystemExit(f"FAIL required source missing: {p}")
    fa=json.loads(required[0].read_text(encoding="utf-8")); ea=json.loads(required[1].read_text(encoding="utf-8")); ba=json.loads(required[3].read_text(encoding="utf-8")); da=json.loads(required[5].read_text(encoding="utf-8"))
    if fa.get("omegaHoldoutPbpRowsRead") != 0 or ea.get("omegaHoldoutRowsRead") != 0 or ba.get("integrity",{}).get("omega2025RowsRead") != 0 or da.get("integrity",{}).get("omega2025RowsRead") != 0:
        raise SystemExit("FAIL OMEGA 2025 seal not clean")
    if any(x != 0 for x in [fa.get("marketFieldsRead",0),ea.get("marketFieldsRead",0),ba.get("integrity",{}).get("marketFieldsRead",0),da.get("integrity",{}).get("marketFieldsRead",0)]):
        raise SystemExit("FAIL market contamination")

    exposure_rows=read_csv(exposure/"omega_tackle_exposure_player_games.csv")
    if any(int(num(r.get("season")))==2025 for r in exposure_rows): raise SystemExit("FAIL 2025 exposure row read")
    team_snap_totals=xb.estimate_team_defensive_snaps(exposure_rows)
    preg=er.build_exposure_pregame_rows(exposure_rows,team_snap_totals)
    if any(int(r["season"])==2025 for r in preg): raise SystemExit("FAIL 2025 pregame row emitted")

    selected_l2, search=er.choose_l2(preg)
    train=[r for r in preg if 2017<=int(r["season"])<=2023]
    val=[r for r in preg if int(r["season"])==2024]
    model=er.fit_ridge(train,selected_l2)
    for r in val:
        r["challenger_snap_share"] = model.predict(r)
        r["diagnostic_history_band"] = history_band(int(r["prior_games"]))
        r["diagnostic_role_band"] = role_band(float(r["baseline_last4_snap_share"]))

    baseline_val=read_csv(base/"omega_2024_player_validation.csv")
    bmap={(r.get("game_id"),r.get("team"),r.get("player_id")):r for r in baseline_val}
    emap={(r.get("game_id"),r.get("team"),r.get("player_id")):r for r in val}
    if len(bmap)!=len(baseline_val): raise SystemExit("FAIL duplicate key in OMEGA 0.2 player validation")
    missing=[k for k in bmap if k not in emap]
    extra=[k for k in emap if k not in bmap]
    if missing or extra:
        raise SystemExit(f"FAIL exposure feature/0.2 validation key mismatch missing={len(missing)} extra={len(extra)}")

    joined=[]
    for k,b in bmap.items():
        e=emap[k]; z=dict(b)
        for name in er.FEATURE_NAMES:
            z[f"exposure_{name}"]=e[name]
        z["challenger_snap_share"]=e["challenger_snap_share"]
        z["baseline_snap_share"]=num(b.get("prior_last4_snap_share"))
        team_snaps=num(b.get("predicted_team_defensive_snaps"))
        rate=num(b.get("shrunk_credit_rate_per_snap"))
        z["challenger_player_defensive_snaps"]=max(0.0,team_snaps*z["challenger_snap_share"])
        z["challenger_xtc"]=max(0.0,z["challenger_player_defensive_snaps"]*rate)
        z["diagnostic_history_band"]=history_band(int(num(b.get("prior_games"))))
        z["diagnostic_role_band"]=role_band(z["baseline_snap_share"])
        joined.append(z)

    snapshare_cmp=compare(joined,"actual_snap_share","challenger_snap_share","baseline_snap_share")
    playersnap_cmp=compare(joined,"actual_defensive_snaps","challenger_player_defensive_snaps","predicted_player_defensive_snaps")
    xtc_cmp=compare(joined,"actual_xtc","challenger_xtc","predicted_xtc")
    xtc_vs_recent=compare(joined,"actual_xtc","challenger_xtc","benchmark_last4_xtc")
    boot=cluster_bootstrap(joined,actual="actual_xtc",challenger="challenger_xtc",baseline="predicted_xtc")
    fold_best=next(x for x in search if float(x["l2"])==selected_l2)

    core=[r for r in joined if str(r.get("position_group")) in {"DB","DL","LB"}]
    slices={
        "byPosition":slice_compare(joined,"position_group","actual_xtc","challenger_xtc","predicted_xtc"),
        "byHistory":slice_compare(joined,"diagnostic_history_band","actual_xtc","challenger_xtc","predicted_xtc"),
        "byBaselineRole":slice_compare(joined,"diagnostic_role_band","actual_xtc","challenger_xtc","predicted_xtc"),
        "coreDefenders":compare(core,"actual_xtc","challenger_xtc","predicted_xtc"),
    }

    predev_ok=float(fold_best["maeImprovementVsLast4"])>0
    point_ok=(snapshare_cmp["maeImprovement"]>0 and playersnap_cmp["maeImprovement"]>0 and xtc_cmp["maeImprovement"]>0)
    ci=boot["maeImprovementCI95"]
    if predev_ok and point_ok and ci[0] > 0:
        verdict="H012_EXPOSURE_CHALLENGER_PASS"
    elif predev_ok and point_ok:
        verdict="H012_DIRECTIONAL_PASS"
    elif snapshare_cmp["maeImprovement"]<=0 and xtc_cmp["maeImprovement"]<=0:
        verdict="H012_FAIL"
    else:
        verdict="H012_MIXED"

    audit={
        "schemaVersion":SCHEMA,"version":er.VERSION,"lineage":er.LINEAGE,"generatedAt":now(),"sourceSnapshotId":sid,
        "integrity":{"omega2025RowsRead":0,"postseasonIncluded":False,"marketFieldsRead":0,"oddsPapiRequests":0,"xTOAddedToPlayerModel":False,"tackleRateChanged":False,"teamSnapModelChanged":False},
        "preRegisteredMechanism":{"id":"H012","name":"Exposure / Role-State Prediction","reasonForPriority":"0.2.1 showed player xTC residual correlation +0.6043 with player snap residual; H011 xTO residual correlation was positive but smaller (+0.2182). Only H012 is changed in this phase.","H011Status":"DEFERRED_NOT_TESTED_IN_0.2.2"},
        "chronology":{"historySeed":2016,"fitSeasons":[2017,2018,2019,2020,2021,2022,2023],"l2SelectionFolds":[2021,2022,2023],"diagnosticDirectedConfirmation":2024,"sealedHoldout":2025},
        "selection":{"selectedL2":selected_l2,"search":search,"featureNames":list(er.FEATURE_NAMES)},
        "samples":{"pregameRows":len(preg),"fitRows2017To2023":len(train),"validationRows2024":len(joined)},
        "validation2024":{"snapShare":snapshare_cmp,"playerDefensiveSnaps":playersnap_cmp,"xTC_vs_0.2":xtc_cmp,"xTC_vs_last4":xtc_vs_recent,"xTCGameClusterBootstrap_vs_0.2":boot,"slices":slices},
        "verdict":verdict,
        "interpretation":"2024 is not a pristine new holdout because 0.2.1 diagnostics were used to prioritize H012. Hyperparameters/features are nevertheless selected without 2024 target optimization. 2025 remains the sealed OMEGA holdout.",
        "nextGate":"If H012 passes, freeze the exposure challenger as the exposure component and test H011 opportunity-density coupling next, still without opening 2025 or market data. If H012 fails/mixes, inspect role-history slices before adding complexity.",
    }

    outbase=root/"data/models/nfl/omega_tackle_022_exposure"
    out=outbase/sid
    if out.exists(): raise SystemExit(f"Refusing overwrite immutable OMEGA 0.2.2 output: {out}")
    staging=outbase/("."+sid+".staging"); staging.mkdir(parents=True,exist_ok=False)
    try:
        write_csv(staging/"omega_2024_exposure_challenger_validation.csv",joined)
        (staging/"omega_exposure_role_model.json").write_text(json.dumps(model.to_dict(),indent=2)+"\n",encoding="utf-8")
        (staging/"OMEGA_0.2.2_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        def cfmt(x): return f"[{x[0]:+.4f}, {x[1]:+.4f}]"
        lines=[
            "# OMEGA Tackle Model 0.2.2 — Exposure / Role Challenger Audit","",
            f"Generated: {audit['generatedAt']}","",
            "**SINGLE-MECHANISM CHALLENGER. H012 ONLY. NO MARKET DATA. OMEGA 2025 REMAINS SEALED.**","",
            "## Decision from 0.2.1","",
            "The 0.2.1 diagnostic showed a materially stronger relationship between xTC residuals and player exposure error than between xTC residuals and team xTO error. Therefore H012 is tested first; H011 is explicitly deferred.","",
            "## Integrity","",
            f"- Source snapshot: `{sid}`",
            "- 2025 tackle rows read: **0**",
            "- Market fields read: **0**",
            "- OddsPapi requests: **0**",
            "- xTO added to player model: **NO**",
            "- 0.2 tackle-credit rate changed: **NO**",
            "- 0.2 team defensive-snap model changed: **NO**","",
            "## Chronological selection","",
            f"- Exposure ridge L2 selected on 2021–2023 folds only: **{selected_l2}**",
            f"- Selected-fold mean snap-share MAE improvement vs last-4 exposure baseline: **{fold_best['maeImprovementVsLast4']:+.5f}**",
            "- Final exposure fit: **2017–2023**",
            "- 2024: **diagnostic-directed confirmation** (not a pristine holdout)",
            "- 2025: **SEALED OMEGA HOLDOUT**","",
            "## 2024 exposure validation","",
            f"- Snap-share MAE: challenger **{snapshare_cmp['challenger']['mae']:.5f}** vs baseline **{snapshare_cmp['baseline']['mae']:.5f}** · improvement **{snapshare_cmp['maeImprovement']:+.5f}** ({snapshare_cmp['maeImprovementPct']:+.2f}%)",
            f"- Player defensive-snap MAE: challenger **{playersnap_cmp['challenger']['mae']:.4f}** vs 0.2 **{playersnap_cmp['baseline']['mae']:.4f}** · improvement **{playersnap_cmp['maeImprovement']:+.4f}** ({playersnap_cmp['maeImprovementPct']:+.2f}%)","",
            "## 2024 xTC effect with all non-exposure components frozen","",
            f"- xTC MAE: challenger **{xtc_cmp['challenger']['mae']:.4f}** vs OMEGA 0.2 **{xtc_cmp['baseline']['mae']:.4f}** · improvement **{xtc_cmp['maeImprovement']:+.4f}** ({xtc_cmp['maeImprovementPct']:+.2f}%)",
            f"- xTC RMSE improvement vs OMEGA 0.2: **{xtc_cmp['rmseImprovement']:+.4f}**",
            f"- Paired game-cluster bootstrap xTC MAE Δ (0.2 - challenger): **{boot['maeImprovementPoint']:+.4f}**, 95% CI **{cfmt(boot['maeImprovementCI95'])}**, P(Δ>0) **{boot['probabilityPositive']:.3f}**",
            f"- Challenger xTC MAE vs raw last-4 tackle average: **{xtc_vs_recent['challenger']['mae']:.4f}** vs **{xtc_vs_recent['baseline']['mae']:.4f}**","",
            "## Verdict","",
            f"**{verdict}**","",
            "This phase tests whether better role/exposure forecasting improves tackle-count prediction. It does not test sportsbook edge and does not test H011/xTO coupling.","",
            "## Next gate","",
            audit['nextGate'],"",
        ]
        (staging/"OMEGA_0.2.2_AUDIT.md").write_text("\n".join(lines),encoding="utf-8")
        files=[]
        for p in sorted(staging.iterdir()):
            if p.is_file(): files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
        (staging/"OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"createdAt":now(),"files":files},indent=2)+"\n",encoding="utf-8")
        os.replace(staging,out)
        (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE_CHALLENGER").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

    print("OMEGA 0.2.2 EXPOSURE / ROLE CHALLENGER")
    print(f"PASS source snapshot: {sid}")
    print(f"PASS selected exposure L2 (2021-2023 only): {selected_l2}")
    print(f"2024 snap-share MAE improvement: {snapshare_cmp['maeImprovement']:+.5f}")
    print(f"2024 xTC MAE improvement vs 0.2: {xtc_cmp['maeImprovement']:+.5f}")
    print(f"2024 xTC cluster bootstrap 95% CI: {boot['maeImprovementCI95']}")
    print(f"VERDICT: {verdict}")
    print("PASS OMEGA 2025 untouched · market fields 0 · OddsPapi 0 · H011 deferred")
    print(f"REPORT: {out/'OMEGA_0.2.2_AUDIT.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

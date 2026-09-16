#!/usr/bin/env python3
"""OMEGA 0.30 — immutable Week 1 evaluation and Week 2 decision audit.

Scores the untouched frozen 0.16 Week-1 ledger across all six games, then reports
prospective challenger evidence (DAL-NYG 0.24 and DEN-KC 0.29) separately.  This is
an evaluation utility only: no model fitting, coefficient changes, market reads, or
writes to frozen OMEGA artifacts.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse, csv, hashlib, importlib.util, json, math, os, shutil

SCHEMA = "OMEGA_WEEK1_EVALUATION_0.30.0"
EXPECTED_LEDGER_SHA = "e81f4298e46f96e44e155ee186cb8c738e447048a0a5d8624065365e4e9a264b"
TARGET_GAMES = {
    "2026_01_ARI_LAC", "2026_01_GB_MIN", "2026_01_MIA_LV",
    "2026_01_WAS_PHI", "2026_01_DAL_NYG", "2026_01_DEN_KC",
}
DAL_CHALLENGER_ID = "20260914T013816Z_c4c00033"
DEN_FREEZE_ID = "20260915T001242Z_62e5b31c"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def rcsv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def wcsv(path: Path, rows):
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    if not fields:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def num(v, default=None):
    try:
        if v in (None, ""):
            return default
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def truth(v):
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "pass", "ready"}


def safe_logloss(p, y):
    p = max(1e-12, min(1 - 1e-12, float(p)))
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def metrics(rows, pred="predicted_xtc", actual="actual_xtc"):
    z = [r for r in rows if num(r.get(pred)) is not None and num(r.get(actual)) is not None]
    if not z:
        return {"n": 0}
    ys = [float(r[actual]) for r in z]
    ps = [float(r[pred]) for r in z]
    return {
        "n": len(z),
        "actualMean": fmean(ys),
        "predictedMean": fmean(ps),
        "mae": fmean(abs(y-p) for y,p in zip(ys,ps)),
        "rmse": math.sqrt(fmean((y-p)**2 for y,p in zip(ys,ps))),
        "biasPredMinusActual": fmean(p-y for y,p in zip(ys,ps)),
    }


def pearson(xs, ys):
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = fmean(xs), fmean(ys)
    dx, dy = [x-mx for x in xs], [y-my for y in ys]
    den = math.sqrt(sum(x*x for x in dx) * sum(y*y for y in dy))
    return sum(x*y for x,y in zip(dx,dy))/den if den > 0 else None


def normalize_pct(v):
    x = num(v)
    if x is None or x < 0:
        return None
    if x > 1.5:
        x /= 100.0
    return max(0.0, min(1.0, x)) if x <= 1.05 else None


def load_score_lib(root: Path):
    p = root / "scripts/nfl/score_omega_prospective_eval_0230.py"
    spec = importlib.util.spec_from_file_location("omega_score023_week1", p)
    if spec is None or spec.loader is None:
        raise SystemExit("FAIL cannot load OMEGA 0.23 scorer")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def resolve_results_manifest(root: Path, arg: str):
    if arg:
        return Path(arg).expanduser().resolve()
    ptr = root / "data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST"
    if not ptr.exists():
        raise SystemExit("FAIL no dedicated 2026 results manifest")
    v = ptr.read_text().strip()
    return Path(v) if v.startswith("/") else root / v


def resolve_snap_manifest(root: Path, arg: str):
    if arg:
        return Path(arg).expanduser().resolve()
    ptr = root / "data/raw/nfl/omega/CURRENT_OMEGA_2026_SNAP_COUNTS"
    if not ptr.exists():
        return None
    sid = ptr.read_text().strip()
    return root / "data/raw/nfl/omega/snap_count_results_0290" / sid / "SNAP_COUNTS_RESULTS_MANIFEST.json"


def locate_ledger(root: Path):
    base = root / "data/prospective/nfl/omega/tackle_probability_016"
    matches = []
    if base.exists():
        for p in base.glob("*/OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv"):
            if sha(p) == EXPECTED_LEDGER_SHA:
                matches.append(p)
    if len(matches) != 1:
        raise SystemExit(f"FAIL expected frozen Week-1 ledger SHA found {len(matches)} times")
    return matches[0]


def load_snap_actuals_all(root: Path, snap_manifest: Path | None, source_meta):
    if snap_manifest is None or not snap_manifest.exists():
        return {}, {"status": "UNAVAILABLE"}
    import pyarrow.parquet as pq
    sm = json.loads(snap_manifest.read_text())
    sp = snap_manifest.parent / "snap_counts_2026.parquet"
    if not sp.exists() or sha(sp) != sm.get("sha256"):
        raise SystemExit("FAIL snap-count file/hash mismatch")
    players = next((x for x in source_meta.get("assets", []) if x.get("source") == "players"), None)
    if not players:
        raise SystemExit("FAIL results source lacks players identity asset")
    pp = root / str(players.get("blobPath") or "")
    if not pp.exists() or sha(pp) != players.get("sha256"):
        raise SystemExit("FAIL players asset/hash mismatch")
    pf = pq.ParquetFile(pp)
    names = set(pf.schema_arrow.names)
    pfrcol = "pfr_id" if "pfr_id" in names else ("pfr_player_id" if "pfr_player_id" in names else "")
    if not pfrcol or "gsis_id" not in names:
        raise SystemExit("FAIL players asset lacks GSIS/PFR bridge")
    pmap = {
        str(r.get(pfrcol) or "").strip(): str(r.get("gsis_id") or "").strip()
        for r in pf.read(columns=["gsis_id", pfrcol]).to_pylist()
        if r.get(pfrcol) and r.get("gsis_id")
    }
    sf = pq.ParquetFile(sp)
    rows = sf.read(columns=["game_id","pfr_player_id","team","defense_snaps","defense_pct"]).to_pylist()
    out = {}; target = bridged = 0
    for r in rows:
        gid = str(r.get("game_id") or "")
        if gid not in TARGET_GAMES:
            continue
        target += 1
        gsis = pmap.get(str(r.get("pfr_player_id") or "").strip(), "")
        if not gsis:
            continue
        bridged += 1
        out[(gid, gsis)] = {
            "actual_snap_share": normalize_pct(r.get("defense_pct")),
            "actual_defense_snaps": num(r.get("defense_snaps"), 0.0),
        }
    return out, {"status":"AVAILABLE","snapshotId":sm.get("snapshotId"),"sha256":sm.get("sha256"),"targetRows":target,"bridgedRows":bridged}


def latest_json_under(base: Path, filename: str):
    if not base.exists():
        return None, None
    found = []
    for p in base.glob(f"*/{filename}"):
        try:
            found.append((p.parent.name, p, json.loads(p.read_text())))
        except Exception:
            pass
    if not found:
        return None, None
    found.sort(key=lambda x: x[0])
    return found[-1][1], found[-1][2]


def game_metrics(scored):
    out = []
    for gid in sorted(TARGET_GAMES):
        z = [r for r in scored if r["game_id"] == gid]
        m = metrics(z)
        probs = [float(r["threshold_brier_mean"]) for r in z]
        out.append({"game_id":gid, **m, "thresholdBrier":fmean(probs) if probs else None,
                    "playedDefense":sum(r.get("snap_status")=="PLAYED_DEFENSE" for r in z),
                    "noDefenseSnap":sum(r.get("snap_status")=="NO_DEFENSE_SNAP" for r in z)})
    return out


def segment_rows(scored, field):
    out = []
    vals = sorted({str(r.get(field) or "MISSING") for r in scored})
    for v in vals:
        z = [r for r in scored if str(r.get(field) or "MISSING") == v]
        m = metrics(z)
        out.append({"segment":field,"value":v,**m})
    return out


def pct(x):
    return "NA" if x is None else f"{100*x:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--source-manifest", default="")
    ap.add_argument("--snap-manifest", default="")
    a = ap.parse_args(); root = Path(a.root).expanduser().resolve()

    ledger = locate_ledger(root)
    forecasts = [r for r in rcsv(ledger) if int(num(r.get("season"),0)) == 2026 and int(num(r.get("week"),0)) == 1]
    games = {r.get("game_id") for r in forecasts}
    if games != TARGET_GAMES:
        raise SystemExit(f"FAIL frozen ledger games mismatch: {sorted(games)}")
    if len(forecasts) != 294:
        raise SystemExit(f"FAIL expected 294 frozen Week-1 rows; got {len(forecasts)}")

    lib = load_score_lib(root)
    source_path = resolve_results_manifest(root, a.source_manifest)
    source_manifest, smeta, pbp_asset, pbp_path, sched_path = lib.locate_source(root, str(source_path))
    complete = lib.completed_games_from_schedule(sched_path, TARGET_GAMES)
    if complete != TARGET_GAMES:
        raise SystemExit(f"FAIL not all Week-1 games complete: missing {sorted(TARGET_GAMES-complete)}")
    actual, seen, pbp_audit = lib.reconstruct_actuals(root, pbp_path, TARGET_GAMES)
    if seen != TARGET_GAMES:
        raise SystemExit(f"FAIL PBP missing Week-1 games: {sorted(TARGET_GAMES-seen)}")

    snap_manifest = resolve_snap_manifest(root, a.snap_manifest)
    snap_actuals, snap_audit = load_snap_actuals_all(root, snap_manifest, smeta)

    scored = []; all_brier = []; all_logloss = []
    for r in forecasts:
        x = dict(r); key = (r["game_id"], r["player_id"])
        y = int(actual.get(key, 0)); pred = float(r.get("predicted_xtc") or 0)
        x.update({"actual_xtc":y,"residual_actual_minus_pred":y-pred,"abs_error":abs(y-pred),"squared_error":(y-pred)**2})
        bs = []; ls = []
        for whole in range(15):
            line = whole + 0.5; tag = str(line).replace(".", "_")
            p = float(r[f"p_over_{tag}"]); event = 1.0 if y > line else 0.0
            bs.append((p-event)**2); ls.append(safe_logloss(p,event))
            all_brier.append((p-event)**2); all_logloss.append(safe_logloss(p,event))
        x["threshold_brier_mean"] = fmean(bs); x["threshold_logloss_mean"] = fmean(ls)
        sa = snap_actuals.get(key)
        if sa and sa.get("actual_snap_share") is not None:
            s = float(sa["actual_snap_share"]); sn = float(sa.get("actual_defense_snaps") or 0)
            x["actual_snap_share"] = s; x["actual_defense_snaps"] = sn
            x["snap_status"] = "PLAYED_DEFENSE" if sn > 0 else "NO_DEFENSE_SNAP"
            ps = num(r.get("predicted_snap_share"))
            if ps is not None:
                x["snap_residual_actual_minus_pred"] = s-ps
                x["snap_abs_error"] = abs(s-ps)
        else:
            x["actual_snap_share"] = ""; x["actual_defense_snaps"] = ""; x["snap_status"] = "MISSING_SNAP_COUNT"
        scored.append(x)

    all_m = metrics(scored)
    played = [r for r in scored if r.get("snap_status") == "PLAYED_DEFENSE"]
    played_m = metrics(played)
    no_snap = [r for r in scored if r.get("snap_status") == "NO_DEFENSE_SNAP"]
    research_ready = [r for r in scored if truth(r.get("research_ready")) or truth(r.get("researchReady"))]
    snap_rows = [r for r in played if num(r.get("predicted_snap_share")) is not None and num(r.get("actual_snap_share")) is not None]
    snap_m = metrics(snap_rows, pred="predicted_snap_share", actual="actual_snap_share")
    xs = [float(r["snap_abs_error"]) for r in snap_rows if num(r.get("snap_abs_error")) is not None]
    ys = [float(r["abs_error"]) for r in snap_rows if num(r.get("snap_abs_error")) is not None]
    snap_tackle_corr = pearson(xs, ys)
    low_snap_err = [r for r in snap_rows if float(r.get("snap_abs_error") or 0) < .10]
    high_snap_err = [r for r in snap_rows if float(r.get("snap_abs_error") or 0) >= .20]

    games_out = game_metrics(scored)
    segments = []
    for fld in ("position_group", "role_tier", "availability_status"):
        if any(r.get(fld) not in (None,"") for r in scored):
            segments.extend(segment_rows(scored, fld))

    dal_path, dal = latest_json_under(root/"data/results/nfl/omega_role_adjusted_challenger_0240"/DAL_CHALLENGER_ID,
                                      "OMEGA_0.24_ROLE_ADJUSTED_SCORE_REPORT.json")
    den_path, den = latest_json_under(root/"data/results/nfl/omega_current_role_snap_0290"/DEN_FREEZE_ID,
                                      "OMEGA_0.29_CURRENT_ROLE_SNAP_SCORE_REPORT.json")
    if dal is None:
        raise SystemExit("FAIL DAL-NYG 0.24 prospective challenger score not found")
    if den is None:
        raise SystemExit("FAIL DEN-KC 0.29 prospective challenger score not found")

    den_tc = den.get("tackleCount", {}); den_snap = den.get("snapShareConditionalOnPlaying", {})
    role_point_snap_improved = (
        den_snap.get("h012Point",{}).get("mae") is not None and
        den_snap.get("rolePoint",{}).get("mae") is not None and
        den_snap["rolePoint"]["mae"] < den_snap["h012Point"]["mae"]
    )
    mixture_improved = (
        den_tc.get("originalH012",{}).get("mae") is not None and
        den_tc.get("snapMixtureMean",{}).get("mae") is not None and
        den_tc["snapMixtureMean"]["mae"] < den_tc["originalH012"]["mae"] and
        den_tc.get("thresholdBrier",{}).get("improvement",0) > 0
    )
    coverage = den_snap.get("intervalCoverage", {})
    tails_undercover = ((coverage.get("80") is not None and coverage["80"] < .74) or
                        (coverage.get("90") is not None and coverage["90"] < .84))

    week2 = {
        "baselineOmega": "KEEP_FROZEN_AS_WEEK2_CONTROL",
        "currentRolePoint": "PARALLEL_CHALLENGER_NOT_PROMOTED",
        "snapDistributionMixture": "RESEARCH_ONLY_NOT_PROMOTED" if not mixture_improved else "PARALLEL_CHALLENGER_NOT_PROMOTED",
        "roleConflictPolicy": "QUARANTINE_RAW_MARKET_SIGNAL_PENDING_ROLE_REVIEW",
        "backupConflictPolicy": "REVIEW_ONLY_NO_AUTOMATIC_CORRECTION",
        "freezeOrder": "FREEZE_BASELINE_AND_CHALLENGER_BEFORE_MARKET_CAPTURE",
        "week2Evaluation": "SCORE_ALL_FORECASTS_AND_ALL_GAMES_SEPARATELY_FROM_BETTING_PORTFOLIO",
        "developmentPriority": "RECALIBRATE_SNAP_DISTRIBUTION_TAILS_ON_HISTORICAL_OOF_ONLY" if tails_undercover else "CONTINUE_PROSPECTIVE_ROLE_VALIDATION",
        "promotionRule": "NO_PROMOTION_FROM_WEEK1_SINGLE_GAME_CHALLENGER_EVIDENCE",
    }

    report = {
        "schemaVersion": SCHEMA,
        "generatedAt": now(),
        "season": 2026, "week": 1,
        "status": "COMPLETE_IMMUTABLE_WEEK1_EVALUATION",
        "integrity": {
            "frozenOmegaLedgerModified": False, "modelRefitOnWeek1Results": False,
            "marketFieldsReadForModelScoring": 0, "oddsPapiRequests": 0,
            "sourceLedgerSha256": sha(ledger), "expectedLedgerSha256": EXPECTED_LEDGER_SHA,
        },
        "coverage": {
            "games": len(TARGET_GAMES), "forecastRows": len(scored),
            "thresholdForecastsOverOnly": 15*len(scored), "playedDefenseRows": len(played),
            "noDefenseSnapRows": len(no_snap), "snapRowsGradedConditionalOnPlaying": len(snap_rows),
            "researchReadyRowsDetected": len(research_ready),
        },
        "source": {
            "resultsSnapshotId": smeta.get("snapshotId"), "pbpSha256": pbp_asset.get("sha256"),
            "pbpAudit": pbp_audit, "snapCounts": snap_audit,
        },
        "untouchedOmega": {
            "allFrozenForecasts": all_m,
            "playedDefenseOnly": played_m,
            "researchReadyOnly": metrics(research_ready) if research_ready else {"n":0},
            "thresholdBrier": fmean(all_brier), "thresholdLogLoss": fmean(all_logloss),
            "conditionalSnapShare": snap_m,
            "snapErrorVsTackleAbsErrorPearson": snap_tackle_corr,
            "tackleMAEWhenSnapAbsErrorLt10pp": metrics(low_snap_err).get("mae"),
            "tackleMAEWhenSnapAbsErrorGe20pp": metrics(high_snap_err).get("mae"),
            "nSnapAbsErrorLt10pp": len(low_snap_err), "nSnapAbsErrorGe20pp": len(high_snap_err),
        },
        "prospectiveChallengers": {
            "dalNygManualRole024": {
                "scoreReport": str(dal_path.relative_to(root)),
                "players": dal.get("coverage",{}).get("players"),
                "original": dal.get("originalOmegaMetrics"), "adjusted": dal.get("roleAdjustedMetrics"),
                "improvement": dal.get("improvement"), "thresholdBrier": dal.get("thresholdBrier"),
                "scope": "12_PLAYER_PREGAME_CHALLENGER_NOT_FULL_SLATE",
            },
            "denKcCurrentRole028": {
                "scoreReport": str(den_path.relative_to(root)),
                "coverage": den.get("coverage"), "tackleCount": den_tc,
                "snapShareConditionalOnPlaying": den_snap,
                "rolePointSnapMAEImproved": role_point_snap_improved,
                "snapMixtureTackleImproved": mixture_improved,
                "scope": "48_PLAYER_FULL_GAME_PROSPECTIVE_CHALLENGER",
            },
        },
        "week2OperatingDecision": week2,
        "interpretation": [
            "Untouched OMEGA Week-1 performance is the primary benchmark and includes all frozen forecasts, not selected bets.",
            "Played-defense metrics separate conditional tackle forecasting from availability/no-play failures.",
            "DAL-NYG and DEN-KC challengers remain separate prospective experiments and are not merged into baseline Week-1 metrics.",
            "Betting outcomes are not used to promote or fit the model; portfolio ROI must be tracked separately.",
        ],
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sid = f"{stamp}_{str(pbp_asset.get('sha256') or '')[:8]}"
    base = root/"data/results/nfl/omega_week1_evaluation_0300"/"2026_week1"
    final = base/sid; staging = base/("."+sid+".staging")
    base.mkdir(parents=True, exist_ok=True)
    if final.exists() or staging.exists():
        raise SystemExit("FAIL duplicate Week-1 evaluation id")
    staging.mkdir(parents=True)
    try:
        wcsv(staging/"OMEGA_0.30_WEEK1_PLAYER_SCORES.csv", scored)
        wcsv(staging/"OMEGA_0.30_WEEK1_GAME_SUMMARY.csv", games_out)
        wcsv(staging/"OMEGA_0.30_WEEK1_SEGMENT_SUMMARY.csv", segments)
        rp = staging/"OMEGA_0.30_WEEK1_EVALUATION_REPORT.json"
        rp.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
        md = staging/"OMEGA_0.30_WEEK1_EVALUATION_REPORT.md"
        lines = [
            "# OMEGA 0.30 — Week 1 Evaluation", "",
            f"Generated: {report['generatedAt']}", "",
            "## Untouched frozen OMEGA", "",
            f"- Games: 6 · Forecast rows: {len(scored)} · Over-threshold probability forecasts: {15*len(scored)}",
            f"- All forecasts: MAE {all_m['mae']:.3f} · RMSE {all_m['rmse']:.3f} · bias {all_m['biasPredMinusActual']:+.3f}",
            f"- Threshold Brier: {fmean(all_brier):.4f} · log loss {fmean(all_logloss):.4f}",
            f"- Played-defense only: n {len(played)} · MAE {played_m['mae']:.3f} · RMSE {played_m['rmse']:.3f}",
            f"- Conditional snap-share: n {snap_m['n']} · MAE {snap_m.get('mae',float('nan')):.4f}",
            f"- |snap error| vs |T+A error| Pearson: {snap_tackle_corr if snap_tackle_corr is not None else 'NA'}",
            "", "## Prospective challengers", "",
            f"- DAL-NYG 0.24 (12 players): MAE improvement {dal.get('improvement',{}).get('mae')} · Brier improvement {dal.get('improvement',{}).get('thresholdBrier')}",
            f"- DEN-KC 0.2.8 (48 players): original MAE {den_tc.get('originalH012',{}).get('mae')} -> mixture {den_tc.get('snapMixtureMean',{}).get('mae')}",
            f"- DEN-KC snap point MAE: H012 {den_snap.get('h012Point',{}).get('mae')} -> role {den_snap.get('rolePoint',{}).get('mae')} -> distribution mean {den_snap.get('distributionMean',{}).get('mae')}",
            f"- DEN-KC interval coverage 50/80/90: {pct(coverage.get('50'))}/{pct(coverage.get('80'))}/{pct(coverage.get('90'))}",
            "", "## Week 2 operating decision", "",
        ]
        for k,v in week2.items():
            lines.append(f"- **{k}**: {v}")
        lines += ["", "No Week-1 outcome is used to refit frozen OMEGA in this report."]
        md.write_text("\n".join(lines)+"\n", encoding="utf-8")
        hashes = {p.name:sha(p) for p in staging.iterdir() if p.is_file()}
        (staging/"OMEGA_0.30_WEEK1_EVALUATION_HASHES.json").write_text(json.dumps(hashes,indent=2)+"\n")
        os.replace(staging, final)
        ptr = root/"data/results/nfl/omega/CURRENT_OMEGA_WEEK1_EVALUATION"
        ptr.parent.mkdir(parents=True, exist_ok=True)
        tmp = ptr.with_name("."+ptr.name+".tmp"); tmp.write_text(f"2026_week1/{sid}\n"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True); raise

    print("OMEGA 0.30 — WEEK 1 EVALUATION / WEEK 2 DECISION AUDIT")
    print(f"PASS complete slate · games 6 · frozen forecasts {len(scored)} · thresholds {15*len(scored)}")
    print(f"UNTOUCHED OMEGA ALL:    MAE {all_m['mae']:.3f} · RMSE {all_m['rmse']:.3f} · bias {all_m['biasPredMinusActual']:+.3f} · Brier {fmean(all_brier):.4f}")
    print(f"UNTOUCHED OMEGA PLAYED: n {len(played)} · MAE {played_m['mae']:.3f} · RMSE {played_m['rmse']:.3f}")
    if snap_m.get('n'):
        print(f"H012 SNAP SHARE:        n {snap_m['n']} · MAE {snap_m['mae']:.4f} · RMSE {snap_m['rmse']:.4f}")
        if snap_tackle_corr is not None:
            print(f"SNAP↔T+A ERROR:         Pearson |snap error| vs |T+A error| {snap_tackle_corr:+.3f}")
        print(f"T+A MAE BY SNAP ERROR:  <10pp n {len(low_snap_err)} MAE {metrics(low_snap_err).get('mae',float('nan')):.3f} · >=20pp n {len(high_snap_err)} MAE {metrics(high_snap_err).get('mae',float('nan')):.3f}")
    di = dal.get('improvement',{})
    print(f"DAL-NYG 0.24:           12-player MAE improvement {di.get('mae',0):+.3f} · Brier {di.get('thresholdBrier',0):+.4f}")
    doi = den_tc.get('originalH012',{}); dmi = den_tc.get('snapMixtureMean',{})
    print(f"DEN-KC 0.2.8:          T+A MAE {doi.get('mae',float('nan')):.3f}->{dmi.get('mae',float('nan')):.3f} · mixture promoted NO")
    if den_snap:
        print(f"DEN-KC SNAP:            H012 {den_snap.get('h012Point',{}).get('mae',float('nan')):.4f} -> role {den_snap.get('rolePoint',{}).get('mae',float('nan')):.4f} -> dist {den_snap.get('distributionMean',{}).get('mae',float('nan')):.4f}")
        print(f"DEN-KC COVERAGE:        50/80/90 {pct(coverage.get('50'))}/{pct(coverage.get('80'))}/{pct(coverage.get('90'))}")
    print("WEEK 2: baseline OMEGA stays frozen control · current-role point runs parallel · snap-mixture research-only · role conflicts quarantined")
    print("PASS refits 0 · market fields read for scoring 0 · OMEGA writes 0")
    print(f"REPORT: {final/'OMEGA_0.30_WEEK1_EVALUATION_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

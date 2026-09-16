#!/usr/bin/env python3
"""OMEGA 0.31 — one-time component-level 2025 current-role point holdout.

This evaluator is downstream research only.  It loads the already-fitted OMEGA 0.2.7
RoleCorrectionModel, the immutable OMEGA 0.12 blind-2025 H012 snap-share ledger, and
strictly pregame weekly depth state.  It never refits either model.  Realized 2025
snap shares are used only as targets and as strictly-prior state for later 2025 weeks.

Important: 2025 was previously consumed by the project for the older OMEGA 0.13
T+A holdout.  This is therefore a component-level confirmatory test of the 0.2.7
current-role correction, not a claim that 2025 is globally virgin to the project.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Callable, Sequence
import argparse
import csv
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

SCHEMA = "OMEGA_CURRENT_ROLE_2025_CONFIRMATORY_HOLDOUT_0.31.0"
EXPECTED_SID = "20260910T205221Z_58d8156a"
EXPECTED_BLIND_SHA256 = "59c1a1726bb705661babe3f51fc408e389a25bece6a18df0fdf79065b08d036e"
EXPECTED_ROWS = 10524
EXPECTED_GAMES = 272
EXPECTED_WEEKS = tuple(range(1, 19))
EXPECTED_ROLE_ARTIFACT = "20260910T205221Z_58d8156a__20260914T222159Z_8f6be75b"
EXPECTED_DEPTH_AUDIT = "20260914T222159Z_8f6be75b"
PROTOCOL_PATH = "docs/architecture/OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_PROTOCOL.md"
EXPECTED_PROTOCOL_GIT_BLOB_SHA1 = "efed95e8e165ffd626600ca312514f87a12be2ac"
DEPTH_2025_URL = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2025.parquet"
BOOTSTRAP_REPS = 10000
BOOTSTRAP_SEED = 310031
MIN_GATE_N = 30


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def rcsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def wcsv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or ["status"], extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def num(v: Any, default: float | None = None) -> float | None:
    if v in (None, ""):
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def truthy(v: Any) -> bool:
    x = num(v)
    if x is not None:
        return int(x) != 0
    return str(v or "").strip().lower() in {"true", "yes", "y", "t"}


def normteam(v: Any) -> str:
    x = str(v or "").strip().upper()
    return {"JAX": "JAC", "LAR": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}.get(x, x)


def percentile(xs: Sequence[float], q: float) -> float:
    z = sorted(float(x) for x in xs)
    if not z:
        raise ValueError("empty percentile")
    p = max(0.0, min(1.0, float(q))) * (len(z) - 1)
    lo, hi = int(math.floor(p)), int(math.ceil(p))
    if lo == hi:
        return z[lo]
    w = p - lo
    return z[lo] * (1.0 - w) + z[hi] * w


def metrics(rows: Sequence[dict[str, Any]], pred: str) -> dict[str, Any]:
    if not rows:
        return {"n": 0}
    ys = [float(r["actual_snap_share"]) for r in rows]
    ps = [float(r[pred]) for r in rows]
    return {
        "n": len(rows),
        "actualMean": fmean(ys),
        "predictedMean": fmean(ps),
        "mae": fmean(abs(y-p) for y, p in zip(ys, ps)),
        "rmse": math.sqrt(fmean((y-p)**2 for y, p in zip(ys, ps))),
        "biasPredMinusActual": fmean(p-y for y, p in zip(ys, ps)),
    }


def compare(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    h = metrics(rows, "h012_snap_share")
    r = metrics(rows, "role_snap_share")
    return {
        "n": len(rows),
        "h012": h,
        "role": r,
        "maeImprovement": h["mae"] - r["mae"],
        "rmseImprovement": h["rmse"] - r["rmse"],
        "biasChangeRoleMinusH012": r["biasPredMinusActual"] - h["biasPredMinusActual"],
    }


def cluster_bootstrap(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by: dict[str, tuple[int, float, float]] = {}
    tmp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        tmp[str(r["game_id"])].append(r)
    for gid, rr in tmp.items():
        by[gid] = (
            len(rr),
            sum(abs(float(x["actual_snap_share"]) - float(x["h012_snap_share"])) for x in rr),
            sum(abs(float(x["actual_snap_share"]) - float(x["role_snap_share"])) for x in rr),
        )
    keys = sorted(by)
    if len(keys) != EXPECTED_GAMES:
        raise SystemExit(f"FAIL bootstrap game coverage {len(keys)} != {EXPECTED_GAMES}")
    rng = random.Random(BOOTSTRAP_SEED)
    draws: list[float] = []
    for _ in range(BOOTSTRAP_REPS):
        n = hb = rr = 0.0
        for _j in range(len(keys)):
            nn, hsum, rsum = by[keys[rng.randrange(len(keys))]]
            n += nn; hb += hsum; rr += rsum
        draws.append((hb - rr) / n)
    point = compare(rows)["maeImprovement"]
    return {
        "cluster": "game_id",
        "clusters": len(keys),
        "reps": BOOTSTRAP_REPS,
        "seed": BOOTSTRAP_SEED,
        "maeImprovementPoint": point,
        "maeImprovementCI95": [percentile(draws, .025), percentile(draws, .975)],
        "probabilityPositive": sum(x > 0 for x in draws) / len(draws),
    }


def load_player_bridge(root: Path, sid: str) -> tuple[dict[str, str], dict[str, dict[str, str]], dict[str, Any]]:
    import pyarrow.parquet as pq
    mp = root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json"
    if not mp.exists():
        raise SystemExit(f"FAIL source manifest missing: {mp}")
    sm = json.loads(mp.read_text(encoding="utf-8"))
    pa = next((a for a in sm.get("assets", []) if a.get("source") == "players"), None)
    if not pa:
        raise SystemExit("FAIL source manifest lacks players asset")
    pp = root / str(pa.get("blobPath") or "")
    if not pp.exists() or sha256_file(pp) != pa.get("sha256"):
        raise SystemExit("FAIL players asset hash mismatch")
    pf = pq.ParquetFile(pp); names = set(pf.schema_arrow.names)
    pfrcol = "pfr_id" if "pfr_id" in names else ("pfr_player_id" if "pfr_player_id" in names else "")
    if not pfrcol or "gsis_id" not in names:
        raise SystemExit("FAIL players asset lacks GSIS/PFR bridge")
    cols = [x for x in ("gsis_id", pfrcol, "display_name", "position", "position_group") if x in names]
    p2g: dict[str, str] = {}; meta: dict[str, dict[str, str]] = {}
    for r in pf.read(columns=cols).to_pylist():
        gsis = str(r.get("gsis_id") or "").strip(); pfr = str(r.get(pfrcol) or "").strip()
        if not gsis:
            continue
        meta[gsis] = {
            "display_name": str(r.get("display_name") or "").strip(),
            "position": str(r.get("position") or "").strip(),
            "position_group": str(r.get("position_group") or "").strip(),
            "pfr_id": pfr,
        }
        if pfr:
            p2g[pfr] = gsis
    return p2g, meta, sm


def locate_2025_snap_asset(root: Path, sid: str, required_sha: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    base = root / "data/raw/nfl/nflverse/phase2f_holdout/snapshots"
    found: list[tuple[str, Path, dict[str, Any], dict[str, Any]]] = []
    for mp in base.glob("*/SOURCE_MANIFEST.json"):
        try:
            m = json.loads(mp.read_text(encoding="utf-8")); a = m.get("asset", {})
            if m.get("sourcePhase1SnapshotId") != sid or int(m.get("season") or 0) != 2025:
                continue
            p = root / str(a.get("blobPath") or "")
            if p.exists() and sha256_file(p) == a.get("sha256"):
                found.append((str(m.get("createdAt") or ""), p, a, m))
        except Exception:
            continue
    exact = [x for x in found if str(x[2].get("sha256") or "") == required_sha]
    if not exact:
        raise SystemExit(f"FAIL exact blind-build 2025 snap asset not found: {required_sha}")
    _, path, asset, manifest = sorted(exact)[-1]
    return path, asset, manifest


def download_or_reuse_2025_depth(root: Path) -> tuple[Path, str, str]:
    # 0.2.8 may already have admitted the same 2025 file as strictly-prior 2026 state.
    candidates = sorted((root / "data/raw/nfl/omega/prospective_prior_state_2026").glob("*/depth_charts_2025.parquet"))
    for p in reversed(candidates):
        if p.exists() and p.stat().st_size > 0:
            return p, sha256_file(p), "REUSED_0.2.8_PRIOR_STATE"
    cache = root / "data/raw/nfl/omega/confirmatory_2025_depth_0310"
    existing = sorted(cache.glob("*/depth_charts_2025.parquet")) if cache.exists() else []
    for p in reversed(existing):
        if p.exists() and p.stat().st_size > 0:
            return p, sha256_file(p), "REUSED_0.31_CACHE"
    curl = shutil.which("curl")
    if not curl:
        raise SystemExit("FAIL curl unavailable for verified 2025 depth download")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="omega031_depth25_") as td:
        tmp = Path(td) / "depth_charts_2025.parquet"
        cmd = [curl, "--fail", "--location", "--silent", "--show-error", "--connect-timeout", "20", "--max-time", "180", "--retry", "2", "--retry-delay", "1", "--output", str(tmp), DEPTH_2025_URL]
        cp = subprocess.run(cmd, text=True, capture_output=True)
        if cp.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
            raise SystemExit("FAIL 2025 depth download: " + (cp.stderr or cp.stdout or "empty asset").strip())
        digest = sha256_file(tmp); d = cache / digest[:12]; d.mkdir(parents=True, exist_ok=False)
        out = d / "depth_charts_2025.parquet"; shutil.copy2(tmp, out)
        (d / "SOURCE.json").write_text(json.dumps({"url": DEPTH_2025_URL, "sha256": digest, "capturedAt": now(), "purpose": "OMEGA 0.31 component-level confirmatory role input", "modelRefit": False}, indent=2) + "\n", encoding="utf-8")
        return out, digest, "DOWNLOADED_0.31"


def read_depth_rows(path: Path, year: int) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path); names = set(pf.schema_arrow.names)
    required = {"week", "gsis_id", "depth_team"}
    if not required <= names:
        raise SystemExit(f"FAIL {year} depth schema lacks weekly historical fields: {sorted(required-names)}")
    cols = [x for x in ("season", "week", "game_type", "club_code", "team", "gsis_id", "depth_position", "depth_team", "formation") if x in names]
    out: list[dict[str, Any]] = []
    for r in pf.read(columns=cols).to_pylist():
        season = int(num(r.get("season"), float(year)) or year)
        if season != year:
            continue
        if str(r.get("game_type") or "REG").strip().upper() not in {"REG", ""}:
            continue
        if str(r.get("formation") or "").strip().upper() not in {"DEFENSE", "DEF"}:
            continue
        pid = str(r.get("gsis_id") or "").strip(); team = normteam(r.get("club_code") or r.get("team"))
        week = int(num(r.get("week"), 0) or 0); rank = int(num(r.get("depth_team"), 0) or 0)
        if not pid or not team or week <= 0 or rank <= 0:
            continue
        out.append({"season": year, "week": week, "team": team, "player_id": pid, "depth_rank": rank, "depth_position": str(r.get("depth_position") or "").strip()})
    return out


def depth_map_2025(root: Path, depth25: Path, depth25_sha: str) -> tuple[dict[tuple[int, str, str], dict[str, Any]], dict[str, Any]]:
    aid = EXPECTED_DEPTH_AUDIT
    adir = root / "data/raw/nfl/omega/depth_chart_source_audits" / aid
    ap = adir / "OMEGA_DEPTH_CHART_SOURCE_AUDIT.json"
    if not ap.exists():
        raise SystemExit(f"FAIL historical depth audit missing: {ap}")
    audit = json.loads(ap.read_text(encoding="utf-8"))
    a24 = next((a for a in audit.get("assets", []) if int(a.get("year") or 0) == 2024), None)
    if not a24:
        raise SystemExit("FAIL 2024 depth asset absent from frozen audit")
    p24 = adir / str(a24.get("filename") or "")
    if not p24.exists() or sha256_file(p24) != a24.get("sha256"):
        raise SystemExit("FAIL 2024 depth asset hash mismatch")
    rows = read_depth_rows(p24, 2024) + read_depth_rows(depth25, 2025)
    best: dict[tuple[int, int, str, str], dict[str, Any]] = {}
    for r in rows:
        k = (int(r["season"]), int(r["week"]), str(r["team"]), str(r["player_id"]))
        old = best.get(k)
        if old is None or int(r["depth_rank"]) < int(old["depth_rank"]):
            best[k] = dict(r)
    bypid: dict[str, dict[tuple[int, int], list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in best.values():
        bypid[str(r["player_id"])][(int(r["season"]), int(r["week"]))].append(r)
    for _pid, times in bypid.items():
        prev: dict[str, Any] | None = None
        for t in sorted(times):
            group = times[t]
            for r in group:
                r["prev_depth_rank"] = int(prev["depth_rank"]) if prev else 0
                r["prev_depth_team"] = str(prev["team"]) if prev else ""
                r["prev_depth_position"] = str(prev.get("depth_position") or "") if prev else ""
            prev = sorted(group, key=lambda z: (int(z["depth_rank"]), str(z["team"])))[0]
    out: dict[tuple[int, str, str], dict[str, Any]] = {}
    for (season, week, team, pid), r in best.items():
        if season == 2025:
            out[(week, team, pid)] = r
    return out, {"depthAudit2024": aid, "depth2024Sha256": a24.get("sha256"), "depth2025Sha256": depth25_sha, "depth2025Rows": sum(1 for r in rows if int(r["season"]) == 2025), "depth2025UniquePlayerWeeks": len(out)}


def load_role_model(root: Path, cr: Any) -> tuple[Any, dict[str, Any], Path, str]:
    ptr = root / "data/models/nfl/CURRENT_OMEGA_TACKLE_CURRENT_ROLE_SNAP_DISTRIBUTION_CHALLENGER"
    if not ptr.exists() or ptr.read_text(encoding="utf-8").strip() != EXPECTED_ROLE_ARTIFACT:
        raise SystemExit("FAIL 0.2.7 role artifact pointer drift")
    d = root / "data/models/nfl/omega_tackle_027_current_role_snap_distribution" / EXPECTED_ROLE_ARTIFACT
    mp = d / "omega_current_role_model.json"; ap = d / "OMEGA_0.2.7_CURRENT_ROLE_SNAP_DISTRIBUTION_AUDIT.json"
    if not mp.exists() or not ap.exists():
        raise SystemExit("FAIL 0.2.7 serialized role artifact missing")
    audit = json.loads(ap.read_text(encoding="utf-8")); integ = audit.get("integrity", {})
    if integ.get("omega2025RowsRead") != 0 or integ.get("depthChart2025RowsRead") != 0 or integ.get("marketFieldsRead") != 0:
        raise SystemExit("FAIL 0.2.7 development integrity drift")
    if audit.get("verdict") != "H012R_CURRENT_ROLE_DISTRIBUTION_STRONG_PASS":
        raise SystemExit("FAIL 0.2.7 source artifact not the validated strong-pass artifact")
    mj = json.loads(mp.read_text(encoding="utf-8")); m = mj.get("roleModel", {})
    model = cr.RoleCorrectionModel(
        means=[float(x) for x in m["means"]], scales=[float(x) for x in m["scales"]],
        intercept=float(m["intercept"]), coefficients=[float(x) for x in m["coefficients"]], l2=float(m["l2"]),
    )
    return model, audit, mp, sha256_file(mp)


def instantiate_h012(model_dict: dict[str, Any], er: Any) -> Any:
    return er.RidgeModel(
        feature_names=tuple(model_dict["featureNames"]), means=[float(x) for x in model_dict["means"]],
        scales=[float(x) for x in model_dict["scales"]], intercept=float(model_dict["intercept"]),
        coefficients=[float(x) for x in model_dict["coefficients"]], l2=float(model_dict["l2"]),
    )


def subgroup_report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    defs: dict[str, Callable[[dict[str, Any]], bool]] = {
        "depthCovered": lambda r: int(r["depth_present"]) == 1,
        "rank1": lambda r: int(r["depth_rank"]) == 1,
        "rank2": lambda r: int(r["depth_rank"]) == 2,
        "rank3plus": lambda r: int(r["depth_rank"]) >= 3,
        "promotedToRank1": lambda r: int(r["promoted_to_rank1"]) == 1,
        "demotedFromRank1": lambda r: int(r["demoted_from_rank1"]) == 1,
        "week1": lambda r: int(r["week"]) == 1,
        "week1Rank1": lambda r: int(r["week"]) == 1 and int(r["depth_rank"]) == 1,
        "coldStart": lambda r: int(r["prior_games"]) == 0,
        "coldStartRank1": lambda r: int(r["prior_games"]) == 0 and int(r["depth_rank"]) == 1,
        "starterConflict": lambda r: int(r["depth_rank"]) == 1 and float(r["h012_snap_share"]) < .65,
        "backupConflict": lambda r: int(r["depth_rank"]) >= 2 and float(r["h012_snap_share"]) >= .65,
        "positionDB": lambda r: str(r["position_group"]).upper() == "DB",
        "positionLB": lambda r: str(r["position_group"]).upper() == "LB",
        "positionDL": lambda r: str(r["position_group"]).upper() == "DL",
        "largeRoleDisagreement": lambda r: abs(float(r["role_correction"])) >= .15,
    }
    return {name: compare([r for r in rows if fn(r)]) for name, fn in defs.items()}


def gate_status(sub: dict[str, Any]) -> str:
    if int(sub.get("n") or 0) < MIN_GATE_N:
        return "INSUFFICIENT_FOR_GATE"
    return "PASS" if float(sub.get("maeImprovement") or 0.0) >= 0 else "FAIL"


def verdict(overall: dict[str, Any], boot: dict[str, Any], subs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    starter_gate = gate_status(subs["starterConflict"])
    week1_gate = gate_status(subs["week1Rank1"])
    gate_ok = lambda x: x in {"PASS", "INSUFFICIENT_FOR_GATE"}
    mi = float(overall["maeImprovement"]); ri = float(overall["rmseImprovement"])
    strong = mi > 0 and ri > 0 and float(boot["maeImprovementCI95"][0]) > 0 and gate_ok(starter_gate) and gate_ok(week1_gate)
    directional = mi > 0 and ri > 0 and float(boot["probabilityPositive"]) >= .90 and not strong
    if strong:
        v = "STRONG_CONFIRM"
        mapping = "Week 2: current-role point becomes preferred exposure challenger for depth-covered non-backup-conflict rows; frozen OMEGA remains independently scored control; full mixture remains research-only."
    elif directional:
        v = "DIRECTIONAL_CONFIRM"
        mapping = "Week 2: current-role point remains parallel challenger; role conflicts stay quarantined; gather prospective Week 2 evidence before promotion."
    elif mi <= 0 and ri <= 0:
        v = "FAIL"
        mapping = "Week 2: current-role point remains research/shadow only; frozen OMEGA remains control; role conflicts require review rather than auto-correction."
    else:
        v = "MIXED"
        mapping = "Week 2: current-role point remains research/shadow only; frozen OMEGA remains control; role conflicts require review rather than auto-correction."
    gates = {"minimumGateRows": MIN_GATE_N, "starterConflict": starter_gate, "week1Rank1": week1_gate, "overallMAEPositive": mi > 0, "overallRMSEPositive": ri > 0, "bootstrapCI95LowerPositive": float(boot["maeImprovementCI95"][0]) > 0, "bootstrapProbabilityPositiveAtLeast090": float(boot["probabilityPositive"]) >= .90}
    return v, gates, mapping


def existing_result(root: Path) -> Path | None:
    ptr = root / "data/results/nfl/omega/CURRENT_OMEGA_2025_CURRENT_ROLE_CONFIRMATORY"
    if not ptr.exists():
        return None
    p = root / ptr.read_text(encoding="utf-8").strip()
    return p if p.exists() else None


def print_existing(path: Path) -> int:
    rp = path / "OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_REPORT.json"
    hp = path / "OMEGA_0.31_OUTPUT_HASHES.json"
    if not rp.exists() or not hp.exists():
        raise SystemExit(f"FAIL existing confirmatory pointer is incomplete: {path}")
    hs = json.loads(hp.read_text(encoding="utf-8"))
    if sha256_file(rp) != hs.get(rp.name):
        raise SystemExit("FAIL existing confirmatory report hash mismatch")
    r = json.loads(rp.read_text(encoding="utf-8")); o = r["overall"]
    print("OMEGA 0.31 — EXISTING IMMUTABLE 2025 CURRENT-ROLE CONFIRMATORY HOLDOUT")
    print(f"PASS verdict {r['verdict']} · rows {o['n']} · no second score run performed")
    print(f"H012 MAE {o['h012']['mae']:.5f} -> ROLE {o['role']['mae']:.5f} · improvement {o['maeImprovement']:+.5f}")
    print(f"REPORT: {rp}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args(); root = Path(args.root).expanduser().resolve()

    already = existing_result(root)
    if already is not None:
        return print_existing(already)

    protocol = root / PROTOCOL_PATH
    if not protocol.exists() or git_blob_sha1(protocol) != EXPECTED_PROTOCOL_GIT_BLOB_SHA1:
        raise SystemExit("FAIL frozen OMEGA 0.31 protocol blob mismatch; do not score 2025")

    omega = root / "packages/models/nfl/omega"; provider = root / "packages/providers/nflverse/src"
    sys.path[:0] = [str(omega), str(provider)]
    import current_role_snap_distribution_challenger as cr
    import exposure_role_challenger as er
    import exposure_universe as eu
    import xto_xtc_baseline as xb
    import contract

    # Immutable blind H012 ledger and audit.
    blind_dir = root / "data/models/nfl/omega_tackle_012_blind_2025" / EXPECTED_SID
    blind_path = blind_dir / "OMEGA_2025_BLIND_PREDICTIONS.csv"
    blind_audit_path = blind_dir / "OMEGA_0.12_BLIND_AUDIT.json"
    global_models_path = blind_dir / "OMEGA_2025_GLOBAL_MODELS.json"
    for p in (blind_path, blind_audit_path, global_models_path):
        if not p.exists():
            raise SystemExit(f"FAIL blind-2025 prerequisite missing: {p}")
    if sha256_file(blind_path) != EXPECTED_BLIND_SHA256:
        raise SystemExit("FAIL immutable blind-2025 ledger SHA drift")
    blind = rcsv(blind_path)
    games = {r["game_id"] for r in blind}; weeks = {int(r["week"]) for r in blind}
    if len(blind) != EXPECTED_ROWS or len(games) != EXPECTED_GAMES or tuple(sorted(weeks)) != EXPECTED_WEEKS:
        raise SystemExit("FAIL immutable blind-2025 coverage drift")
    ba = json.loads(blind_audit_path.read_text(encoding="utf-8"))
    required_snap_sha = str(ba.get("source", {}).get("2025SnapAssetSha256") or "")
    if not required_snap_sha:
        raise SystemExit("FAIL blind audit lacks pinned 2025 snap asset SHA")

    role_model, role_audit, role_model_path, role_model_sha = load_role_model(root, cr)
    depth25_path, depth25_sha, depth25_mode = download_or_reuse_2025_depth(root)
    dmap, depth_meta = depth_map_2025(root, depth25_path, depth25_sha)

    # Verify outcome source identity/schema in preflight, but do not materialize target rows yet.
    p2g, player_meta, _source_meta = load_player_bridge(root, EXPECTED_SID)
    snap_path, snap_asset, snap_manifest = locate_2025_snap_asset(root, EXPECTED_SID, required_snap_sha)
    import pyarrow.parquet as pq
    snap_schema = set(pq.ParquetFile(snap_path).schema_arrow.names)
    required_cols = {"game_id", "season", "game_type", "week", "pfr_player_id", "team", "defense_snaps"}
    if not required_cols <= snap_schema:
        raise SystemExit(f"FAIL 2025 snap schema drift: {sorted(required_cols-snap_schema)}")

    print("OMEGA 0.31 — SEALED 2025 CURRENT-ROLE CONFIRMATORY PREFLIGHT")
    print(f"PASS protocol git-blob {EXPECTED_PROTOCOL_GIT_BLOB_SHA1} · gates frozen before scoring")
    print(f"PASS blind H012 ledger {EXPECTED_BLIND_SHA256} · rows {len(blind)} · games {len(games)}")
    print(f"PASS frozen role artifact {EXPECTED_ROLE_ARTIFACT} · refit prohibited")
    print(f"PASS 2025 depth {depth25_sha} · {depth25_mode} · weekly role input only")
    print(f"PASS pinned 2025 snap outcome asset {required_snap_sha} · schema verified")
    if args.preflight_only:
        print("PASS PRELIGHT ONLY · 2025 outcome rows not materialized by scorer")
        return 0

    # Materialize the exact snap source used by the blind builder and reconstruct the
    # same conditional exposure universe without reading tackle outcomes.
    cols = [x for x in ("game_id", "season", "game_type", "week", "pfr_player_id", "position", "team", "opponent", "defense_snaps", "defense_pct", "special_teams_snaps", "special_teams_pct", "player") if x in snap_schema]
    snap_rows = pq.ParquetFile(snap_path).read(columns=cols).to_pylist()
    for r in snap_rows:
        if r.get("team"):
            r["team"] = contract.normalize_team_abbr(str(r["team"]))
        if r.get("opponent"):
            r["opponent"] = contract.normalize_team_abbr(str(r["opponent"]))
    exp25, exp_audit = eu.build_expanded_rows(snap_rows, {}, pfr_to_gsis=p2g, player_meta=player_meta, allowed_game_ids=games)
    exp25 = [r for r in exp25 if int(r.get("season") or 0) == 2025 and str(r.get("game_type") or "") == "REG" and truthy(r.get("eligible_standard_rate_fit"))]
    if not exp25:
        raise SystemExit("FAIL no eligible 2025 snap exposure rows")

    # Reconstruct the exact leakage-safe H012 feature state.  The helper is temporarily
    # allowed to emit 2025 rows; no model is fit here. It emits a whole week before
    # admitting that week's actual snap shares to history.
    hist_path = root / "data/normalized/nfl/omega_tackle_exposure" / EXPECTED_SID / "omega_tackle_exposure_player_games.csv"
    hist = rcsv(hist_path)
    if any(int(float(r.get("season") or 0)) >= 2025 for r in hist):
        raise SystemExit("FAIL historical exposure foundation unexpectedly contains 2025")
    combined = list(hist) + exp25
    totals = xb.estimate_team_defensive_snaps(combined)
    old_holdout = er.HOLDOUT_SEASON
    er.HOLDOUT_SEASON = 2026
    try:
        preg = er.build_exposure_pregame_rows(combined, totals)
    finally:
        er.HOLDOUT_SEASON = old_holdout
    preg25 = {(r["game_id"], r["player_id"]): r for r in preg if int(r["season"]) == 2025}
    blind_map = {(r["game_id"], r["player_id"]): r for r in blind}
    missing = sorted(set(blind_map) - set(preg25))
    if missing:
        raise SystemExit(f"FAIL reconstructed pregame exposure missing {len(missing)} blind keys; first={missing[:3]}")

    # Parity check against the already-serialized blind H012 model and predictions.
    gj = json.loads(global_models_path.read_text(encoding="utf-8")); h012_model = instantiate_h012(gj["H012ExposureModel"], er)
    prior_mismatch = 0; h012_drift = 0; max_h012_drift = 0.0
    for k, b in blind_map.items():
        p = preg25[k]
        if int(b["prior_games"]) != int(p["prior_games"]):
            prior_mismatch += 1
        d = abs(float(b["predicted_snap_share"]) - float(h012_model.predict(p)))
        max_h012_drift = max(max_h012_drift, d)
        if d > 1e-9:
            h012_drift += 1
    if prior_mismatch or h012_drift:
        raise SystemExit(f"FAIL blind feature reconstruction parity: prior_games mismatches={prior_mismatch}, H012 drifts={h012_drift}, max={max_h012_drift:.3g}")

    scored: list[dict[str, Any]] = []
    for b in blind:
        key = (b["game_id"], b["player_id"]); p = preg25[key]
        week = int(b["week"]); team = normteam(b["team"]); pid = b["player_id"]
        d = dmap.get((week, team, pid))
        rank = int(d["depth_rank"]) if d else 0; prev = int(d.get("prev_depth_rank") or 0) if d else 0
        role_input = {
            "position_group": b.get("position_group", ""), "prior_games": p["prior_games"], "week": week,
            "team": team, "depth_present": 1 if d else 0, "depth_rank": rank,
            "depth_position": d.get("depth_position", "") if d else "", "prev_depth_rank": prev,
            "prev_depth_team": d.get("prev_depth_team", "") if d else "", "prev_depth_present": 1 if prev > 0 else 0,
            "promoted_to_rank1": 1 if rank == 1 and prev >= 2 else 0,
            "demoted_from_rank1": 1 if prev == 1 and rank >= 2 else 0,
            "rank_improvement": max(0, prev-rank) if rank and prev else 0,
            "rank_demotion": max(0, rank-prev) if rank and prev else 0,
            "team_changed": 1 if d and d.get("prev_depth_team") and str(d.get("prev_depth_team")) != team else 0,
            "last4_snap_share_std": p.get("last4_snap_share_std", 0.0),
        }
        h = float(b["predicted_snap_share"]); rp = float(role_model.predict(role_input, h)); actual = float(p["actual_snap_share"])
        scored.append({
            "game_id": b["game_id"], "season": 2025, "week": week, "team": team, "opponent": normteam(b.get("opponent")),
            "player_id": pid, "player_name": b.get("display_name", ""), "position": b.get("position", ""), "position_group": b.get("position_group", ""),
            "prior_games": int(p["prior_games"]), "last4_snap_share_std": float(p.get("last4_snap_share_std") or 0.0),
            "depth_present": 1 if d else 0, "depth_rank": rank, "depth_position": d.get("depth_position", "") if d else "",
            "prev_depth_rank": prev, "prev_depth_team": d.get("prev_depth_team", "") if d else "",
            "promoted_to_rank1": 1 if rank == 1 and prev >= 2 else 0, "demoted_from_rank1": 1 if prev == 1 and rank >= 2 else 0,
            "h012_snap_share": h, "role_snap_share": rp, "role_correction": rp-h, "actual_snap_share": actual,
            "h012_abs_error": abs(actual-h), "role_abs_error": abs(actual-rp),
        })

    overall = compare(scored); boot = cluster_bootstrap(scored); subs = subgroup_report(scored)
    v, gates, week2 = verdict(overall, boot, subs)
    depth_cov = sum(int(r["depth_present"]) for r in scored) / len(scored)

    report = {
        "schemaVersion": SCHEMA, "generatedAt": now(), "status": "SCORED_IMMUTABLE", "verdict": v,
        "scientificStatus": "COMPONENT_LEVEL_CONFIRMATORY_ONLY_2025_PREVIOUSLY_CONSUMED_BY_OLDER_OMEGA_0.13",
        "protocol": {"path": PROTOCOL_PATH, "gitBlobSha1": EXPECTED_PROTOCOL_GIT_BLOB_SHA1, "bootstrapReps": BOOTSTRAP_REPS, "bootstrapSeed": BOOTSTRAP_SEED},
        "integrity": {"modelRefits": 0, "hyperparameterSearchesAfter2025Open": 0, "marketFieldsRead": 0, "oddsPapiRequests": 0, "frozenOmegaWrites": 0, "roleArtifactWrites": 0, "sameWeekOutcomeAdmittedBeforePrediction": False, "h012ParityMismatchRows": h012_drift, "priorGamesMismatchRows": prior_mismatch},
        "sources": {"sourceSnapshotId": EXPECTED_SID, "blindLedgerSha256": EXPECTED_BLIND_SHA256, "blindAuditSha256": sha256_file(blind_audit_path), "snapAssetSha256": required_snap_sha, "snapSourceManifest": str(snap_manifest.get("snapshotId") or snap_manifest.get("createdAt") or ""), "depth2025": {"sha256": depth25_sha, "mode": depth25_mode, "url": DEPTH_2025_URL}, "roleArtifactId": EXPECTED_ROLE_ARTIFACT, "roleModelSha256": role_model_sha, **depth_meta},
        "coverage": {"rows": len(scored), "games": len({r["game_id"] for r in scored}), "weeks": sorted({int(r["week"]) for r in scored}), "depthCoverage": depth_cov, "reconstructedExposureRows2025": len(exp25), "exposureAudit": exp_audit},
        "overall": overall, "bootstrap": boot, "subgroups": subs, "predeclaredGates": gates,
        "week2Mapping": week2,
        "restrictions": {"fullSnapMixturePromotionAllowedByThisTest": False, "backupConflictWeek2Status": "QUARANTINED_REGARDLESS_OF_AGGREGATE_VERDICT", "frozenOmegaStatus": "INDEPENDENTLY_SCORED_CONTROL"},
        "source0272024": {"verdict": role_audit.get("verdict"), "pointMetrics": role_audit.get("pointMetrics"), "subgroups": role_audit.get("subgroups", {})},
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runid = f"{stamp}_{EXPECTED_BLIND_SHA256[:8]}"
    base = root / "data/results/nfl/omega_2025_current_role_holdout_0310" / EXPECTED_ROLE_ARTIFACT
    final = base / runid; staging = base / ("." + runid + ".staging")
    if final.exists() or staging.exists():
        raise SystemExit("FAIL duplicate 0.31 result id")
    base.mkdir(parents=True, exist_ok=True); staging.mkdir(parents=True, exist_ok=False)
    try:
        sp = staging / "OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_SCORED.csv"; wcsv(sp, scored)
        rp = staging / "OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_REPORT.json"; rp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        shutil.copy2(protocol, staging / "OMEGA_0.31_FROZEN_PROTOCOL.md")
        md = [
            "# OMEGA 0.31 — 2025 Current-Role Point Confirmatory Holdout", "",
            f"**VERDICT: {v}**", "", f"Generated: `{report['generatedAt']}`  ",
            "Scientific status: component-level confirmatory only; 2025 was previously consumed by the older OMEGA 0.13 project holdout.", "",
            "## Overall", "",
            f"- Rows: **{overall['n']}** · games: **{EXPECTED_GAMES}** · depth coverage: **{depth_cov:.1%}**",
            f"- H012 MAE **{overall['h012']['mae']:.5f}** → role **{overall['role']['mae']:.5f}** · improvement **{overall['maeImprovement']:+.5f}**",
            f"- H012 RMSE **{overall['h012']['rmse']:.5f}** → role **{overall['role']['rmse']:.5f}** · improvement **{overall['rmseImprovement']:+.5f}**",
            f"- MAE game-cluster bootstrap 95% CI **[{boot['maeImprovementCI95'][0]:+.5f}, {boot['maeImprovementCI95'][1]:+.5f}]** · P(positive) **{boot['probabilityPositive']:.3f}**", "",
            "## Gate subgroups", "",
            f"- starterConflict: n **{subs['starterConflict']['n']}** · improvement **{subs['starterConflict'].get('maeImprovement', 0):+.5f}** · gate **{gates['starterConflict']}**",
            f"- week1Rank1: n **{subs['week1Rank1']['n']}** · improvement **{subs['week1Rank1'].get('maeImprovement', 0):+.5f}** · gate **{gates['week1Rank1']}**",
            f"- backupConflict: n **{subs['backupConflict']['n']}** · improvement **{subs['backupConflict'].get('maeImprovement', 0):+.5f}** · Week 2 remains quarantined", "",
            "## Week 2 mapping", "", week2, "",
            "Full snap-mixture remains research-only. Frozen OMEGA remains an independently scored control.", "",
        ]
        (staging / "OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_REPORT.md").write_text("\n".join(md), encoding="utf-8")
        hashes = {p.name: sha256_file(p) for p in staging.iterdir() if p.is_file()}
        (staging / "OMEGA_0.31_OUTPUT_HASHES.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, final)
        ptr = root / "data/results/nfl/omega/CURRENT_OMEGA_2025_CURRENT_ROLE_CONFIRMATORY"; ptr.parent.mkdir(parents=True, exist_ok=True)
        tmp = ptr.with_name("." + ptr.name + ".tmp"); tmp.write_text(str(final.relative_to(root)) + "\n", encoding="utf-8"); os.replace(tmp, ptr)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True); raise

    print("\nOMEGA 0.31 — 2025 CURRENT-ROLE POINT CONFIRMATORY HOLDOUT")
    print(f"PASS component-level sealed evaluation · rows {len(scored)} · games {EXPECTED_GAMES} · depth coverage {depth_cov:.1%}")
    print(f"H012: MAE {overall['h012']['mae']:.5f} · RMSE {overall['h012']['rmse']:.5f} · bias {overall['h012']['biasPredMinusActual']:+.5f}")
    print(f"ROLE: MAE {overall['role']['mae']:.5f} · RMSE {overall['role']['rmse']:.5f} · bias {overall['role']['biasPredMinusActual']:+.5f}")
    print(f"IMPROVEMENT: MAE {overall['maeImprovement']:+.5f} · RMSE {overall['rmseImprovement']:+.5f}")
    print(f"BOOTSTRAP MAE 95% CI [{boot['maeImprovementCI95'][0]:+.5f}, {boot['maeImprovementCI95'][1]:+.5f}] · P(positive) {boot['probabilityPositive']:.3f}")
    for name in ("starterConflict", "backupConflict", "promotedToRank1", "demotedFromRank1", "week1Rank1", "coldStartRank1", "largeRoleDisagreement"):
        s = subs[name]
        print(f"{name}: n {s['n']} · H012 {s.get('h012',{}).get('mae',0):.4f} -> role {s.get('role',{}).get('mae',0):.4f} · improvement {s.get('maeImprovement',0):+.4f}")
    print(f"VERDICT: {v}")
    print(f"WEEK 2: {week2}")
    print("PASS refits 0 · searches after 2025 open 0 · market fields 0 · OddsPapi 0 · frozen OMEGA writes 0")
    print(f"REPORT: {final/'OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

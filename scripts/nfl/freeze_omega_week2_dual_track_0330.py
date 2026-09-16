#!/usr/bin/env python3
"""OMEGA 0.33 — Week 2 prior-state admission + dual-track prospective freeze.

This is an operational research freeze, not a model fit.

CONTROL:
  Exact frozen OMEGA H008 + H012 mean construction with frozen NB_ROLE probability
  parameters. Completed 2026 Week 1 state is admitted only as strictly-prior history.

ROLE_POINT:
  Exact serialized OMEGA 0.2.7 current-role point correction applied to H012.
  This changes snap-share location and xTC mean only. A probability SHADOW is emitted
  with the CONTROL H012 NB_ROLE tier held fixed so the prospective comparison isolates
  the role-point mean change. It is not a promoted probability model.

The empirical 0.2.8 snap-mixture is intentionally not emitted/promoted here.
No market data, Week 2 outcomes, refits, or writes to frozen OMEGA are permitted.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys

SCHEMA = "OMEGA_2026_WEEK2_DUAL_TRACK_PROSPECTIVE_FREEZE_0.33.0"
VERSION = "0.33.0"
SEASON = 2026
TARGET_WEEK = 2
PRIOR_WEEK = 1
CORE = {"DB", "DL", "LB"}
MIN_ROLE_COVERAGE = 0.80
ROLE_CONFIRM_MIN_COVERAGE = 0.80


def nowdt() -> datetime:
    return datetime.now(timezone.utc)


def now() -> str:
    return nowdt().isoformat(timespec="seconds").replace("+00:00", "Z")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def rcsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def wcsv(path: Path, rows: Sequence[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or ["status"], extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})
    return fields


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def num(v: Any, default: float = 0.0) -> float:
    try:
        if v in (None, ""):
            return default
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def truthy(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "t", "ready", "pass"}


def parse_ts(v: Any) -> datetime:
    s = str(v or "").strip().replace("Z", "+00:00")
    if not s:
        raise ValueError("empty timestamp")
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_date(v: Any) -> date | None:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(s[:10])
        except Exception:
            return None


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FAIL cannot load module {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_asset_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        return rcsv(path)
    if path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    raise SystemExit(f"FAIL unsupported asset format: {path}")


def asset_from_manifest(meta: dict[str, Any], source: str, season: int | None = None) -> dict[str, Any]:
    hits = []
    for a in meta.get("assets", []):
        if str(a.get("source") or "") != source:
            continue
        if season is not None and int(a.get("season") or 0) != season:
            continue
        hits.append(a)
    if len(hits) != 1:
        raise SystemExit(f"FAIL expected one {source}/{season} asset; found {len(hits)}")
    return hits[0]


def verified_asset_path(root: Path, asset: dict[str, Any]) -> Path:
    p = root / str(asset.get("blobPath") or "")
    if not p.exists():
        raise SystemExit(f"FAIL source asset missing: {p}")
    expected = str(asset.get("sha256") or "")
    if expected and sha(p) != expected:
        raise SystemExit(f"FAIL source asset hash mismatch: {p}")
    return p


def schedule_week_rows(rows: Sequence[dict[str, Any]], week: int) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if int(num(r.get("season"), 0)) != SEASON or int(num(r.get("week"), 0)) != week:
            continue
        gt = str(r.get("game_type") or r.get("season_type") or "REG").strip().upper()
        if gt not in {"REG", ""}:
            continue
        if not str(r.get("game_id") or "").strip():
            continue
        out.append(dict(r))
    return out


def schedule_complete(r: dict[str, Any]) -> bool:
    result = str(r.get("result") or "").strip()
    hs = str(r.get("home_score") or "").strip()
    aws = str(r.get("away_score") or "").strip()
    return bool(result or (hs != "" and aws != ""))


def game_day(r: dict[str, Any]) -> date | None:
    for k in ("gameday", "game_date", "date", "event_date", "start_date"):
        d = parse_date(r.get(k))
        if d is not None:
            return d
    return None


def normalize_schedule_teams(rows: Sequence[dict[str, Any]], contract: Any) -> None:
    for r in rows:
        for k in ("away_team", "home_team"):
            if r.get(k):
                r[k] = contract.normalize_team_abbr(str(r[k]))


def resolve_results_manifest(root: Path) -> tuple[Path, dict[str, Any]]:
    ptr = root / "data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST"
    if not ptr.exists():
        raise SystemExit("FAIL dedicated 2026 results pointer missing; refresh results first")
    v = ptr.read_text(encoding="utf-8").strip()
    p = Path(v) if v.startswith("/") else root / v
    if not p.exists():
        raise SystemExit(f"FAIL results manifest missing: {p}")
    return p, json.loads(p.read_text(encoding="utf-8"))


def resolve_snap_manifest(root: Path) -> tuple[Path, dict[str, Any], Path]:
    ptr = root / "data/raw/nfl/omega/CURRENT_OMEGA_2026_SNAP_COUNTS"
    if not ptr.exists():
        raise SystemExit("FAIL 2026 snap-count pointer missing; refresh snap counts first")
    sid = ptr.read_text(encoding="utf-8").strip()
    mp = root / "data/raw/nfl/omega/snap_count_results_0290" / sid / "SNAP_COUNTS_RESULTS_MANIFEST.json"
    if not mp.exists():
        raise SystemExit(f"FAIL 2026 snap manifest missing: {mp}")
    meta = json.loads(mp.read_text(encoding="utf-8"))
    sp = mp.parent / "snap_counts_2026.parquet"
    if not sp.exists() or sha(sp) != str(meta.get("sha256") or ""):
        raise SystemExit("FAIL 2026 snap-count asset/hash mismatch")
    return mp, meta, sp


def load_week_pbp(path: Path, game_ids: set[str], te: Any, contract: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    required = {"game_id", "play_id", "season", "week", "posteam", "defteam"}
    missing = required - names
    if missing:
        raise SystemExit(f"FAIL Week 1 PBP missing required columns: {sorted(missing)}")
    optional = (
        "play_type", "no_play", "play_deleted", "special_teams_play", "qtr", "down", "ydstogo",
        "yardline_100", "game_seconds_remaining", "score_differential", "score_differential_post",
        "yards_gained", "air_yards", "yards_after_catch", "run_location", "run_gap", "pass_location",
        "pass_length", "shotgun", "no_huddle", "qb_scramble", "sack", "complete_pass", "interception",
        "fumble", "fumble_lost", "rush_attempt", "rush", "pass_attempt", "qb_dropback",
    ) + tuple(te.TACKLE_ID_COLUMNS) + tuple(te.TACKLE_NAME_COLUMNS) + tuple(te.TACKLE_TEAM_COLUMNS)
    cols = list(required) + [c for c in optional if c in names and c not in required]
    table = pq.read_table(path, columns=cols, filters=[("season", "=", SEASON), ("week", "=", PRIOR_WEEK)])
    raw = [r for r in table.to_pylist() if str(r.get("game_id") or "") in game_ids]
    if not raw:
        raise SystemExit("FAIL no Week 1 2026 PBP rows materialized")
    if any(int(num(r.get("week"), 0)) != PRIOR_WEEK for r in raw):
        raise SystemExit("FAIL non-Week-1 PBP row entered prior-state materialization")
    seen = {str(r.get("game_id") or "") for r in raw}
    if seen != game_ids:
        raise SystemExit(f"FAIL Week 1 PBP game coverage mismatch; missing={sorted(game_ids-seen)} extra={sorted(seen-game_ids)}")
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    plays: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for r in raw:
        gid = str(r.get("game_id") or "")
        by_game[gid].append(r)
        if r.get("posteam"):
            r["posteam"] = contract.normalize_team_abbr(str(r["posteam"]))
        if r.get("defteam"):
            r["defteam"] = contract.normalize_team_abbr(str(r["defteam"]))
        ev = te.extract_credit_events(r)
        events.extend(ev)
        plays.append(te.build_play_opportunity_row(r, ev))
    readiness = {}
    for gid, rr in by_game.items():
        qs = [int(num(r.get("qtr"), 0)) for r in rr if r.get("qtr") not in (None, "")]
        if len(rr) < 80 or (qs and max(qs) < 4):
            raise SystemExit(f"FAIL Week 1 game not PBP-complete: {gid} rows={len(rr)} maxQ={max(qs) if qs else 'NA'}")
        readiness[gid] = {"pbpRows": len(rr), "maxQtr": max(qs) if qs else None}
    return plays, events, {"rows": len(raw), "games": len(seen), "perGame": readiness}


def load_week_snap_rows(path: Path, game_ids: set[str], contract: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    required = {"game_id", "season", "week", "pfr_player_id", "team", "opponent", "defense_snaps", "defense_pct"}
    missing = required - names
    if missing:
        raise SystemExit(f"FAIL Week 1 snap asset missing required columns: {sorted(missing)}")
    cols = list(required) + [c for c in ("game_type", "position", "special_teams_snaps", "special_teams_pct", "player") if c in names]
    table = pq.read_table(path, columns=cols, filters=[("season", "=", SEASON), ("week", "=", PRIOR_WEEK)])
    rows = [dict(r) for r in table.to_pylist() if str(r.get("game_id") or "") in game_ids]
    seen = {str(r.get("game_id") or "") for r in rows}
    if seen != game_ids:
        raise SystemExit(f"FAIL Week 1 snap game coverage mismatch; missing={sorted(game_ids-seen)}")
    for r in rows:
        r["team"] = contract.normalize_team_abbr(str(r.get("team") or "")) if r.get("team") else ""
        r["opponent"] = contract.normalize_team_abbr(str(r.get("opponent") or "")) if r.get("opponent") else ""
        if not r.get("game_type"):
            r["game_type"] = "REG"
    return rows, {"rows": len(rows), "games": len(seen)}


def instantiate_models(gm: dict[str, Any], xb: Any, er: Any):
    x = gm["xTOModel"]
    xto = xb.RidgeModel(
        feature_names=tuple(x["featureNames"]), means=[float(v) for v in x["means"]],
        scales=[float(v) for v in x["scales"]], intercept=float(x["intercept"]),
        coefficients=[float(v) for v in x["coefficients"]], l2=float(x["l2"]),
        target_name=str(x.get("targetName") or "actual_opportunity_plays"),
    )
    h = gm["H012ExposureModel"]
    h012 = er.RidgeModel(
        feature_names=tuple(h["featureNames"]), means=[float(v) for v in h["means"]],
        scales=[float(v) for v in h["scales"]], intercept=float(h["intercept"]),
        coefficients=[float(v) for v in h["coefficients"]], l2=float(h["l2"]),
    )
    return xto, h012


def load_role_gate_and_model(root: Path, cr: Any) -> tuple[str, Any, dict[str, Any], Path, str, Path, dict[str, Any]]:
    confirm_ptr = root / "data/results/nfl/omega/CURRENT_OMEGA_2025_CURRENT_ROLE_CONFIRMATORY"
    if not confirm_ptr.exists():
        raise SystemExit("FAIL OMEGA 0.31 confirmatory pointer missing")
    confirm_dir = root / confirm_ptr.read_text(encoding="utf-8").strip()
    confirm_report_path = confirm_dir / "OMEGA_0.31_2025_CURRENT_ROLE_CONFIRMATORY_REPORT.json"
    confirm_hashes_path = confirm_dir / "OMEGA_0.31_OUTPUT_HASHES.json"
    if not confirm_report_path.exists() or not confirm_hashes_path.exists():
        raise SystemExit("FAIL OMEGA 0.31 confirmatory bundle incomplete")
    hashes = json.loads(confirm_hashes_path.read_text(encoding="utf-8"))
    if hashes.get(confirm_report_path.name) != sha(confirm_report_path):
        raise SystemExit("FAIL OMEGA 0.31 confirmatory report hash mismatch")
    confirm = json.loads(confirm_report_path.read_text(encoding="utf-8"))
    if confirm.get("verdict") != "STRONG_CONFIRM":
        raise SystemExit(f"FAIL Week 2 role promotion gate: 0.31 verdict={confirm.get('verdict')}")
    dc = float(confirm.get("coverage", {}).get("depthCoverage") or 0.0)
    if dc < ROLE_CONFIRM_MIN_COVERAGE:
        raise SystemExit(f"FAIL Week 2 role promotion gate: 0.31 depth coverage {dc:.1%}")

    ptr = root / "data/models/nfl/CURRENT_OMEGA_TACKLE_CURRENT_ROLE_SNAP_DISTRIBUTION_CHALLENGER"
    if not ptr.exists():
        raise SystemExit("FAIL OMEGA 0.2.7 role artifact pointer missing")
    oid = ptr.read_text(encoding="utf-8").strip()
    d = root / "data/models/nfl/omega_tackle_027_current_role_snap_distribution" / oid
    mp = d / "omega_current_role_model.json"
    ap = d / "OMEGA_0.2.7_CURRENT_ROLE_SNAP_DISTRIBUTION_AUDIT.json"
    for p in (mp, ap):
        if not p.exists():
            raise SystemExit(f"FAIL OMEGA 0.2.7 artifact missing: {p}")
    audit = json.loads(ap.read_text(encoding="utf-8"))
    if audit.get("verdict") != "H012R_CURRENT_ROLE_DISTRIBUTION_STRONG_PASS":
        raise SystemExit("FAIL OMEGA 0.2.7 artifact is not validated strong-pass")
    integ = audit.get("integrity", {})
    if int(integ.get("omega2025RowsRead") or 0) != 0 or int(integ.get("depthChart2025RowsRead") or 0) != 0 or int(integ.get("marketFieldsRead") or 0) != 0:
        raise SystemExit("FAIL OMEGA 0.2.7 development integrity drift")
    m = json.loads(mp.read_text(encoding="utf-8"))["roleModel"]
    model = cr.RoleCorrectionModel(
        means=[float(v) for v in m["means"]], scales=[float(v) for v in m["scales"]],
        intercept=float(m["intercept"]), coefficients=[float(v) for v in m["coefficients"]], l2=float(m["l2"]),
    )
    return oid, model, audit, mp, sha(mp), confirm_report_path, confirm


def previous_week_depth(root: Path, source_dir: Path, week1_schedule: Sequence[dict[str, Any]], contract: Any) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    p = source_dir / "depth_charts.csv"
    if not p.exists():
        raise SystemExit(f"FAIL pregame capture lacks raw depth history: {p}")
    rows = rcsv(p)
    if not rows:
        raise SystemExit("FAIL raw 2026 depth history is empty")
    fields = set(rows[0])
    required = {"dt", "team", "gsis_id", "pos_rank"}
    if not required <= fields:
        raise SystemExit(f"FAIL unsupported 2026 depth schema; missing {sorted(required-fields)}")

    week1_day: dict[str, date] = {}
    for g in week1_schedule:
        gd = game_day(g)
        if gd is None:
            raise SystemExit(f"FAIL Week 1 schedule lacks gameday for {g.get('game_id')}")
        away = contract.normalize_team_abbr(str(g.get("away_team") or ""))
        home = contract.normalize_team_abbr(str(g.get("home_team") or ""))
        week1_day[away] = gd; week1_day[home] = gd
    if len(week1_day) < 28:
        raise SystemExit(f"FAIL suspicious Week 1 team/gameday coverage: {len(week1_day)}")

    by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        team = contract.normalize_team_abbr(str(r.get("team") or "")) if r.get("team") else ""
        pid = str(r.get("gsis_id") or "").strip()
        rank = int(num(r.get("pos_rank"), 0))
        d = parse_date(r.get("dt"))
        if not team or not pid or rank <= 0 or d is None:
            continue
        by_team[team].append({
            "dt": str(r.get("dt") or ""), "date": d, "team": team, "player_id": pid,
            "depth_rank": rank, "depth_position": str(r.get("pos_abb") or r.get("pos_name") or "").strip(),
        })

    out: dict[tuple[str, str], dict[str, Any]] = {}
    selected: dict[str, str] = {}
    missing_teams: list[str] = []
    for team, gd in sorted(week1_day.items()):
        eligible = [r for r in by_team.get(team, []) if r["date"] < gd]
        if not eligible:
            missing_teams.append(team)
            continue
        latest_date = max(r["date"] for r in eligible)
        day_rows = [r for r in eligible if r["date"] == latest_date]
        latest_dt = max(str(r["dt"]) for r in day_rows)
        snap = [r for r in day_rows if str(r["dt"]) == latest_dt]
        selected[team] = latest_dt
        by_pid: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in snap:
            by_pid[r["player_id"]].append(r)
        for pid, rr in by_pid.items():
            cur = sorted(rr, key=lambda z: (int(z["depth_rank"]), str(z["depth_position"])))[0]
            out[(team, pid)] = dict(cur)
    if len(selected) < 28:
        raise SystemExit(f"FAIL previous-role Week 1 depth snapshots too sparse: {len(selected)} teams; missing={missing_teams}")
    return out, {
        "rawDepthRows": len(rows), "selectedTeamSnapshots": len(selected), "missingTeams": missing_teams,
        "selectionRule": "latest exact TEAM snapshot on calendar date STRICTLY BEFORE team Week 1 gameday; same-day excluded",
        "selectedSnapshots": selected,
    }


def role_state(rank: int, h012: float) -> str:
    if rank <= 0:
        return "NO_DEPTH_FALLBACK_H012"
    if rank >= 2 and h012 >= 0.65:
        return "REVIEW_BACKUP_CONFLICT"
    if rank == 1 and h012 < 0.65:
        return "STARTER_CONFLICT_REVIEW"
    return "ROLE_ALIGNED"


def add_probabilities(row: dict[str, Any], *, prefix: str, mean: float, tier: str, dist: Any, params: dict[str, Any]) -> None:
    for whole in range(15):
        line = whole + 0.5
        tag = str(line).replace(".", "_")
        po = dist.over_probability(line, max(0.0, mean), "NB_ROLE", params, tier)
        row[f"{prefix}p_over_{tag}"] = po
        row[f"{prefix}p_under_{tag}"] = 1.0 - po


def canonical_track(base: dict[str, Any], *, track: str, snap: float, xtc: float, tier: str, params: dict[str, Any], dist: Any) -> dict[str, Any]:
    z = dict(base)
    z["forecast_track"] = track
    z["predicted_snap_share"] = snap
    z["predicted_xtc"] = xtc
    z["distribution_family"] = "NB_ROLE"
    z["distribution_role_tier"] = tier
    z["distribution_size"] = params.get(f"size_{tier}", params["globalSize"])
    for whole in range(15):
        line = whole + 0.5; tag = str(line).replace(".", "_")
        po = dist.over_probability(line, max(0.0, xtc), "NB_ROLE", params, tier)
        z[f"p_over_{tag}"] = po; z[f"p_under_{tag}"] = 1.0 - po
        z[f"fair_over_{tag}"] = dist.fair_american(po); z[f"fair_under_{tag}"] = dist.fair_american(1.0-po)
    return z


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--week", type=int, default=TARGET_WEEK)
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    if args.week != TARGET_WEEK:
        raise SystemExit(f"FAIL OMEGA 0.33 is frozen specifically for Week {TARGET_WEEK}; requested {args.week}")

    started = nowdt()
    sys.path[:0] = [str(root/"packages/models/nfl/omega"), str(root/"packages/providers/nflverse/src")]
    import frozen_spec as fs
    import tackle_events as te
    import exposure_universe as eu
    import xto_xtc_baseline as xb
    import exposure_role_challenger as er
    import tackle_opportunity_footprint as tf
    import tackle_count_distribution as dist
    import current_role_snap_distribution_challenger as cr
    import contract

    wk1 = load_module("omega016_week1_helpers_033", root/"scripts/nfl/build_omega_tackle_016_2026_week1.py")

    # ---- Immutable model inputs: serialized models only, never refit. ----
    pptr = root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not pptr.exists():
        raise SystemExit("FAIL frozen OMEGA probability pointer missing")
    model_sid = pptr.read_text(encoding="utf-8").strip()
    prob_spec_path = root/"data/models/nfl/omega_tackle_016_probability_frozen"/model_sid/"OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json"
    if not prob_spec_path.exists():
        raise SystemExit("FAIL frozen OMEGA probability spec missing")
    prob_spec = json.loads(prob_spec_path.read_text(encoding="utf-8"))
    if prob_spec.get("distributionFamily") != "NB_ROLE":
        raise SystemExit("FAIL frozen probability family drift")
    nb_params = prob_spec["distributionParamsFitThrough2024"]

    blind_dir = root/"data/models/nfl/omega_tackle_012_blind_2025"/model_sid
    global_models_path = blind_dir/"OMEGA_2025_GLOBAL_MODELS.json"
    blind_audit_path = blind_dir/"OMEGA_0.12_BLIND_AUDIT.json"
    if not global_models_path.exists() or not blind_audit_path.exists():
        raise SystemExit("FAIL frozen serialized mean-model lineage missing")
    gm = json.loads(global_models_path.read_text(encoding="utf-8"))
    xto_model, h012_model = instantiate_models(gm, xb, er)
    blind_audit = json.loads(blind_audit_path.read_text(encoding="utf-8"))
    required_2025_snap_sha = str(blind_audit.get("source", {}).get("2025SnapAssetSha256") or "")
    if not required_2025_snap_sha:
        raise SystemExit("FAIL blind audit lacks pinned 2025 snap asset SHA")

    role_oid, role_model, role_audit, role_model_path, role_model_sha, confirm_path, confirm = load_role_gate_and_model(root, cr)

    # ---- Fresh Week 2 pregame state. ----
    sptr = root/"data/raw/nfl/omega/CURRENT_OMEGA_TACKLE_2026_PREGAME_SOURCE"
    if not sptr.exists():
        raise SystemExit("FAIL fresh 2026 pregame-source pointer missing")
    source_id = sptr.read_text(encoding="utf-8").strip()
    source_dir = root/"data/raw/nfl/omega/prospective_2026_pregame"/source_id
    source_manifest_path = source_dir/"PREGAME_SOURCE_MANIFEST.json"
    state_path = source_dir/"normalized_pregame_state.csv"
    games_path = source_dir/"target_games.csv"
    for p in (source_manifest_path, state_path, games_path):
        if not p.exists():
            raise SystemExit(f"FAIL Week 2 pregame capture incomplete: {p}")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if int(source_manifest.get("season") or 0) != SEASON or int(source_manifest.get("targetWeek") or 0) != TARGET_WEEK:
        raise SystemExit("FAIL current pregame source is not 2026 Week 2")
    if int(source_manifest.get("marketFieldsRead") or 0) != 0 or int(source_manifest.get("oddsPapiRequests") or 0) != 0:
        raise SystemExit("FAIL Week 2 pregame source market contamination")
    state = rcsv(state_path); target_games = rcsv(games_path)
    if not target_games:
        raise SystemExit("FAIL Week 2 target game list empty")
    target_game_ids = {str(r.get("game_id") or "") for r in target_games if r.get("game_id")}
    kickoff_values = [parse_ts(r.get("kickoff_utc")) for r in target_games if r.get("kickoff_utc")]
    if len(kickoff_values) != len(target_games):
        raise SystemExit("FAIL Week 2 target schedule has missing kickoff")
    earliest_kickoff = min(kickoff_values)
    source_capture = parse_ts(source_manifest.get("capturedAt"))
    if source_capture >= earliest_kickoff:
        raise SystemExit("FAIL Week 2 role/roster source captured at/after earliest kickoff")
    if started >= earliest_kickoff:
        raise SystemExit("FAIL OMEGA 0.33 freeze started at/after earliest Week 2 kickoff")

    # ---- Dedicated results/snap sources. Materialize Week 1 only. ----
    results_manifest_path, results_meta = resolve_results_manifest(root)
    sched_asset = asset_from_manifest(results_meta, "schedules")
    pbp26_asset = asset_from_manifest(results_meta, "play_by_play", SEASON)
    players26_asset = asset_from_manifest(results_meta, "players")
    sched_path = verified_asset_path(root, sched_asset)
    pbp26_path = verified_asset_path(root, pbp26_asset)
    verified_asset_path(root, players26_asset)
    schedule_rows = read_asset_rows(sched_path)
    normalize_schedule_teams(schedule_rows, contract)
    week1_schedule = schedule_week_rows(schedule_rows, PRIOR_WEEK)
    if len(week1_schedule) < 10:
        raise SystemExit(f"FAIL suspicious Week 1 schedule coverage: {len(week1_schedule)} games")
    week1_game_ids = {str(r["game_id"]) for r in week1_schedule}
    incomplete = sorted(str(r["game_id"]) for r in week1_schedule if not schedule_complete(r))
    if incomplete:
        raise SystemExit(f"FAIL Week 1 is not fully complete; games={incomplete}")

    p1, e1, pbp_week1_audit = load_week_pbp(pbp26_path, week1_game_ids, te, contract)
    snap_manifest_path, snap_meta, snap26_path = resolve_snap_manifest(root)
    snap1, snap_week1_audit = load_week_snap_rows(snap26_path, week1_game_ids, contract)
    pm26, p2g26 = wk1.player_meta(root, players26_asset)
    ex1, ex1_audit = eu.build_expanded_rows(
        snap1, eu.aggregate_event_player_games(e1), pfr_to_gsis=p2g26, player_meta=pm26, allowed_game_ids=week1_game_ids,
    )
    ex1 = [r for r in ex1 if int(num(r.get("season"), 0)) == SEASON and int(num(r.get("week"), 0)) == PRIOR_WEEK]
    if not ex1:
        raise SystemExit("FAIL no eligible reconstructed 2026 Week 1 exposure rows")

    # ---- Frozen historical state through 2024 + complete 2025 strictly prior. ----
    foundation = root/"data/normalized/nfl/omega_tackle"/model_sid
    exdir = root/"data/normalized/nfl/omega_tackle_exposure"/model_sid
    phase1 = root/"data/normalized/nfl/phase1"/model_sid
    histp = rcsv(foundation/"omega_tackle_play_opportunities.csv")
    histe = rcsv(foundation/"omega_tackle_credit_events.csv")
    histex = rcsv(exdir/"omega_tackle_exposure_player_games.csv")
    source25_manifest_path = root/"data/raw/nfl/nflverse/snapshots"/model_sid/"SOURCE_MANIFEST.json"
    source25_manifest = json.loads(source25_manifest_path.read_text(encoding="utf-8"))
    assets25 = {(str(a.get("source")), a.get("season")): a for a in source25_manifest.get("assets", [])}
    pa25 = assets25.get(("players", None)); pbpa25 = assets25.get(("play_by_play", 2025))
    if not pa25 or not pbpa25:
        raise SystemExit("FAIL frozen source lacks 2025 PBP/player identity assets")
    pm25, p2g25 = wk1.player_meta(root, pa25)
    games25 = [r for r in rcsv(phase1/"game_identity.csv") if int(num(r.get("season"),0)) == 2025 and str(r.get("game_type") or "") == "REG"]
    allowed25 = {str(r["game_id"]) for r in games25}
    req = ("game_id","play_id","season","week","posteam","defteam")
    opt = (
        "play_type","no_play","play_deleted","special_teams_play","qtr","down","ydstogo","yardline_100",
        "game_seconds_remaining","score_differential","score_differential_post","yards_gained","air_yards",
        "yards_after_catch","run_location","run_gap","pass_location","pass_length","shotgun","no_huddle",
        "qb_scramble","sack","complete_pass","interception","fumble","fumble_lost","rush_attempt","rush",
        "pass_attempt","qb_dropback",
    ) + tuple(te.TACKLE_ID_COLUMNS) + tuple(te.TACKLE_NAME_COLUMNS) + tuple(te.TACKLE_TEAM_COLUMNS)
    raw25, _ = wk1.pqrows(root/pbpa25["blobPath"], req, opt)
    p25: list[dict[str,Any]] = []; e25: list[dict[str,Any]] = []
    for r in raw25:
        if str(r.get("game_id") or "") not in allowed25:
            continue
        if r.get("posteam"): r["posteam"] = wk1.normteam(contract, r["posteam"])
        if r.get("defteam"): r["defteam"] = wk1.normteam(contract, r["defteam"])
        ev = te.extract_credit_events(r); e25.extend(ev); p25.append(te.build_play_opportunity_row(r, ev))
    snap25_asset = wk1.snap_asset_2025(root, model_sid)
    if str(snap25_asset.get("sha256") or "") != required_2025_snap_sha:
        raise SystemExit("FAIL 2025 snap prior asset differs from immutable blind-build source")
    sr25, _ = wk1.pqrows(root/snap25_asset["blobPath"], ("game_id","season","game_type","week","pfr_player_id","position","team","opponent","defense_snaps"), ("defense_pct","special_teams_snaps","special_teams_pct","player"))
    for r in sr25:
        if r.get("team"): r["team"] = wk1.normteam(contract, r["team"])
        if r.get("opponent"): r["opponent"] = wk1.normteam(contract, r["opponent"])
    ex25, ex25_audit = eu.build_expanded_rows(sr25, eu.aggregate_event_player_games(e25), pfr_to_gsis=p2g25, player_meta=pm25, allowed_game_ids=allowed25)
    ex25 = [r for r in ex25 if int(num(r.get("season"),0)) == 2025 and str(r.get("game_type") or "") == "REG"]

    # ---- Aggregate prior football state, with holdout guards temporarily moved beyond target. ----
    team_hist = xb.aggregate_team_game_outcomes(histp, histex)
    team25 = xb.aggregate_team_game_outcomes(p25, ex25)
    team1 = xb.aggregate_team_game_outcomes(p1, ex1)
    ts_hist = xb.estimate_team_defensive_snaps(histex)
    ts25 = xb.estimate_team_defensive_snaps(ex25)
    ts1 = xb.estimate_team_defensive_snaps(ex1)
    old_holdout = tf.HOLDOUT_SEASON
    tf.HOLDOUT_SEASON = 2027
    try:
        fam_hist = tf.aggregate_team_family_opportunities(histp)
        fam25 = tf.aggregate_team_family_opportunities(p25)
        fam1 = tf.aggregate_team_family_opportunities(p1)
        pfc_hist = tf.aggregate_player_family_credits(histe)
        pfc25 = tf.aggregate_player_family_credits(e25)
        pfc1 = tf.aggregate_player_family_credits(e1)
    finally:
        tf.HOLDOUT_SEASON = old_holdout
    fmh = {(r["game_id"],r["defense_team"]):r for r in fam_hist}
    fm25 = {(r["game_id"],r["defense_team"]):r for r in fam25}
    fm1 = {(r["game_id"],r["defense_team"]):r for r in fam1}

    off_hist: dict[str,list[dict[str,Any]]] = defaultdict(list)
    def_hist: dict[str,list[dict[str,Any]]] = defaultdict(list)
    off_fam: dict[str,list[dict[str,Any]]] = defaultdict(list)
    def_fam: dict[str,list[dict[str,Any]]] = defaultdict(list)
    league_fam = {f:0.0 for f in fs.FAMILIES}; league_fam_total = 0.0
    for g in sorted(team_hist + team25 + team1, key=lambda r:(int(r["season"]),int(r["week"]),r["game_id"],r["defense_team"])):
        off_hist[g["offense_team"]].append(g); def_hist[g["defense_team"]].append(g)
    for g in sorted(fam_hist + fam25 + fam1, key=lambda r:(int(r["season"]),int(r["week"]),r["game_id"],r["defense_team"])):
        off_fam[g["offense_team"]].append(g); def_fam[g["defense_team"]].append(g)
        league_fam_total += float(g.get("total_opportunity_plays") or 0.0)
        for f in fs.FAMILIES:
            league_fam[f] += float(g.get(f"opp_{f}") or 0.0)

    player_snap_hist: dict[str,list[float]] = defaultdict(list)
    pos_snap_sum: dict[str,float] = defaultdict(float); pos_snap_n: dict[str,int] = defaultdict(int)
    player_fam_hist: dict[str,dict[str,list[dict[str,float]]]] = defaultdict(lambda:defaultdict(list))
    pos_fam_c: dict[tuple[str,str],float] = defaultdict(float); pos_fam_e: dict[tuple[str,str],float] = defaultdict(float)

    def update_player_state(rows: Sequence[dict[str,Any]], fam_map: dict[tuple[str,str],dict[str,Any]], pfc: dict[tuple[str,str],dict[str,float]], totals: dict[tuple[str,str],float]) -> None:
        for r in sorted(rows, key=lambda x:(int(num(x.get("season"),0)),int(num(x.get("week"),0)),str(x.get("game_id") or ""),str(x.get("player_id") or ""))):
            if not truthy(r.get("eligible_standard_rate_fit")):
                continue
            pid = str(r.get("player_id") or ""); team = str(r.get("team") or ""); gid = str(r.get("game_id") or "")
            ss = wk1.snap_share(r, totals, xb); snaps = xb.num(r.get("defense_snaps"))
            if not pid or not team or not gid or ss is None or snaps is None or snaps <= 0:
                continue
            pg = tf.canonical_position_group(r)
            player_snap_hist[pid].append(float(ss)); pos_snap_sum[pg] += float(ss); pos_snap_n[pg] += 1
            fg = fam_map.get((gid, team)); fc = pfc.get((gid, pid), {f:0.0 for f in fs.FAMILIES})
            if fg is None:
                continue
            for f in fs.FAMILIES:
                exposure = float(fg.get(f"opp_{f}") or 0.0) * float(ss)
                credit = float(fc.get(f,0.0))
                player_fam_hist[pid][f].append({"credits":credit,"exposure":exposure})
                pos_fam_c[(pg,f)] += credit; pos_fam_e[(pg,f)] += exposure

    update_player_state(histex, fmh, pfc_hist, ts_hist)
    update_player_state(ex25, fm25, pfc25, ts25)
    update_player_state(ex1, fm1, pfc1, ts1)

    # ---- Strict previous role state from before each team's Week 1 game. ----
    prev_depth, prev_depth_audit = previous_week_depth(root, source_dir, week1_schedule, contract)

    # ---- Week 2 team opportunity/family forecasts. ----
    league_share = {f:(league_fam[f]/league_fam_total if league_fam_total>0 else 1.0/len(fs.FAMILIES)) for f in fs.FAMILIES}
    team_features: dict[tuple[str,str],dict[str,Any]] = {}
    xto_pred: dict[tuple[str,str],float] = {}
    family_pred: dict[tuple[str,str],dict[str,float]] = {}
    for gm in target_games:
        gid = str(gm["game_id"]); away = wk1.normteam(contract, gm.get("away_team")); home = wk1.normteam(contract, gm.get("home_team"))
        for offense, defense in ((away,home),(home,away)):
            tr = wk1.team_feature(gid,TARGET_WEEK,offense,defense,off_hist,def_hist,xb)
            team_features[(gid,defense)] = tr
            xto_pred[(gid,defense)] = xto_model.predict([float(tr[n]) for n in xb.TEAM_FEATURE_NAMES])
            os = wk1.famshare(off_fam[offense], tuple(fs.FAMILIES), fs.TEAM_WINDOW_GAMES)
            ds = wk1.famshare(def_fam[defense], tuple(fs.FAMILIES), fs.TEAM_WINDOW_GAMES)
            raw = {f:max(0.0,0.5*((os[f] if os else league_share[f])+(ds[f] if ds else league_share[f]))) for f in fs.FAMILIES}
            s = sum(raw.values()); family_pred[(gid,defense)] = {f:(raw[f]/s if s>0 else league_share[f]) for f in fs.FAMILIES}

    # ---- Emit dual-track prospective rows. ----
    dual: list[dict[str,Any]] = []; controls: list[dict[str,Any]] = []; shadows: list[dict[str,Any]] = []
    trust_counts: Counter[str] = Counter(); role_changed = 0; depth_present_n = 0
    for r in state:
        if str(r.get("research_ready") or "") != "TRUE" or str(r.get("roster_status") or "") != "ACTIVE_ROSTER" or str(r.get("game_status") or "") in {"OUT","INACTIVE"}:
            continue
        gid = str(r.get("game_id") or ""); team = wk1.normteam(contract,r.get("team")); pid = str(r.get("player_id") or "")
        pg = str(r.get("position_group") or "").upper()
        if gid not in target_game_ids or pg not in CORE or not pid or (gid,team) not in team_features:
            continue
        hist = player_snap_hist[pid]
        hrow = wk1.role_feature(pg,hist,pos_snap_sum,pos_snap_n,er)
        h012 = max(0.0,min(1.0,float(h012_model.predict(hrow))))
        shares = family_pred[(gid,team)]; xto = float(xto_pred[(gid,team)])
        per_snap = 0.0; family_rates: dict[str,float] = {}; control_credits: dict[str,float] = {}
        for f in fs.FAMILIES:
            ph = player_fam_hist[pid][f][-fs.PLAYER_FAMILY_RATE_WINDOW_GAMES:]
            pc = sum(x["credits"] for x in ph); pe = sum(x["exposure"] for x in ph)
            pr = pos_fam_c[(pg,f)]/pos_fam_e[(pg,f)] if pos_fam_e[(pg,f)]>0 else 0.15
            rate = (pc+fs.FAMILY_ALPHA*pr)/(pe+fs.FAMILY_ALPHA) if pe+fs.FAMILY_ALPHA>0 else pr
            family_rates[f] = rate; per_snap += xto*shares[f]*rate; control_credits[f] = xto*shares[f]*h012*rate
        control_xtc = max(0.0,h012*per_snap)

        rank = int(num(r.get("depth_rank"),0)); dp = str(r.get("depth_position") or "")
        prev = prev_depth.get((team,pid),{}); prev_rank = int(prev.get("depth_rank") or 0); prev_team = str(prev.get("team") or "")
        role_input = {
            "position_group":pg, "prior_games":len(hist), "week":TARGET_WEEK, "team":team,
            "depth_present":1 if rank>0 else 0, "depth_rank":rank, "depth_position":dp,
            "prev_depth_rank":prev_rank, "prev_depth_team":prev_team, "prev_depth_present":1 if prev_rank>0 else 0,
            "promoted_to_rank1":1 if rank==1 and prev_rank>=2 else 0,
            "demoted_from_rank1":1 if prev_rank==1 and rank>=2 else 0,
            "rank_improvement":max(0,prev_rank-rank) if rank and prev_rank else 0,
            "rank_demotion":max(0,rank-prev_rank) if rank and prev_rank else 0,
            "last4_snap_share_std":er.std_or_zero(hist[-4:]),
        }
        role_ss = float(role_model.predict(role_input,h012))
        role_xtc = max(0.0,role_ss*per_snap)
        if abs(role_ss-h012) > 1e-12: role_changed += 1
        if rank>0: depth_present_n += 1
        trust = role_state(rank,h012); trust_counts[trust] += 1
        preferred = rank>0 and trust != "REVIEW_BACKUP_CONFLICT"
        control_tier = dist.role_tier(h012)

        base = {
            "captured_at":source_manifest.get("capturedAt"), "pregame_source_snapshot":source_id,
            "game_id":gid, "season":SEASON, "week":TARGET_WEEK, "kickoff_utc":r.get("kickoff_utc"),
            "team":team, "opponent":wk1.normteam(contract,r.get("opponent")), "player_id":pid,
            "player_name":r.get("player_name"), "position":r.get("position"), "position_group":pg,
            "prior_games":len(hist), "availability_authority":r.get("availability_authority"),
            "game_status":r.get("game_status"), "injury_designation":r.get("injury_designation"),
            "listed_starter":r.get("listed_starter"), "depth_role":r.get("depth_role"),
            "verified_ready":r.get("verified_ready") or "FALSE", "verified_block_reason":r.get("verified_block_reason") or "NO_AUTHORITATIVE_GAME_DAY_INACTIVE_SOURCE",
            "current_depth_rank":rank, "current_depth_position":dp, "previous_week_depth_rank":prev_rank,
            "previous_week_depth_team":prev_team, "previous_week_depth_position":prev.get("depth_position",""),
            "role_state":trust, "week2_preferred_exposure_challenger":"TRUE" if preferred else "FALSE",
            "starter_conflict_warning":"TRUE" if trust=="STARTER_CONFLICT_REVIEW" else "FALSE",
            "backup_conflict_quarantine":"TRUE" if trust=="REVIEW_BACKUP_CONFLICT" else "FALSE",
            "predicted_xto":xto,
        }
        for f in fs.FAMILIES:
            base[f"pred_share_{f}"] = shares[f]; base[f"shrunk_rate_{f}"] = family_rates[f]; base[f"control_pred_credit_{f}"] = control_credits[f]

        c = canonical_track(base,track="FROZEN_OMEGA_CONTROL",snap=h012,xtc=control_xtc,tier=control_tier,params=nb_params,dist=dist)
        c["probability_status"] = "CONTROL_FROZEN_NB_ROLE"
        controls.append(c)

        srow = canonical_track(base,track="CURRENT_ROLE_POINT_SHADOW",snap=role_ss,xtc=role_xtc,tier=control_tier,params=nb_params,dist=dist)
        srow["probability_status"] = "SHADOW_ONLY_ROLE_POINT_MEAN_FIXED_CONTROL_DISPERSION"
        srow["distribution_tier_source"] = "CONTROL_H012_FIXED"
        shadows.append(srow)

        z = dict(base)
        z.update({
            "control_h012_snap_share":h012, "role_point_snap_share":role_ss, "role_correction":role_ss-h012,
            "control_xtc":control_xtc, "role_point_xtc":role_xtc, "role_point_xtc_delta":role_xtc-control_xtc,
            "control_distribution_role_tier":control_tier,
            "role_shadow_distribution_role_tier":control_tier,
            "role_shadow_dispersion_policy":"FIXED_CONTROL_H012_TIER",
            "full_snap_mixture_status":"RESEARCH_ONLY_NOT_EMITTED",
        })
        add_probabilities(z,prefix="control_",mean=control_xtc,tier=control_tier,dist=dist,params=nb_params)
        add_probabilities(z,prefix="role_shadow_",mean=role_xtc,tier=control_tier,dist=dist,params=nb_params)
        dual.append(z)

    if not dual:
        raise SystemExit("FAIL no Week 2 dual-track rows emitted")
    emitted_games = {r["game_id"] for r in dual}
    if emitted_games != target_game_ids:
        raise SystemExit(f"FAIL Week 2 forecast game coverage mismatch; missing={sorted(target_game_ids-emitted_games)}")
    role_coverage = depth_present_n/len(dual)
    if role_coverage < MIN_ROLE_COVERAGE:
        raise SystemExit(f"FAIL Week 2 current-depth coverage {role_coverage:.1%} below operational floor {MIN_ROLE_COVERAGE:.0%}")

    # Fail if any output field looks like market input. Fair-price arithmetic is intentionally absent from dual track.
    forbidden_tokens = ("book", "sportsbook", "market_price", "american_price", "edge", "expected_roi", "settlement")
    fields = set().union(*(r.keys() for r in dual))
    bad = sorted(c for c in fields if any(t in c.lower() for t in forbidden_tokens))
    if bad:
        raise SystemExit(f"FAIL forbidden market-like output fields: {bad}")

    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    seed = f"{source_id}|{results_meta.get('snapshotId')}|{snap_meta.get('snapshotId')}|{role_oid}|W2".encode()
    freeze_id = f"{stamp}_{hashlib.sha256(seed).hexdigest()[:8]}"
    base_dir = root/"data/prospective/nfl/omega_week2_dual_track_0330"
    final = base_dir/freeze_id; staging = base_dir/("."+freeze_id+".staging")
    if final.exists() or staging.exists():
        raise SystemExit(f"FAIL duplicate immutable Week 2 freeze id: {freeze_id}")
    staging.mkdir(parents=True,exist_ok=False)
    try:
        dual_path = staging/"OMEGA_0.33_WEEK2_DUAL_TRACK.csv"
        control_path = staging/"OMEGA_0.33_WEEK2_CONTROL_PROBABILITIES.csv"
        shadow_path = staging/"OMEGA_0.33_WEEK2_ROLE_POINT_SHADOW_PROBABILITIES.csv"
        wcsv(dual_path,dual); wcsv(control_path,controls); wcsv(shadow_path,shadows)

        packaged = nowdt()
        if packaged >= earliest_kickoff:
            raise SystemExit("FAIL OMEGA 0.33 packaging reached/occurred after earliest Week 2 kickoff; freeze prohibited")

        trust = dict(sorted(trust_counts.items()))
        manifest = {
            "schemaVersion":SCHEMA, "version":VERSION, "freezeId":freeze_id,
            "startedAt":started.isoformat().replace("+00:00","Z"), "packagedAt":packaged.isoformat().replace("+00:00","Z"),
            "season":SEASON, "week":TARGET_WEEK, "earliestKickoffUtc":earliest_kickoff.astimezone(timezone.utc).isoformat().replace("+00:00","Z"),
            "packagedAfterEarliestKickoff":packaged>=earliest_kickoff,
            "pregameSource":{"snapshotId":source_id,"capturedAt":source_manifest.get("capturedAt"),"manifestSha256":sha(source_manifest_path),"rows":len(state),"games":len(target_games)},
            "prior2026State":{
                "admittedWeeks":[PRIOR_WEEK], "week2OutcomeRowsMaterialized":0,
                "resultsSnapshotId":results_meta.get("snapshotId"), "resultsManifestSha256":sha(results_manifest_path),
                "scheduleSha256":sched_asset.get("sha256"), "pbpSha256":pbp26_asset.get("sha256"),
                "snapSnapshotId":snap_meta.get("snapshotId"), "snapSha256":snap_meta.get("sha256"),
                "scheduledWeek1Games":len(week1_game_ids), "completedWeek1Games":len(week1_game_ids),
                "week1GameIds":sorted(week1_game_ids), "pbpAudit":pbp_week1_audit,
                "snapAudit":snap_week1_audit, "exposureAudit":ex1_audit,
            },
            "frozenModels":{
                "omegaSourceSnapshotId":model_sid, "globalModelsSha256":sha(global_models_path),
                "probabilitySpecSha256":sha(prob_spec_path), "distributionFamily":"NB_ROLE",
                "modelRefits":0, "coefficientsChanged":False,
            },
            "roleChallenger":{
                "artifactId":role_oid,"modelSha256":role_model_sha,"sourceAuditVerdict":role_audit.get("verdict"),
                "confirmatoryReport":str(confirm_path.relative_to(root)),"confirmatoryReportSha256":sha(confirm_path),
                "confirmatoryVerdict":confirm.get("verdict"),"confirmatoryDepthCoverage":confirm.get("coverage",{}).get("depthCoverage"),
                "preferredExposureUniverse":"depth-covered AND NOT backup-conflict",
                "starterConflictPolicy":"challenger eligible but explicit review warning; no post-hoc removal after 0.32",
                "backupConflictPolicy":"quarantined regardless of favorable post-holdout diagnostic",
            },
            "previousRoleState":prev_depth_audit,
            "forecast":{"rows":len(dual),"games":len(emitted_games),"depthCoverage":role_coverage,"roleChangedRows":role_changed,"trustStateCounts":trust},
            "trackStatus":{
                "control":"FROZEN_OMEGA_CONTROL",
                "rolePoint":"PREFERRED_EXPOSURE_CHALLENGER_WHEN_ELIGIBLE",
                "roleProbability":"PROSPECTIVE_SHADOW_ONLY_FIXED_CONTROL_DISPERSION",
                "fullSnapMixture":"RESEARCH_ONLY_NOT_EMITTED",
            },
            "integrity":{
                "frozenOmegaWrites":0,"modelRefits":0,"hyperparameterSearches":0,"week2OutcomeRowsMaterialized":0,
                "marketFieldsRead":0,"oddsPapiRequests":0,"targetWeekSnapOutcomesRead":0,
                "week1StateAdmittedOnlyAfterCompletion":True,"pregameSourceCapturedBeforeEarliestKickoff":source_capture<earliest_kickoff,
                "packagedBeforeEarliestKickoff":packaged<earliest_kickoff,"authoritativeInactiveOverlayIntegrated":False,
            },
        }
        manifest_path = staging/"OMEGA_0.33_WEEK2_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        hashes = {p.name:sha(p) for p in (dual_path,control_path,shadow_path,manifest_path)}
        (staging/"OMEGA_OUTPUT_HASHES.json").write_text(json.dumps(hashes,indent=2)+"\n",encoding="utf-8")
        os.replace(staging,final)
        atomic_text(root/"data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_DUAL_TRACK_FREEZE", freeze_id+"\n")
    except BaseException:
        shutil.rmtree(staging,ignore_errors=True)
        raise

    print("OMEGA 0.33 — WEEK 2 PRIOR-STATE ADMISSION + DUAL-TRACK PROSPECTIVE FREEZE")
    print(f"PASS freeze {freeze_id} · Week 2 games {len(emitted_games)} · forecasts {len(dual)}")
    print(f"PASS Week 1 prior state: scheduled/completed/PBP/snap games {len(week1_game_ids)}/{len(week1_game_ids)}/{pbp_week1_audit['games']}/{snap_week1_audit['games']}")
    print(f"PASS admitted 2026 outcomes: Week 1 only · Week 2 outcome rows 0")
    print(f"PASS CONTROL frozen H008+H012 + NB_ROLE · serialized models only · refits 0")
    print(f"PASS ROLE_POINT artifact {role_oid} · 0.31 {confirm.get('verdict')} · current-depth coverage {role_coverage:.1%}")
    print(f"TRUST STATES: {dict(sorted(trust_counts.items()))}")
    print("PASS role probability is SHADOW ONLY with CONTROL dispersion tier fixed · full mixture NOT EMITTED")
    print("PASS market fields 0 · OddsPapi 0 · frozen OMEGA writes 0 · authoritative inactive overlay NO")
    print("TOP ROLE-POINT SHIFTS:")
    for r in sorted(dual,key=lambda z:abs(num(z.get("role_correction"))),reverse=True)[:15]:
        print(f"  {r['game_id']} · {r['team']} {r['player_name']}: H012 {100*num(r['control_h012_snap_share']):.1f}% -> ROLE {100*num(r['role_point_snap_share']):.1f}% · xTC {num(r['control_xtc']):.2f}->{num(r['role_point_xtc']):.2f} · {r['role_state']}")
    print(f"MANIFEST: {final/'OMEGA_0.33_WEEK2_MANIFEST.json'}")
    print(f"CONTROL: {final/'OMEGA_0.33_WEEK2_CONTROL_PROBABILITIES.csv'}")
    print(f"ROLE SHADOW: {final/'OMEGA_0.33_WEEK2_ROLE_POINT_SHADOW_PROBABILITIES.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""OMEGA 0.31.4 strict pregame adapter for nflverse 2025+ ESPN depth schema.

Repairs the 0.31.3 plumbing bug that treated pos_grp labels such as DB/LB/DL as
non-defense because they did not literally contain "DEF".  The blind evaluation
universe already contains only defensive-snap players, so this adapter keeps all
non-explicitly-offense/special-team depth rows and lets the GSIS join determine
relevance.  It also fails closed before scoring if blind-row depth coverage is <80%.

No model coefficients, features, gates, or frozen artifacts are changed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any
import csv
import json

MIN_BLIND_DEPTH_COVERAGE = 0.80


def rcsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


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


def load_game_dates(root: Path, sid: str, game_ids: set[str]) -> tuple[dict[str, date], str]:
    """Resolve target gamedays from already-local pinned schedule data only."""
    date_fields = ("gameday", "game_date", "date", "event_date", "start_date")
    local = [
        root / "data/normalized/nfl/phase1" / sid / "game_identity.csv",
        root / "data/normalized/nfl/phase1" / sid / "games.csv",
        root / "data/normalized/nfl/phase1" / sid / "schedule.csv",
    ]
    for p in local:
        if not p.exists():
            continue
        rows = rcsv(p)
        if not rows:
            continue
        fields = set(rows[0])
        dcol = next((x for x in date_fields if x in fields), None)
        if "game_id" not in fields or not dcol:
            continue
        out: dict[str, date] = {}
        for r in rows:
            gid = str(r.get("game_id") or "").strip()
            if gid not in game_ids:
                continue
            d = parse_date(r.get(dcol))
            if d:
                out[gid] = d
        if len(out) == len(game_ids):
            return out, f"{p}:{dcol}"

    mp = root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json"
    if mp.exists():
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        assets = sorted(manifest.get("assets", []), key=lambda a: 0 if str(a.get("source") or "").lower() == "schedules" else 1)
        for a in assets:
            source = str(a.get("source") or "").lower()
            if not any(k in source for k in ("schedule", "game")):
                continue
            bp = root / str(a.get("blobPath") or "")
            if not bp.exists():
                continue
            try:
                if bp.suffix.lower() == ".parquet":
                    import pyarrow.parquet as pq
                    pf = pq.ParquetFile(bp); fields = set(pf.schema_arrow.names)
                    dcol = next((x for x in date_fields if x in fields), None)
                    if "game_id" not in fields or not dcol:
                        continue
                    rows = pf.read(columns=["game_id", dcol]).to_pylist()
                elif bp.suffix.lower() == ".csv":
                    rows = rcsv(bp); fields = set(rows[0]) if rows else set()
                    dcol = next((x for x in date_fields if x in fields), None)
                    if "game_id" not in fields or not dcol:
                        continue
                else:
                    continue
                out: dict[str, date] = {}
                for r in rows:
                    gid = str(r.get("game_id") or "").strip()
                    if gid not in game_ids:
                        continue
                    d = parse_date(r.get(dcol))
                    if d:
                        out[gid] = d
                if len(out) == len(game_ids):
                    return out, f"{bp}:{dcol}"
            except Exception:
                continue
    raise SystemExit("FAIL cannot resolve all 2025 gamedays from already-local pinned schedule data; network fallback prohibited")


def explicitly_non_defensive_group(grp: str) -> bool:
    """Reject only groups that are explicitly offense or special teams.

    ESPN/nflverse may encode defensive groups as DB/LB/DL rather than 'Defense'.
    The downstream join is GSIS-keyed to the blind defensive-snap universe, so
    ambiguous/blank groups are safer to retain than to discard.
    """
    g = str(grp or "").strip().upper().replace("_", " ")
    if not g:
        return False
    if "SPECIAL" in g or g in {"ST", "SPECIAL TEAMS"}:
        return True
    if "OFFENSE" in g or g in {"OFF", "OL", "QB", "RB", "WR", "TE"}:
        return True
    return False


def build_depth_map(mod: Any, root: Path, depth25: Path, depth25_sha: str):
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(depth25); names = set(pf.schema_arrow.names)
    legacy = {"week", "gsis_id", "depth_team"}
    if legacy <= names:
        raise RuntimeError("LEGACY_SCHEMA_DELEGATE")

    required = {"dt", "team", "gsis_id", "pos_rank"}
    if not required <= names:
        raise SystemExit(f"FAIL unsupported 2025 depth schema; missing {sorted(required-names)}; columns={sorted(names)}")

    blind_path = root / "data/models/nfl/omega_tackle_012_blind_2025" / mod.EXPECTED_SID / "OMEGA_2025_BLIND_PREDICTIONS.csv"
    blind = rcsv(blind_path)
    game_ids = {str(r["game_id"]) for r in blind}
    game_dates, date_source = load_game_dates(root, mod.EXPECTED_SID, game_ids)

    team_game: dict[tuple[int, str], tuple[str, date]] = {}
    for r in blind:
        week = int(r["week"]); team = mod.normteam(r["team"]); gid = str(r["game_id"])
        gd = game_dates.get(gid)
        if gd is None:
            raise SystemExit(f"FAIL missing gameday for {gid}")
        old = team_game.get((week, team))
        if old is not None and old[0] != gid:
            raise SystemExit(f"FAIL multiple target games for team/week {(week, team)}")
        team_game[(week, team)] = (gid, gd)

    cols = [x for x in ("dt", "team", "gsis_id", "pos_grp", "pos_name", "pos_abb", "pos_slot", "pos_rank") if x in names]
    raw = pf.read(columns=cols).to_pylist()

    rows_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    usable = 0; rejected_explicit_nondef = 0
    grp_counts: Counter[str] = Counter()
    for r in raw:
        grp = str(r.get("pos_grp") or "").strip().upper()
        grp_counts[grp or "<BLANK>"] += 1
        if explicitly_non_defensive_group(grp):
            rejected_explicit_nondef += 1
            continue
        pid = str(r.get("gsis_id") or "").strip(); team = mod.normteam(r.get("team"))
        rank = int(mod.num(r.get("pos_rank"), 0) or 0); d = parse_date(r.get("dt"))
        if not pid or not team or rank <= 0 or d is None:
            continue
        usable += 1
        rows_by_team[team].append({
            "dt": str(r.get("dt") or "").strip(), "dt_date": d, "team": team,
            "player_id": pid, "depth_rank": rank,
            "depth_position": str(r.get("pos_abb") or r.get("pos_name") or "").strip(),
            "pos_grp": grp,
        })

    best: dict[tuple[int, str, str], dict[str, Any]] = {}
    selected_snapshots: dict[tuple[int, str], str] = {}
    missing_team_snapshots: list[tuple[int, str]] = []

    for (week, team), (_gid, gameday) in sorted(team_game.items()):
        eligible = [r for r in rows_by_team.get(team, []) if r["dt_date"] < gameday]
        if not eligible:
            missing_team_snapshots.append((week, team))
            continue
        latest_date = max(r["dt_date"] for r in eligible)
        day_rows = [r for r in eligible if r["dt_date"] == latest_date]
        latest_dt = max(str(r["dt"]) for r in day_rows)
        snapshot = [r for r in day_rows if str(r["dt"]) == latest_dt]
        selected_snapshots[(week, team)] = latest_dt

        bypid: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in snapshot:
            bypid[str(r["player_id"])].append(r)
        for pid, rr in bypid.items():
            cur = sorted(rr, key=lambda z: (int(z["depth_rank"]), str(z["depth_position"])))[0]
            best[(week, team, pid)] = {
                "season": 2025, "week": week, "team": team, "player_id": pid,
                "depth_rank": int(cur["depth_rank"]), "depth_position": str(cur["depth_position"]),
                "source_dt": latest_dt, "source_dt_date": latest_date.isoformat(),
            }

    # Seed strictly-prior role state from frozen 2024 history.
    aid = mod.EXPECTED_DEPTH_AUDIT
    adir = root / "data/raw/nfl/omega/depth_chart_source_audits" / aid
    audit = json.loads((adir / "OMEGA_DEPTH_CHART_SOURCE_AUDIT.json").read_text(encoding="utf-8"))
    a24 = next((a for a in audit.get("assets", []) if int(a.get("year") or 0) == 2024), None)
    if not a24:
        raise SystemExit("FAIL 2024 depth asset absent from frozen audit")
    p24 = adir / str(a24.get("filename") or "")
    if not p24.exists() or mod.sha256_file(p24) != a24.get("sha256"):
        raise SystemExit("FAIL 2024 depth asset hash mismatch")
    rows24 = mod.read_depth_rows(p24, 2024)

    prev_by_pid: dict[str, dict[str, Any]] = {}
    for r in sorted(rows24, key=lambda z: (int(z["week"]), -int(z["depth_rank"]))):
        pid = str(r["player_id"]); old = prev_by_pid.get(pid)
        if old is None or int(r["week"]) > int(old["week"]) or (int(r["week"]) == int(old["week"]) and int(r["depth_rank"]) < int(old["depth_rank"])):
            prev_by_pid[pid] = dict(r)

    for week in sorted({k[0] for k in best}):
        group = [r for (w, _team, _pid), r in best.items() if w == week]
        for r in group:
            prev = prev_by_pid.get(str(r["player_id"]))
            r["prev_depth_rank"] = int(prev["depth_rank"]) if prev else 0
            r["prev_depth_team"] = str(prev["team"]) if prev else ""
            r["prev_depth_position"] = str(prev.get("depth_position") or "") if prev else ""
        current_by_pid: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in group:
            current_by_pid[str(r["player_id"])].append(r)
        for pid, rr in current_by_pid.items():
            prev_by_pid[pid] = sorted(rr, key=lambda z: (int(z["depth_rank"]), str(z["team"])))[0]

    matched_blind = 0
    for r in blind:
        key = (int(r["week"]), mod.normteam(r["team"]), str(r["player_id"]))
        if key in best:
            matched_blind += 1
    blind_cov = matched_blind / len(blind) if blind else 0.0
    if blind_cov < MIN_BLIND_DEPTH_COVERAGE:
        top_groups = dict(grp_counts.most_common(12))
        raise SystemExit(
            f"FAIL 2025 depth coverage {blind_cov:.1%} below pre-score floor {MIN_BLIND_DEPTH_COVERAGE:.0%}; "
            f"matched {matched_blind}/{len(blind)}; usable rows {usable}; team-week snapshots {len(selected_snapshots)}/{len(team_game)}; "
            f"missing snapshots {len(missing_team_snapshots)}; pos_grp sample {top_groups}"
        )

    meta = {
        "depthAudit2024": aid,
        "depth2024Sha256": a24.get("sha256"),
        "depth2025Sha256": depth25_sha,
        "depth2025Schema": "ESPN_DT_POS_RANK",
        "depth2025RawRows": len(raw),
        "depth2025RowsUsableAfterExplicitNonDefenseFilter": usable,
        "depth2025RowsRejectedExplicitNonDefense": rejected_explicit_nondef,
        "depth2025PosGroupCountsTop12": dict(grp_counts.most_common(12)),
        "depth2025UniquePlayerWeeks": len(best),
        "depth2025SelectedTeamWeekSnapshots": len(selected_snapshots),
        "depth2025MissingTeamWeekSnapshots": len(missing_team_snapshots),
        "depth2025BlindRowsMatched": matched_blind,
        "depth2025BlindCoverage": blind_cov,
        "depth2025CoverageFloor": MIN_BLIND_DEPTH_COVERAGE,
        "depth2025SelectionRule": "latest exact TEAM snapshot on a calendar date STRICTLY BEFORE target gameday; same-day excluded; stale per-player rows excluded",
        "previousRoleRule": "strictly earlier NFL week; Week 1 seeded from latest 2024 historical depth state",
        "gameDateSource": date_source,
        "networkRequestsForSchedule": 0,
    }
    return best, meta

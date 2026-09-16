#!/usr/bin/env python3
"""OMEGA 0.31.2 implementation hardening for the frozen 0.31 protocol.

Adds an evaluation-only adapter for nflverse's 2025+ ESPN depth-chart schema
(dt/team/gsis_id/pos_*/pos_rank).  The frozen 0.31 gates and the fitted 0.2.7 model
are unchanged.

For each 2025 team-game, current role state is the latest depth snapshot whose
calendar date is STRICTLY BEFORE the game's gameday.  Same-day snapshots are
excluded conservatively because the source timestamp timezone and kickoff relation
need not be inferred.  Previous-role features are taken only from an earlier NFL
week (Week 1 falls back to the latest 2024 historical depth state).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
import csv
import importlib.util
import json
import sys


def rcsv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def parse_date(v: Any) -> date | None:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        # Handles ISO timestamps and plain YYYY-MM-DD.
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(s[:10])
        except Exception:
            return None


def load_game_dates(root: Path, sid: str, game_ids: set[str]) -> tuple[dict[str, date], str]:
    """Load already-local schedule dates; never make a network request."""
    candidates = [
        root / "data/normalized/nfl/phase1" / sid / "game_identity.csv",
        root / "data/normalized/nfl/phase1" / sid / "games.csv",
        root / "data/normalized/nfl/phase1" / sid / "schedule.csv",
    ]
    date_fields = ("gameday", "game_date", "date", "event_date", "start_date")
    for p in candidates:
        if not p.exists():
            continue
        rows = rcsv(p)
        if not rows:
            continue
        fields = set(rows[0])
        dcol = next((x for x in date_fields if x in fields), None)
        if "game_id" not in fields or not dcol:
            continue
        out = {}
        for r in rows:
            gid = str(r.get("game_id") or "").strip()
            if gid in game_ids:
                d = parse_date(r.get(dcol))
                if d:
                    out[gid] = d
        if len(out) == len(game_ids):
            return out, f"{p}:{dcol}"

    # Fallback to an already-pinned raw source asset from the frozen snapshot.
    mp = root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json"
    if mp.exists():
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        for a in manifest.get("assets", []):
            name = str(a.get("source") or "").lower()
            if not any(k in name for k in ("schedule", "game")):
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
                out = {}
                for r in rows:
                    gid = str(r.get("game_id") or "").strip()
                    if gid in game_ids:
                        d = parse_date(r.get(dcol))
                        if d:
                            out[gid] = d
                if len(out) == len(game_ids):
                    return out, f"{bp}:{dcol}"
            except Exception:
                continue
    raise SystemExit("FAIL cannot resolve all 2025 game dates from already-local pinned schedule data; no network fallback allowed")


def install_eval_builder(root: Path):
    helper = root / "scripts/nfl/score_omega_2025_current_role_holdout_0311.py"
    spec = importlib.util.spec_from_file_location("omega0311_feature_shim", helper)
    if spec is None or spec.loader is None:
        raise SystemExit("FAIL cannot load OMEGA 0.31.1 feature shim")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    mod.install_eval_only_feature_builder(root)


def main() -> int:
    root = Path("/Users/abbeyfelix/Developer/MODEL").resolve()
    for i, arg in enumerate(sys.argv[:-1]):
        if arg == "--root":
            root = Path(sys.argv[i + 1]).expanduser().resolve()
            break

    install_eval_builder(root)

    scorer_path = root / "scripts/nfl/score_omega_2025_current_role_holdout_0310.py"
    spec = importlib.util.spec_from_file_location("omega031_frozen_protocol_scorer", scorer_path)
    if spec is None or spec.loader is None:
        raise SystemExit("FAIL cannot load OMEGA 0.31 scorer")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    # Keep the 0.31.1 empty-subgroup formatting hardening.
    original_compare = mod.compare
    def safe_compare(rows):
        if rows:
            return original_compare(rows)
        empty = {"n": 0, "actualMean": 0.0, "predictedMean": 0.0, "mae": 0.0, "rmse": 0.0, "biasPredMinusActual": 0.0}
        return {"n": 0, "h012": dict(empty), "role": dict(empty), "maeImprovement": 0.0, "rmseImprovement": 0.0, "biasChangeRoleMinusH012": 0.0}
    mod.compare = safe_compare

    original_depth_map = mod.depth_map_2025
    def depth_map_2025_espn(root2: Path, depth25: Path, depth25_sha: str):
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(depth25); names = set(pf.schema_arrow.names)
        legacy = {"week", "gsis_id", "depth_team"}
        if legacy <= names:
            return original_depth_map(root2, depth25, depth25_sha)

        required = {"dt", "team", "gsis_id", "pos_rank"}
        if not required <= names:
            raise SystemExit(f"FAIL unsupported 2025 depth schema; missing {sorted(required-names)}; columns={sorted(names)}")

        # Immutable blind ledger defines the exact 2025 game/team/week universe.
        blind = rcsv(root2 / "data/models/nfl/omega_tackle_012_blind_2025" / mod.EXPECTED_SID / "OMEGA_2025_BLIND_PREDICTIONS.csv")
        game_ids = {str(r["game_id"]) for r in blind}
        game_dates, date_source = load_game_dates(root2, mod.EXPECTED_SID, game_ids)
        team_game: dict[tuple[int, str], tuple[str, date]] = {}
        for r in blind:
            w = int(r["week"]); team = mod.normteam(r["team"]); gid = str(r["game_id"])
            gd = game_dates.get(gid)
            if gd is None:
                raise SystemExit(f"FAIL no gameday for {gid}")
            old = team_game.get((w, team))
            if old is not None and old[0] != gid:
                raise SystemExit(f"FAIL multiple target games for team/week {(w, team)}")
            team_game[(w, team)] = (gid, gd)

        cols = [x for x in ("dt", "team", "gsis_id", "pos_grp", "pos_name", "pos_abb", "pos_slot", "pos_rank") if x in names]
        raw = pf.read(columns=cols).to_pylist()
        # Candidate history by team/player, defense only.
        hist: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        defense_rows = 0
        for r in raw:
            grp = str(r.get("pos_grp") or "").strip().upper()
            if grp and "DEF" not in grp:
                continue
            pid = str(r.get("gsis_id") or "").strip(); team = mod.normteam(r.get("team"))
            rank = int(mod.num(r.get("pos_rank"), 0) or 0); dt_date = parse_date(r.get("dt"))
            if not pid or not team or rank <= 0 or dt_date is None:
                continue
            defense_rows += 1
            hist[(team, pid)].append({
                "dt": str(r.get("dt") or ""), "dt_date": dt_date, "team": team, "player_id": pid,
                "depth_rank": rank,
                "depth_position": str(r.get("pos_abb") or r.get("pos_name") or "").strip(),
            })
        for z in hist.values():
            z.sort(key=lambda x: (x["dt_date"], str(x["dt"]), -int(x["depth_rank"])))

        # One conservative pregame current state per NFL week/team/player.
        best: dict[tuple[int, str, str], dict[str, Any]] = {}
        for (week, team), (_gid, gameday) in sorted(team_game.items()):
            for (t, pid), z in hist.items():
                if t != team:
                    continue
                elig = [x for x in z if x["dt_date"] < gameday]
                if not elig:
                    continue
                latest_day = max(x["dt_date"] for x in elig)
                same = [x for x in elig if x["dt_date"] == latest_day]
                # Multiple records on the chosen snapshot: strongest listed rank wins,
                # matching the historical reducer's duplicate behavior.
                cur = sorted(same, key=lambda x: (int(x["depth_rank"]), str(x["dt"])), reverse=False)[0]
                best[(week, team, pid)] = {
                    "season": 2025, "week": week, "team": team, "player_id": pid,
                    "depth_rank": int(cur["depth_rank"]), "depth_position": cur["depth_position"],
                    "source_dt": cur["dt"], "source_dt_date": cur["dt_date"].isoformat(),
                }

        # Seed previous-role state from latest 2024 historical week.
        aid = mod.EXPECTED_DEPTH_AUDIT
        adir = root2 / "data/raw/nfl/omega/depth_chart_source_audits" / aid
        audit = json.loads((adir / "OMEGA_DEPTH_CHART_SOURCE_AUDIT.json").read_text(encoding="utf-8"))
        a24 = next((a for a in audit.get("assets", []) if int(a.get("year") or 0) == 2024), None)
        if not a24:
            raise SystemExit("FAIL 2024 depth asset absent from frozen audit")
        p24 = adir / str(a24.get("filename") or "")
        if not p24.exists() or mod.sha256_file(p24) != a24.get("sha256"):
            raise SystemExit("FAIL 2024 depth asset hash mismatch")
        rows24 = mod.read_depth_rows(p24, 2024)
        prev_by_pid: dict[str, dict[str, Any]] = {}
        for r in sorted(rows24, key=lambda x: (int(x["week"]), int(x["depth_rank"]))):
            pid = str(r["player_id"]); old = prev_by_pid.get(pid)
            if old is None or int(r["week"]) > int(old["week"]) or (int(r["week"]) == int(old["week"]) and int(r["depth_rank"]) < int(old["depth_rank"])):
                prev_by_pid[pid] = dict(r)

        # Attach previous state strictly from an earlier NFL week.  All rows in a
        # week see the same pre-week state, then current state is admitted afterward.
        for week in sorted({k[0] for k in best}):
            group = [r for (w, _t, _p), r in best.items() if w == week]
            for r in group:
                prev = prev_by_pid.get(str(r["player_id"]))
                r["prev_depth_rank"] = int(prev["depth_rank"]) if prev else 0
                r["prev_depth_team"] = str(prev["team"]) if prev else ""
                r["prev_depth_position"] = str(prev.get("depth_position") or "") if prev else ""
            bypid: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in group:
                bypid[str(r["player_id"])].append(r)
            for pid, rr in bypid.items():
                prev_by_pid[pid] = sorted(rr, key=lambda x: (int(x["depth_rank"]), str(x["team"])))[0]

        meta = {
            "depthAudit2024": aid,
            "depth2024Sha256": a24.get("sha256"),
            "depth2025Sha256": depth25_sha,
            "depth2025Schema": "ESPN_DT_POS_RANK",
            "depth2025RawRows": len(raw),
            "depth2025DefenseRowsUsable": defense_rows,
            "depth2025UniquePlayerWeeks": len(best),
            "depth2025SelectionRule": "latest snapshot calendar date STRICTLY BEFORE target gameday; same-day excluded",
            "previousRoleRule": "strictly earlier NFL week; Week 1 seeded from latest 2024 historical depth state",
            "gameDateSource": date_source,
            "networkRequestsForSchedule": 0,
        }
        return best, meta

    mod.depth_map_2025 = depth_map_2025_espn
    return int(mod.main())


if __name__ == "__main__":
    raise SystemExit(main())

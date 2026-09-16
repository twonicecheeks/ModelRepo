"""Immutable nflverse -> NFL State Intelligence 0.1.0 normalization.

This is a new downstream normalized snapshot. It intentionally does not broaden or
overwrite Phase 1B normalized artifacts and does not consume market data.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import os
from typing import Any

try:
    import pyarrow.parquet as pq
except Exception as exc:  # pragma: no cover
    pq = None
    _PYARROW_IMPORT_ERROR = exc
else:
    _PYARROW_IMPORT_ERROR = None

try:
    from .contract import normalize_team_abbr
    from .snapshot import load_manifest
except ImportError:
    from contract import normalize_team_abbr
    from snapshot import load_manifest

VERSION = "0.1.0"
SCHEMA_VERSION = "1.0.0"

REQUIRED_COLUMNS = (
    "game_id", "play_id", "season", "week", "posteam", "defteam",
    "down", "ydstogo", "yardline_100", "qtr",
    "qb_dropback", "rush", "sack", "yards_gained",
    "interception", "fumble_lost", "play_type",
)
OPTIONAL_COLUMNS = (
    "drive", "game_seconds_remaining", "half_seconds_remaining",
    "score_differential", "wp", "goal_to_go",
    "no_play", "qb_kneel", "qb_scramble",
    "first_down", "first_down_rush", "first_down_pass", "first_down_penalty",
    "penalty", "penalty_type", "penalty_yards",
    "tackled_for_loss", "fumble", "qb_hit", "aborted_play",
    "complete_pass", "incomplete_pass", "air_yards", "yards_after_catch",
    "pass_attempt", "rush_attempt", "punt_attempt", "field_goal_attempt",
    "kickoff_attempt", "desc", "epa", "success",
    "ep", "wpa", "td_prob", "fg_prob",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _schema_plan(names: set[str]) -> dict[str, Any]:
    missing = [c for c in REQUIRED_COLUMNS if c not in names]
    if missing:
        raise ValueError("state-intelligence PBP missing required column(s): " + ", ".join(missing))
    selected = list(REQUIRED_COLUMNS)
    selected.extend(c for c in OPTIONAL_COLUMNS if c in names and c not in selected)
    return {
        "columns": selected,
        "optionalAvailable": [c for c in OPTIONAL_COLUMNS if c in names],
        "optionalMissing": [c for c in OPTIONAL_COLUMNS if c not in names],
    }


def _load_state_model(root: Path):
    path = root / "packages/models/nfl/game/state_intelligence.py"
    spec = importlib.util.spec_from_file_location("model_nfl_state_intelligence_010", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    if getattr(mod, "VERSION", None) != VERSION:
        raise ValueError(f"state model version drift: {getattr(mod, 'VERSION', None)} != {VERSION}")
    return mod


def _adapt_row(raw: dict[str, Any]) -> dict[str, Any]:
    row = dict(raw)
    for key in ("posteam", "defteam"):
        value = row.get(key)
        if value:
            row[key] = normalize_team_abbr(str(value).upper())

    play_type = str(row.get("play_type") or "").strip().lower()
    if "no_play" not in row:
        row["no_play"] = 1 if play_type == "no_play" else 0
    if "qb_kneel" not in row:
        row["qb_kneel"] = 1 if play_type == "qb_kneel" else 0
    if "qb_scramble" not in row:
        row["qb_scramble"] = 1 if play_type == "qb_scramble" else 0

    # nflverse commonly exports *_attempt fields for special teams. Map a
    # canonical helper without deleting the source field.
    if "punt" not in row and "punt_attempt" in row:
        row["punt"] = row.get("punt_attempt")
    return row


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")


def normalize_state_snapshot(root: Path, manifest_path: Path) -> Path:
    if pq is None:
        raise RuntimeError(f"pyarrow required for state-intelligence normalization: {_PYARROW_IMPORT_ERROR}")

    root = Path(root).resolve()
    manifest_path = Path(manifest_path).resolve()
    manifest = load_manifest(manifest_path, root=root)
    state = _load_state_model(root)

    snapshot_id = str(manifest["snapshotId"])
    out_dir = root / "data/normalized/nfl/state_intelligence_010" / snapshot_id
    if out_dir.exists():
        raise FileExistsError(f"immutable state snapshot already exists: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=False)

    season_audits: list[dict[str, Any]] = []
    source_assets = [a for a in manifest["assets"] if a.get("source") == "play_by_play"]
    try:
        for asset in sorted(source_assets, key=lambda a: int(a["season"])):
            season = int(asset["season"])
            source = root / asset["blobPath"]
            pf = pq.ParquetFile(source)
            plan = _schema_plan(set(pf.schema_arrow.names))
            raw = pf.read(columns=plan["columns"]).to_pylist()

            by_game: dict[str, list[dict[str, Any]]] = {}
            for item in raw:
                row = _adapt_row(item)
                game_id = str(row.get("game_id") or "")
                if not game_id:
                    continue
                by_game.setdefault(game_id, []).append(row)

            annotated: list[dict[str, Any]] = []
            intent_counts: Counter[str] = Counter()
            state_counts: Counter[str] = Counter()
            field_coverage: Counter[str] = Counter()
            tracked_fields = (
                "down", "ydstogo", "yardline_100", "wp", "drive", "qb_scramble",
                "first_down", "penalty", "complete_pass", "air_yards", "yards_after_catch",
            )

            for game_id in sorted(by_game):
                game_rows = state.annotate_game_states(by_game[game_id])
                for row in game_rows:
                    feat = row["state_intelligence"]
                    intent_counts[str(feat["play_intent"])] += 1
                    state_counts[str(feat["competitive_state"])] += 1
                    for field in tracked_fields:
                        if row.get(field) not in (None, ""):
                            field_coverage[field] += 1
                annotated.extend(game_rows)

            out_file = out_dir / f"NFL_STATE_INTELLIGENCE_SNAPS_{season}.jsonl"
            _write_jsonl(out_file, annotated)
            total = len(annotated)
            season_audits.append({
                "season": season,
                "sourceAssetSha256": asset["sha256"],
                "sourceRows": len(raw),
                "annotatedRows": total,
                "games": len(by_game),
                "outputFile": str(out_file.relative_to(root)),
                "outputSha256": _sha256_file(out_file),
                "optionalColumnsAvailable": plan["optionalAvailable"],
                "optionalColumnsMissing": plan["optionalMissing"],
                "playIntentCounts": dict(sorted(intent_counts.items())),
                "competitiveStateCounts": dict(sorted(state_counts.items())),
                "fieldCoveragePct": {
                    k: round(100.0 * v / total, 4) if total else None
                    for k, v in sorted(field_coverage.items())
                },
            })

        audit = {
            "schemaVersion": SCHEMA_VERSION,
            "version": VERSION,
            "createdAt": _utc_now(),
            "sourceSnapshotId": snapshot_id,
            "sourceManifest": str(manifest_path.relative_to(root)),
            "sourceManifestSha256": _sha256_file(manifest_path),
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "frozenOmegaMutation": False,
            "trainingOrRefitPerformed": False,
            "seasons": season_audits,
        }
        audit_path = out_dir / "NFL_STATE_INTELLIGENCE_AUDIT.json"
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

        pointer = root / "data/normalized/nfl/CURRENT_NFL_STATE_INTELLIGENCE"
        tmp = pointer.with_name("." + pointer.name + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
        os.replace(tmp, pointer)
        return audit_path
    except Exception:
        # Immutable snapshots are all-or-nothing. Partial failed output is removed.
        import shutil
        shutil.rmtree(out_dir, ignore_errors=True)
        raise

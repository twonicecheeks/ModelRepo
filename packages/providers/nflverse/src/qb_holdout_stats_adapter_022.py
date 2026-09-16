"""NFL QB Model 0.2.2 — single-season 2025 holdout weekly-stat adapter.

This provider is intentionally separate from the development-only 0.1.9 adapter.
It may acquire exactly the preregistered 2025 holdout season and no other season.
The caller must create the immutable holdout-opening receipt before invoking it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import ssl
import tempfile
import urllib.request
import uuid
from typing import Any, Iterable

try:
    import pyarrow.parquet as pq
except Exception as exc:  # pragma: no cover
    pq = None
    _PYARROW_IMPORT_ERROR = exc
else:
    _PYARROW_IMPORT_ERROR = None

try:
    from .contract import normalize_team_abbr
except ImportError:
    from contract import normalize_team_abbr

VERSION = "0.2.2"
HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
PARQUET_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet"
USER_AGENT = "MODEL-NFL/QB-Model-0.2.2 single-2025-holdout"

REQUIRED_FIELDS = (
    "player_id", "season", "week", "season_type", "game_id", "team",
    "completions", "attempts", "passing_yards", "sacks_suffered",
)
OPTIONAL_FIELDS = (
    "player_name", "player_display_name", "position", "position_group",
    "opponent_team", "carries", "rushing_yards", "passing_tds",
    "interceptions", "passing_air_yards", "passing_yards_after_catch",
    "passing_epa", "passing_cpoe",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def integer(v: Any) -> int | None:
    x = num(v)
    return None if x is None else int(x)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _tls_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError as exc:
        raise RuntimeError("pinned certifi unavailable; run scripts/nfl/bootstrap_phase1_python.command") from exc
    return ssl.create_default_context(cafile=certifi.where())


def _download(url: str, target: Path) -> dict[str, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=180, context=_tls_context()) as resp, target.open("wb") as out:
        shutil.copyfileobj(resp, out, length=1024 * 1024)
        return {
            "etag": resp.headers.get("ETag"),
            "lastModified": resp.headers.get("Last-Modified"),
            "contentType": resp.headers.get("Content-Type"),
            "finalUrl": resp.geturl(),
        }


def normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    team_raw = clean(raw.get("team")).upper()
    opp_raw = clean(raw.get("opponent_team")).upper()
    return {
        "player_id": clean(raw.get("player_id")),
        "season": integer(raw.get("season")),
        "week": integer(raw.get("week")),
        "season_type": clean(raw.get("season_type")).upper(),
        "game_id": clean(raw.get("game_id")),
        "team": normalize_team_abbr(team_raw) if team_raw else "",
        "opponent_team": normalize_team_abbr(opp_raw) if opp_raw else "",
        "player_name": clean(raw.get("player_name")),
        "player_display_name": clean(raw.get("player_display_name")),
        "position": clean(raw.get("position")).upper(),
        "position_group": clean(raw.get("position_group")).upper(),
        "completions": num(raw.get("completions")),
        "attempts": num(raw.get("attempts")),
        "passing_yards": num(raw.get("passing_yards")),
        "sacks_suffered": num(raw.get("sacks_suffered")),
        "carries": num(raw.get("carries")),
        "rushing_yards": num(raw.get("rushing_yards")),
        "passing_tds": num(raw.get("passing_tds")),
        "interceptions": num(raw.get("interceptions")),
        "passing_air_yards": num(raw.get("passing_air_yards")),
        "passing_yards_after_catch": num(raw.get("passing_yards_after_catch")),
        "passing_epa": num(raw.get("passing_epa")),
        "passing_cpoe": num(raw.get("passing_cpoe")),
    }


def acquire_2025_holdout(root: Path, target_player_ids: Iterable[str]) -> Path:
    """Acquire exactly 2025 weekly player stats into immutable holdout directories."""
    if pq is None:
        raise RuntimeError(f"pyarrow required: {_PYARROW_IMPORT_ERROR}")
    ids = {clean(x) for x in target_player_ids if clean(x)}
    if not ids:
        raise ValueError("target_player_ids cannot be empty")

    root = Path(root).resolve()
    sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    raw_stage = root / "data/raw/nfl/nflverse/qb_holdout_stats_022" / ("." + sid + ".staging")
    raw_final = root / "data/raw/nfl/nflverse/qb_holdout_stats_022" / sid
    norm_stage = root / "data/normalized/nfl/qb_holdout_stats_022" / ("." + sid + ".staging")
    norm_final = root / "data/normalized/nfl/qb_holdout_stats_022" / sid
    raw_stage.mkdir(parents=True, exist_ok=False)
    norm_stage.mkdir(parents=True, exist_ok=False)

    try:
        url = PARQUET_URL.format(season=HOLDOUT_SEASON)
        print("DOWNLOAD official weekly player stats 2025 · HOLDOUT OPEN")
        fd, temp_name = tempfile.mkstemp(prefix="stats_player_week_2025_", suffix=".parquet", dir=str(raw_stage))
        os.close(fd)
        temp = Path(temp_name)
        meta = _download(url, temp)
        if temp.stat().st_size <= 0:
            raise RuntimeError("empty 2025 weekly player-stat asset")
        digest = sha256_file(temp)
        blob = root / "data/raw/nfl/nflverse/blobs" / digest[:2] / digest
        blob.parent.mkdir(parents=True, exist_ok=True)
        if blob.exists():
            if sha256_file(blob) != digest:
                raise RuntimeError(f"content-addressed holdout blob mismatch: {blob}")
            temp.unlink()
        else:
            os.replace(temp, blob)

        pf = pq.ParquetFile(blob)
        names = set(pf.schema_arrow.names)
        missing = [c for c in REQUIRED_FIELDS if c not in names]
        if missing:
            raise ValueError("2025 weekly player stats missing fields: " + ", ".join(missing))
        selected = list(REQUIRED_FIELDS) + [c for c in OPTIONAL_FIELDS if c in names]
        raw_rows = pf.read(columns=selected).to_pylist()
        kept: list[dict[str, Any]] = []
        for raw in raw_rows:
            if integer(raw.get("season")) != HOLDOUT_SEASON:
                continue
            if clean(raw.get("season_type")).upper() != "REG":
                continue
            if clean(raw.get("player_id")) not in ids:
                continue
            row = normalize_row(raw)
            row["source_sha256"] = digest
            row["source_url"] = url
            kept.append(row)
        kept.sort(key=lambda r: (r.get("week") or 0, r.get("game_id") or "", r.get("player_id") or ""))

        manifest = {
            "version": VERSION,
            "snapshotId": sid,
            "createdAt": utc_now(),
            "provider": "nflverse",
            "analysisSeason": HOLDOUT_SEASON,
            "holdoutOpened": True,
            "prospectiveSeason": PROSPECTIVE_SEASON,
            "prospectiveRead": False,
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "frozenOmegaMutation": False,
            "asset": {
                "source": "player_stats_weekly",
                "season": HOLDOUT_SEASON,
                "url": url,
                "sha256": digest,
                "bytes": blob.stat().st_size,
                "blobPath": str(blob.relative_to(root)),
                "fetchedAt": utc_now(),
                **meta,
            },
        }
        (raw_stage / "QB_2025_HOLDOUT_STATS_SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        with (norm_stage / "NFL_QB_2025_HOLDOUT_WEEKLY_STATS.jsonl").open("w", encoding="utf-8") as f:
            for row in kept:
                f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        audit = {
            "version": VERSION,
            "snapshotId": sid,
            "createdAt": utc_now(),
            "holdoutSeason": HOLDOUT_SEASON,
            "holdoutOpened": True,
            "prospectiveRead": False,
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "frozenOmegaMutation": False,
            "targetPlayerIds": len(ids),
            "rawRows": len(raw_rows),
            "normalizedTargetPlayerRows": len(kept),
            "selectedFields": selected,
        }
        (norm_stage / "NFL_QB_2025_HOLDOUT_WEEKLY_STATS_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        os.replace(raw_stage, raw_final)
        os.replace(norm_stage, norm_final)
        print(f"PASS official 2025 holdout stats · target-player REG rows {len(kept):,}")
        return norm_final
    except Exception:
        shutil.rmtree(raw_stage, ignore_errors=True)
        shutil.rmtree(norm_stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    print(f"NFL QB 2025 holdout weekly stats adapter {VERSION}")

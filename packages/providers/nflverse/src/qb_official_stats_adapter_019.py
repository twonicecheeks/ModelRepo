"""NFL QB State 0.1.9 — immutable official weekly player-stat supplement.

Development-only acquisition for 2016-2024. The source is nflverse weekly player
stats, whose player_id is GSIS identity. This adapter exists to make official-like
box-score targets authoritative while keeping play-by-play as the mechanism layer.

The sealed 2025 holdout is never requested or read here.
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

VERSION = "0.1.9"
SCHEMA_VERSION = "1.0.0"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
RELEASE_TAG = "stats_player"
PARQUET_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet"
USER_AGENT = "MODEL-NFL/QB-State-0.1.9 official-weekly-target-audit"

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


def snapshot_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]


def assert_development_only(seasons: Iterable[int]) -> tuple[int, ...]:
    values = tuple(sorted({int(s) for s in seasons}))
    if not values:
        raise ValueError("at least one development season is required")
    bad = [s for s in values if s >= SEALED_HOLDOUT_SEASON]
    if bad:
        raise ValueError(
            "QB official stats 0.1.9 acquisition forbids sealed 2025 / prospective 2026+: "
            + ",".join(map(str, bad))
        )
    return values


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
    opponent_raw = clean(raw.get("opponent_team")).upper()
    out = {
        "player_id": clean(raw.get("player_id")),
        "season": integer(raw.get("season")),
        "week": integer(raw.get("week")),
        "season_type": clean(raw.get("season_type")).upper(),
        "game_id": clean(raw.get("game_id")),
        "team": normalize_team_abbr(team_raw) if team_raw else "",
        "opponent_team": normalize_team_abbr(opponent_raw) if opponent_raw else "",
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
    return out


def acquire_and_normalize(root: Path, seasons: Iterable[int], target_player_ids: Iterable[str]) -> Path:
    """Download immutable weekly player stats and retain target-player REG rows.

    Returns the normalized snapshot directory. All source parquet assets are retained
    content-addressed; normalized rows are only for the GSIS IDs needed by 0.1.9.
    """
    if pq is None:
        raise RuntimeError(f"pyarrow required: {_PYARROW_IMPORT_ERROR}")
    seasons = assert_development_only(seasons)
    target_ids = {clean(x) for x in target_player_ids if clean(x)}
    if not target_ids:
        raise ValueError("target_player_ids cannot be empty")

    root = Path(root).resolve()
    sid = snapshot_id()
    raw_stage = root / "data/raw/nfl/nflverse/qb_official_stats_snapshots" / ("." + sid + ".staging")
    raw_final = root / "data/raw/nfl/nflverse/qb_official_stats_snapshots" / sid
    norm_stage = root / "data/normalized/nfl/qb_official_stats_019" / ("." + sid + ".staging")
    norm_final = root / "data/normalized/nfl/qb_official_stats_019" / sid
    raw_stage.mkdir(parents=True, exist_ok=False)
    norm_stage.mkdir(parents=True, exist_ok=False)

    assets: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    season_audits: list[dict[str, Any]] = []
    try:
        for season in seasons:
            url = PARQUET_URL.format(season=season)
            print(f"DOWNLOAD official weekly player stats {season}")
            fd, temp_name = tempfile.mkstemp(prefix=f"stats_player_week_{season}_", suffix=".parquet", dir=str(raw_stage))
            os.close(fd)
            temp = Path(temp_name)
            meta = _download(url, temp)
            if temp.stat().st_size <= 0:
                raise RuntimeError(f"empty weekly player-stat asset: {url}")
            digest = sha256_file(temp)
            blob = root / "data/raw/nfl/nflverse/blobs" / digest[:2] / digest
            blob.parent.mkdir(parents=True, exist_ok=True)
            if blob.exists():
                if sha256_file(blob) != digest:
                    raise RuntimeError(f"content-addressed weekly-stat blob mismatch: {blob}")
                temp.unlink()
            else:
                os.replace(temp, blob)

            pf = pq.ParquetFile(blob)
            names = set(pf.schema_arrow.names)
            missing = [c for c in REQUIRED_FIELDS if c not in names]
            if missing:
                raise ValueError(f"{season} weekly player stats missing fields: {', '.join(missing)}")
            selected = list(REQUIRED_FIELDS) + [c for c in OPTIONAL_FIELDS if c in names]
            raw_rows = pf.read(columns=selected).to_pylist()
            kept = []
            for raw in raw_rows:
                if clean(raw.get("season_type")).upper() != "REG":
                    continue
                if clean(raw.get("player_id")) not in target_ids:
                    continue
                row = normalize_row(raw)
                row["source_sha256"] = digest
                row["source_url"] = url
                kept.append(row)
            kept.sort(key=lambda r: (r.get("season") or 0, r.get("week") or 0, r.get("game_id") or "", r.get("player_id") or ""))
            all_rows.extend(kept)
            season_audits.append({
                "season": season,
                "rawRows": len(raw_rows),
                "targetRows": len(kept),
                "selectedFields": selected,
                "schemaFields": sorted(names),
            })
            assets.append({
                "source": "player_stats_weekly",
                "season": season,
                "filename": f"stats_player_week_{season}.parquet",
                "url": url,
                "sha256": digest,
                "bytes": blob.stat().st_size,
                "blobPath": str(blob.relative_to(root)),
                "fetchedAt": utc_now(),
                **meta,
            })
            print(f"PASS official stats {season} · target-player REG rows {len(kept):,}")

        all_rows.sort(key=lambda r: (r.get("season") or 0, r.get("week") or 0, r.get("game_id") or "", r.get("player_id") or ""))
        manifest = {
            "snapshotSchemaVersion": SCHEMA_VERSION,
            "snapshotId": sid,
            "createdAt": utc_now(),
            "provider": "nflverse",
            "sourceTag": RELEASE_TAG,
            "analysisSeasons": list(seasons),
            "sealedHoldoutSeason": SEALED_HOLDOUT_SEASON,
            "holdoutOpened": False,
            "prospectiveSeason": PROSPECTIVE_SEASON,
            "prospectiveRead": False,
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "frozenOmegaMutation": False,
            "assets": assets,
        }
        (raw_stage / "QB_OFFICIAL_STATS_SOURCE_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        with (norm_stage / "NFL_QB_OFFICIAL_WEEKLY_STATS.jsonl").open("w", encoding="utf-8") as f:
            for row in all_rows:
                f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        audit = {
            "version": VERSION,
            "snapshotId": sid,
            "createdAt": utc_now(),
            "developmentSeasons": list(seasons),
            "holdoutOpened": False,
            "prospectiveRead": False,
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "frozenOmegaMutation": False,
            "targetPlayerIds": len(target_ids),
            "normalizedRows": len(all_rows),
            "seasonAudits": season_audits,
            "authorityRole": "official-like weekly player target/settlement layer; PBP remains mechanism layer",
        }
        (norm_stage / "NFL_QB_OFFICIAL_WEEKLY_STATS_AUDIT.json").write_text(
            json.dumps(audit, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(raw_stage, raw_final)
        os.replace(norm_stage, norm_final)

        raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_QB_OFFICIAL_STATS_SNAPSHOT"
        raw_ptr.parent.mkdir(parents=True, exist_ok=True)
        tmp = raw_ptr.with_name("." + raw_ptr.name + ".tmp")
        tmp.write_text(sid + "\n", encoding="utf-8")
        os.replace(tmp, raw_ptr)
        norm_ptr = root / "data/normalized/nfl/CURRENT_NFL_QB_OFFICIAL_STATS_019"
        tmp2 = norm_ptr.with_name("." + norm_ptr.name + ".tmp")
        tmp2.write_text(str(norm_final.relative_to(root)) + "\n", encoding="utf-8")
        os.replace(tmp2, norm_ptr)
        return norm_final
    except Exception:
        shutil.rmtree(raw_stage, ignore_errors=True)
        shutil.rmtree(norm_stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    print(f"NFL QB official weekly stats adapter {VERSION}")

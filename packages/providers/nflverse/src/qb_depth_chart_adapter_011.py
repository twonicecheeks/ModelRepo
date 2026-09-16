"""NFL QB depth-chart adapter 0.1.1.

Historical 2016-2024 nflverse depth charts use the legacy weekly schema with
`depth_team`; 2025+ uses a date/timestamp schema with `pos_rank`. This module
normalizes both shapes but the development acquisition path is hard-gated to
2016-2024 so the sealed 2025 holdout is never read.
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

VERSION = "0.1.1"
SCHEMA_VERSION = "1.0.0"
SEALED_HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
RELEASE_TAG = "depth_charts"
PARQUET_URL = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_{season}.parquet"
USER_AGENT = "MODEL-NFL/QB-State-0.1.1 depth-chart research adapter"

LEGACY_REQUIRED = (
    "season", "club_code", "week", "game_type", "depth_team", "gsis_id",
    "position", "depth_position", "full_name",
)
MODERN_REQUIRED = (
    "dt", "team", "player_name", "gsis_id", "pos_abb", "pos_rank",
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
        raise ValueError("QB depth 0.1.1 development acquisition forbids sealed 2025 / prospective 2026+: " + ",".join(map(str, bad)))
    return values


def _clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else int(x)


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


def normalize_legacy_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    position = _clean(raw.get("position")).upper()
    depth_position = _clean(raw.get("depth_position")).upper()
    if position != "QB" and depth_position != "QB":
        return None
    source_team = _clean(raw.get("club_code")).upper()
    if not source_team:
        return None
    return {
        "season": _int(raw.get("season")),
        "week": _int(raw.get("week")),
        "game_type": _clean(raw.get("game_type")).upper(),
        "source_team": source_team,
        "team": normalize_team_abbr(source_team),
        "gsis_id": _clean(raw.get("gsis_id")),
        "full_name": _clean(raw.get("full_name")),
        "position": position,
        "depth_position": depth_position,
        "depth_rank": _int(raw.get("depth_team")),
        "as_of": "",
        "source_schema": "LEGACY_WEEKLY_PRE2025",
    }


def normalize_modern_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    pos = _clean(raw.get("pos_abb")).upper()
    if pos != "QB":
        return None
    source_team = _clean(raw.get("team")).upper()
    if not source_team:
        return None
    return {
        "season": None,
        "week": None,
        "game_type": "",
        "source_team": source_team,
        "team": normalize_team_abbr(source_team),
        "gsis_id": _clean(raw.get("gsis_id")),
        "full_name": _clean(raw.get("player_name")),
        "position": pos,
        "depth_position": pos,
        "depth_rank": _int(raw.get("pos_rank")),
        "as_of": _clean(raw.get("dt")),
        "source_schema": "MODERN_TIMESTAMP_2025_PLUS",
    }


def normalize_parquet(path: Path, season: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if pq is None:
        raise RuntimeError(f"pyarrow required: {_PYARROW_IMPORT_ERROR}")
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    if season < SEALED_HOLDOUT_SEASON:
        missing = [c for c in LEGACY_REQUIRED if c not in names]
        if missing:
            raise ValueError(f"{path.name} missing legacy depth columns: {', '.join(missing)}")
        selected = [c for c in LEGACY_REQUIRED if c in names]
        raw_rows = pf.read(columns=selected).to_pylist()
        rows = [x for r in raw_rows if (x := normalize_legacy_row(r)) is not None]
        schema = "LEGACY_WEEKLY_PRE2025"
    else:
        missing = [c for c in MODERN_REQUIRED if c not in names]
        if missing:
            raise ValueError(f"{path.name} missing modern depth columns: {', '.join(missing)}")
        selected = [c for c in MODERN_REQUIRED if c in names]
        raw_rows = pf.read(columns=selected).to_pylist()
        rows = [x for r in raw_rows if (x := normalize_modern_row(r)) is not None]
        schema = "MODERN_TIMESTAMP_2025_PLUS"
    rows.sort(key=lambda r: (r.get("season") or 0, r.get("week") or 0, r["team"], r.get("depth_rank") or 999, r.get("gsis_id") or r.get("full_name") or ""))
    return rows, {
        "schema": schema,
        "rawRows": len(raw_rows),
        "qbRows": len(rows),
        "qbRowsWithGsis": sum(1 for r in rows if r.get("gsis_id")),
        "qb1Rows": sum(1 for r in rows if r.get("depth_rank") == 1),
        "columns": sorted(names),
    }


def acquire_and_normalize(root: Path, seasons: Iterable[int]) -> Path:
    seasons = assert_development_only(seasons)
    root = Path(root).resolve()
    sid = snapshot_id()
    raw_stage = root / "data/raw/nfl/nflverse/qb_depth_snapshots" / ("." + sid + ".staging")
    raw_final = root / "data/raw/nfl/nflverse/qb_depth_snapshots" / sid
    norm_stage = root / "data/normalized/nfl/qb_depth_011" / ("." + sid + ".staging")
    norm_final = root / "data/normalized/nfl/qb_depth_011" / sid
    raw_stage.mkdir(parents=True, exist_ok=False)
    norm_stage.mkdir(parents=True, exist_ok=False)

    assets: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    season_audits: list[dict[str, Any]] = []
    try:
        for season in seasons:
            url = PARQUET_URL.format(season=season)
            print(f"DOWNLOAD depth charts {season}")
            fd, temp_name = tempfile.mkstemp(prefix=f"depth_{season}_", suffix=".parquet", dir=str(raw_stage))
            os.close(fd)
            temp = Path(temp_name)
            meta = _download(url, temp)
            if temp.stat().st_size <= 0:
                raise RuntimeError(f"empty depth-chart asset: {url}")
            digest = sha256_file(temp)
            blob = root / "data/raw/nfl/nflverse/blobs" / digest[:2] / digest
            blob.parent.mkdir(parents=True, exist_ok=True)
            if blob.exists():
                if sha256_file(blob) != digest:
                    raise RuntimeError(f"content-addressed depth blob mismatch: {blob}")
                temp.unlink()
            else:
                os.replace(temp, blob)
            rows, audit = normalize_parquet(blob, season)
            for r in rows:
                r["source_sha256"] = digest
                r["source_url"] = url
            all_rows.extend(rows)
            season_audits.append({"season": season, **audit})
            assets.append({
                "source": "depth_charts", "season": season,
                "filename": f"depth_charts_{season}.parquet", "url": url,
                "sha256": digest, "bytes": blob.stat().st_size,
                "blobPath": str(blob.relative_to(root)), "fetchedAt": utc_now(), **meta,
            })
            print(f"PASS {season} · QB rows {len(rows):,} · QB1 rows {audit['qb1Rows']:,}")

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
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "frozenOmegaMutation": False,
            "assets": assets,
        }
        (raw_stage / "QB_DEPTH_SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        with (norm_stage / "NFL_QB_DEPTH_CHARTS.jsonl").open("w", encoding="utf-8") as f:
            for row in all_rows:
                f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        audit = {
            "version": VERSION,
            "snapshotId": sid,
            "createdAt": utc_now(),
            "developmentSeasons": list(seasons),
            "holdoutOpened": False,
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "frozenOmegaMutation": False,
            "rowCount": len(all_rows),
            "qb1Rows": sum(1 for r in all_rows if r.get("depth_rank") == 1),
            "gsisCoveragePct": (100.0 * sum(1 for r in all_rows if r.get("gsis_id")) / len(all_rows)) if all_rows else None,
            "seasonAudits": season_audits,
            "timingCaveat": "Legacy pre-2025 source is week-level; exact publication timestamp is not present in the legacy schema.",
        }
        (norm_stage / "NFL_QB_DEPTH_CHART_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        os.replace(raw_stage, raw_final)
        os.replace(norm_stage, norm_final)
        raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_QB_DEPTH_SNAPSHOT"
        raw_ptr.parent.mkdir(parents=True, exist_ok=True)
        tmp = raw_ptr.with_name("." + raw_ptr.name + ".tmp")
        tmp.write_text(sid + "\n", encoding="utf-8")
        os.replace(tmp, raw_ptr)
        norm_ptr = root / "data/normalized/nfl/CURRENT_NFL_QB_DEPTH_CHARTS"
        tmp2 = norm_ptr.with_name("." + norm_ptr.name + ".tmp")
        tmp2.write_text(str(norm_final.relative_to(root)) + "\n", encoding="utf-8")
        os.replace(tmp2, norm_ptr)
        return norm_final / "NFL_QB_DEPTH_CHART_AUDIT.json"
    except Exception:
        shutil.rmtree(raw_stage, ignore_errors=True)
        shutil.rmtree(norm_stage, ignore_errors=True)
        raise

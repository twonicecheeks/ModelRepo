"""Immutable nflverse snapshot acquisition for MODEL NFL Phase 1B.

Raw source bytes are stored once in a SHA256 content-addressed blob store. Each run
writes an immutable manifest that points at those blobs, then atomically updates a
CURRENT_RAW_SNAPSHOT pointer. No sportsbook API is called here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import ssl
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Iterable

try:
    from .contract import (
        CONTRACT_VERSION,
        HISTORY_SEED_SEASONS,
        RESEARCH_ANALYSIS_SEASONS,
        source_specs,
    )
except ImportError:  # direct execution/tests
    from contract import CONTRACT_VERSION, HISTORY_SEED_SEASONS, RESEARCH_ANALYSIS_SEASONS, source_specs

SNAPSHOT_SCHEMA_VERSION = "1.0.0"
USER_AGENT = "MODEL-NFL/2.9.0 Phase1B nflverse research snapshot"


@dataclass(frozen=True)
class AssetPlan:
    source: str
    url: str
    filename: str
    season: int | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_snapshot_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_asset_plan(
    analysis_seasons: Iterable[int] = RESEARCH_ANALYSIS_SEASONS,
    history_seed_seasons: Iterable[int] = HISTORY_SEED_SEASONS,
) -> list[AssetPlan]:
    specs = source_specs()
    seasons = sorted({int(x) for x in analysis_seasons} | {int(x) for x in history_seed_seasons})
    if not seasons:
        raise ValueError("snapshot requires at least one season")

    out = [
        AssetPlan("schedules", specs["schedules"].url_for_season(), "games.csv"),
        AssetPlan("players", specs["players"].url_for_season(), "players.parquet"),
    ]
    for season in seasons:
        out.append(AssetPlan(
            "weekly_rosters",
            specs["weekly_rosters"].url_for_season(season),
            f"roster_weekly_{season}.parquet",
            season,
        ))
        out.append(AssetPlan(
            "play_by_play",
            specs["play_by_play"].url_for_season(season),
            f"play_by_play_{season}.parquet",
            season,
        ))
    return out


def _verified_tls_context() -> ssl.SSLContext:
    """Return a certificate-validating TLS context backed by pinned certifi CA data.

    MODEL's isolated NFL research environment can be created from Python builds whose
    OpenSSL trust store is not wired to the macOS Keychain. That produces
    CERTIFICATE_VERIFY_FAILED in urllib even when pip/curl work normally. We therefore
    make the CA bundle an explicit, pinned research dependency rather than weakening
    TLS verification or relying on machine-specific certificate installation.
    """
    try:
        import certifi  # installed only in MODEL's isolated Phase 1B environment
    except ImportError as exc:
        raise RuntimeError(
            "verified TLS CA bundle unavailable; run scripts/nfl/bootstrap_phase1_python.command "
            "to install the pinned certifi dependency"
        ) from exc
    return ssl.create_default_context(cafile=certifi.where())


def _download_http(url: str, target: Path, *, timeout: int = 120, retries: int = 3) -> dict[str, str | None]:
    last: Exception | None = None
    context = _verified_tls_context()
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp, target.open("wb") as out:
                shutil.copyfileobj(resp, out, length=1024 * 1024)
                headers = resp.headers
                return {
                    "etag": headers.get("ETag"),
                    "lastModified": headers.get("Last-Modified"),
                    "contentType": headers.get("Content-Type"),
                    "finalUrl": resp.geturl(),
                }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last = exc
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"download failed after {retries} attempt(s): {url}: {last}")


def _store_blob(root: Path, temp_path: Path, digest: str) -> Path:
    blob = root / "data/raw/nfl/nflverse/blobs" / digest[:2] / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    if blob.exists():
        if sha256_file(blob) != digest:
            raise RuntimeError(f"content-addressed blob hash mismatch: {blob}")
        temp_path.unlink(missing_ok=True)
        return blob
    os.replace(temp_path, blob)
    return blob


def acquire_snapshot(
    root: Path,
    *,
    analysis_seasons: Iterable[int] = RESEARCH_ANALYSIS_SEASONS,
    history_seed_seasons: Iterable[int] = HISTORY_SEED_SEASONS,
    fetcher: Callable[[str, Path], dict[str, str | None]] | None = None,
) -> Path:
    root = Path(root).resolve()
    analysis = sorted({int(x) for x in analysis_seasons})
    seeds = sorted({int(x) for x in history_seed_seasons})
    plan = build_asset_plan(analysis, seeds)
    fetcher = fetcher or (lambda url, path: _download_http(url, path))

    snapshots_root = root / "data/raw/nfl/nflverse/snapshots"
    snapshots_root.mkdir(parents=True, exist_ok=True)
    snapshot_id = make_snapshot_id()
    staging = snapshots_root / ("." + snapshot_id + ".staging")
    final = snapshots_root / snapshot_id
    staging.mkdir(parents=True, exist_ok=False)

    assets: list[dict[str, Any]] = []
    try:
        for i, asset in enumerate(plan, 1):
            print(f"[{i}/{len(plan)}] nflverse {asset.source}" + (f" {asset.season}" if asset.season else ""))
            fd, temp_name = tempfile.mkstemp(prefix="model_nfl_", suffix=".part", dir=str(staging))
            os.close(fd)
            temp_path = Path(temp_name)
            meta = fetcher(asset.url, temp_path) or {}
            size = temp_path.stat().st_size
            if size <= 0:
                raise RuntimeError(f"downloaded empty asset: {asset.url}")
            digest = sha256_file(temp_path)
            blob = _store_blob(root, temp_path, digest)
            assets.append({
                "source": asset.source,
                "season": asset.season,
                "filename": asset.filename,
                "url": asset.url,
                "sha256": digest,
                "bytes": size,
                "blobPath": str(blob.relative_to(root)),
                "fetchedAt": utc_now(),
                "etag": meta.get("etag"),
                "lastModified": meta.get("lastModified"),
                "contentType": meta.get("contentType"),
            })

        manifest = {
            "snapshotSchemaVersion": SNAPSHOT_SCHEMA_VERSION,
            "snapshotId": snapshot_id,
            "createdAt": utc_now(),
            "provider": "nflverse",
            "contractVersion": CONTRACT_VERSION,
            "analysisSeasons": analysis,
            "historySeedSeasons": seeds,
            "trainingWindowFrozen": False,
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "assets": assets,
        }
        (staging / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, final)
        pointer_tmp = root / "data/raw/nfl/nflverse/.CURRENT_RAW_SNAPSHOT.tmp"
        pointer = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer_tmp.write_text(snapshot_id + "\n", encoding="utf-8")
        os.replace(pointer_tmp, pointer)
        return final / "SOURCE_MANIFEST.json"
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def load_manifest(path: Path, root: Path | None = None) -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("snapshotSchemaVersion") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("snapshot manifest schema drift")
    if data.get("contractVersion") != CONTRACT_VERSION:
        raise ValueError("snapshot contract version drift")
    if root is not None:
        root = Path(root).resolve()
        for asset in data.get("assets", []):
            blob = root / asset["blobPath"]
            if not blob.exists():
                raise FileNotFoundError(blob)
            if sha256_file(blob) != asset["sha256"]:
                raise ValueError(f"snapshot blob hash mismatch: {asset['filename']}")
    return data


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--analysis-seasons", default="2016-2025")
    args = ap.parse_args()
    a, b = (int(x) for x in args.analysis_seasons.split("-", 1))
    manifest = acquire_snapshot(args.root, analysis_seasons=range(a, b + 1), history_seed_seasons=(a - 1,))
    print(manifest)

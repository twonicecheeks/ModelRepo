"""NFL QB Model 0.2.4 — immutable 2026 prospective-history source acquisition.

Acquires only public nflverse source assets needed to construct lagged 2026 QB
passing-yards features: the schedule, current-season play-by-play and weekly player
statistics. Source bytes are stored content-addressed with an immutable manifest.
This adapter does not parse target/current-week outcomes, fit a model, or access any
sportsbook/market source.
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
from typing import Any

try:
    from .contract import source_specs
    from .qb_official_stats_adapter_019 import PARQUET_URL as PLAYER_STATS_URL
except ImportError:
    from contract import source_specs
    from qb_official_stats_adapter_019 import PARQUET_URL as PLAYER_STATS_URL

VERSION = "0.2.4"
SCHEMA_VERSION = "1.0.0"
PROSPECTIVE_SEASON = 2026
USER_AGENT = "MODEL-NFL/QB-0.2.4 prospective-history"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]


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


def _store_blob(root: Path, temp: Path, digest: str) -> Path:
    blob = root / "data/raw/nfl/nflverse/blobs" / digest[:2] / digest
    blob.parent.mkdir(parents=True, exist_ok=True)
    if blob.exists():
        if sha256_file(blob) != digest:
            raise RuntimeError(f"content-addressed blob mismatch: {blob}")
        temp.unlink(missing_ok=True)
        return blob
    os.replace(temp, blob)
    return blob


def acquire(root: Path, *, target_week: int) -> Path:
    """Acquire immutable 2026 sources for one target-week as-of score.

    Full source files are archived for reproducibility. The scorer must predicate-
    filter PBP/player stats to REG rows with week < target_week before constructing
    features. The schedule is used only to prove that the prior-week team-game
    universe is complete; schedule outcomes/market columns are never features.
    """
    root = Path(root).expanduser().resolve()
    tw = int(target_week)
    if not (1 <= tw <= 30):
        raise ValueError("target_week out of range")
    specs = source_specs()
    plans = [
        ("schedules", specs["schedules"].url_for_season(), "games.csv"),
        ("play_by_play", specs["play_by_play"].url_for_season(PROSPECTIVE_SEASON), f"play_by_play_{PROSPECTIVE_SEASON}.parquet"),
        ("player_stats_weekly", PLAYER_STATS_URL.format(season=PROSPECTIVE_SEASON), f"stats_player_week_{PROSPECTIVE_SEASON}.parquet"),
    ]
    run_id = make_run_id()
    raw_root = root / "data/raw/nfl/nflverse/qb_prospective_024"
    stage = raw_root / ("." + run_id + ".staging")
    final = raw_root / run_id
    stage.mkdir(parents=True, exist_ok=False)
    assets: list[dict[str, Any]] = []
    try:
        for source, url, filename in plans:
            print(f"DOWNLOAD nflverse {source}" + (f" {PROSPECTIVE_SEASON}" if source != "schedules" else "") + " — as-of source archive")
            suffix = ".csv" if source == "schedules" else ".parquet"
            fd, tmpname = tempfile.mkstemp(prefix="qb024_", suffix=suffix, dir=str(stage))
            os.close(fd)
            temp = Path(tmpname)
            meta = _download(url, temp)
            if temp.stat().st_size <= 0:
                raise RuntimeError(f"empty prospective source asset: {url}")
            digest = sha256_file(temp)
            blob = _store_blob(root, temp, digest)
            assets.append({
                "source": source,
                "season": None if source == "schedules" else PROSPECTIVE_SEASON,
                "filename": filename,
                "url": url,
                "sha256": digest,
                "bytes": blob.stat().st_size,
                "blobPath": str(blob.relative_to(root)),
                "fetchedAt": utc_now(),
                **meta,
            })
        manifest = {
            "snapshotSchemaVersion": SCHEMA_VERSION,
            "version": VERSION,
            "runId": run_id,
            "createdAt": utc_now(),
            "provider": "nflverse",
            "prospectiveSeason": PROSPECTIVE_SEASON,
            "targetWeek": tw,
            "featureAdmissionRule": f"REG only; season={PROSPECTIVE_SEASON}; week < {tw}",
            "scheduleRole": "identity/completeness audit only; schedule outcomes and market columns forbidden",
            "targetOrLaterOutcomeAdmissionAllowed": False,
            "coefficientFitAllowed": False,
            "marketDependency": False,
            "oddsPapiRequests": 0,
            "frozenOmegaMutation": False,
            "assets": assets,
        }
        (stage / "QB_PROSPECTIVE_024_SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(stage, final)
        return final / "QB_PROSPECTIVE_024_SOURCE_MANIFEST.json"
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def asset_by_source(manifest: dict[str, Any], source: str) -> dict[str, Any]:
    matches = [a for a in manifest.get("assets", []) if str(a.get("source")) == str(source)]
    if len(matches) != 1:
        raise ValueError(f"prospective source asset count for {source}: {len(matches)}")
    return matches[0]


if __name__ == "__main__":
    print(f"NFL QB prospective history adapter {VERSION}")

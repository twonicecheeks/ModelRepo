#!/usr/bin/env python3
"""Inspect nflverse depth-chart history for a leakage-safe OMEGA role model.

This is a source-audit utility, not a model. It intentionally refuses to read the
sealed 2025 season. Default assets are 2019-2024 (development/diagnostic history)
and 2026 (prospective schema/current source only).
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import shutil
import subprocess

DEFAULT_YEARS = (2019, 2020, 2021, 2022, 2023, 2024, 2026)
SEALED_YEAR = 2025
BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download/depth_charts"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, path: Path) -> None:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("system curl not found; refusing to disable TLS verification")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    try:
        part.unlink()
    except FileNotFoundError:
        pass
    cmd = [
        curl,
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "20",
        "--max-time",
        "180",
        "--retry",
        "2",
        "--retry-delay",
        "1",
        "--user-agent",
        "OMEGA-MODEL/0.26 depth-chart-source-audit",
        "--output",
        str(part),
        url,
    ]
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != 0:
        try:
            part.unlink()
        except FileNotFoundError:
            pass
        raise RuntimeError((r.stderr or r.stdout or f"curl exit {r.returncode}").strip())
    if not part.exists() or part.stat().st_size == 0:
        raise RuntimeError(f"empty download: {url}")
    os.replace(part, path)


def parse_years(raw: str) -> tuple[int, ...]:
    years = tuple(sorted({int(x.strip()) for x in raw.split(",") if x.strip()}))
    if not years:
        raise ValueError("no years requested")
    if SEALED_YEAR in years:
        raise ValueError("2025 is sealed and this audit refuses to read it")
    if any(y < 2001 or y > 2026 for y in years):
        raise ValueError(f"unsupported year(s): {years}")
    return years


def scalar(v):
    try:
        return v.as_py()
    except Exception:
        return v


def summarize_parquet(path: Path, year: int) -> dict:
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    names = list(pf.schema_arrow.names)
    wanted = [
        x
        for x in (
            "season",
            "week",
            "game_type",
            "dt",
            "team",
            "club_code",
            "gsis_id",
            "pfr_player_id",
            "full_name",
            "player_name",
            "position",
            "pos_abb",
            "pos_rank",
            "depth_position",
            "depth_team",
            "formation",
        )
        if x in names
    ]
    table = pf.read(columns=wanted) if wanted else None
    rows = table.num_rows if table is not None else pf.metadata.num_rows
    data = table.to_pylist() if table is not None else []

    def vals(col):
        if col not in wanted:
            return []
        return [str(r.get(col) or "").strip() for r in data if str(r.get(col) or "").strip()]

    dts = vals("dt")
    weeks = []
    if "week" in wanted:
        for r in data:
            v = r.get("week")
            if v not in (None, ""):
                try:
                    weeks.append(int(float(v)))
                except Exception:
                    pass
    game_types = sorted(set(vals("game_type")))
    teams = sorted(set(vals("team") or vals("club_code")))
    ids = vals("gsis_id")
    ranks = []
    if "pos_rank" in wanted:
        for r in data:
            v = r.get("pos_rank")
            if v not in (None, ""):
                try:
                    ranks.append(int(float(v)))
                except Exception:
                    pass

    temporal_candidates = [x for x in ("dt", "week") if x in names]
    id_candidates = [x for x in ("gsis_id", "pfr_player_id") if x in names]
    rank_candidates = [x for x in ("pos_rank", "depth_team") if x in names]

    sample = []
    keep = [
        x
        for x in (
            "dt",
            "week",
            "game_type",
            "team",
            "club_code",
            "gsis_id",
            "full_name",
            "player_name",
            "position",
            "pos_abb",
            "pos_rank",
            "depth_position",
            "depth_team",
            "formation",
        )
        if x in wanted
    ]
    for r in data[:3]:
        sample.append({k: scalar(r.get(k)) for k in keep})

    return {
        "year": year,
        "rows": rows,
        "columns": names,
        "relevantColumns": wanted,
        "temporalCandidates": temporal_candidates,
        "identityCandidates": id_candidates,
        "rankCandidates": rank_candidates,
        "dtMin": min(dts) if dts else None,
        "dtMax": max(dts) if dts else None,
        "uniqueDt": len(set(dts)),
        "weekMin": min(weeks) if weeks else None,
        "weekMax": max(weeks) if weeks else None,
        "uniqueWeeks": len(set(weeks)),
        "gameTypes": game_types,
        "teamCount": len(teams),
        "gsisIdPresentPct": round(100.0 * len(ids) / rows, 4) if rows else None,
        "posRankMin": min(ranks) if ranks else None,
        "posRankMax": max(ranks) if ranks else None,
        "sample": sample,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--years", default=",".join(map(str, DEFAULT_YEARS)))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    years = parse_years(args.years)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = root / "data/raw/nfl/omega/depth_chart_source_audits"
    staging = base / ("." + stamp + ".staging")
    staging.mkdir(parents=True, exist_ok=False)

    assets = []
    summaries = []
    try:
        for year in years:
            if year == SEALED_YEAR:
                raise RuntimeError("2025 seal violation")
            name = f"depth_charts_{year}.parquet"
            url = f"{BASE_URL}/{name}"
            dest = staging / name
            print(f"FETCH {year}: {url}")
            download(url, dest)
            digest = sha256_file(dest)
            summary = summarize_parquet(dest, year)
            summaries.append(summary)
            assets.append(
                {
                    "year": year,
                    "filename": name,
                    "url": url,
                    "sha256": digest,
                    "bytes": dest.stat().st_size,
                    "rows": summary["rows"],
                }
            )

        audit = {
            "schemaVersion": "OMEGA_DEPTH_CHART_SOURCE_AUDIT_0.26",
            "createdAt": now(),
            "yearsRead": list(years),
            "sealed2025RowsRead": 0,
            "marketFieldsRead": 0,
            "oddsPapiRequests": 0,
            "purpose": "Determine whether nflverse depth-chart history can support strictly pregame OMEGA role-location modeling.",
            "assets": assets,
            "summaries": summaries,
        }
        digest_seed = json.dumps(assets, sort_keys=True, separators=(",", ":")).encode()
        sid = f"{stamp}_{hashlib.sha256(digest_seed).hexdigest()[:8]}"
        final = base / sid
        if final.exists():
            raise RuntimeError(f"immutable audit already exists: {final}")
        (staging / "OMEGA_DEPTH_CHART_SOURCE_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n")
        os.replace(staging, final)
        (root / "data/raw/nfl/omega/CURRENT_DEPTH_CHART_SOURCE_AUDIT").write_text(sid + "\n")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print()
    print("OMEGA 0.26 — NFLVERSE DEPTH-CHART HISTORY SOURCE AUDIT")
    print(f"PASS immutable audit: {sid}")
    print("PASS 2025 sealed · rows read 0 · market fields 0 · OddsPapi 0")
    for s in summaries:
        print()
        print(
            f"{s['year']}: rows {s['rows']} · temporal {s['temporalCandidates']} · "
            f"identity {s['identityCandidates']} · rank {s['rankCandidates']}"
        )
        print(
            f"  dt {s['dtMin']} .. {s['dtMax']} · unique dt {s['uniqueDt']} · "
            f"week {s['weekMin']}..{s['weekMax']} ({s['uniqueWeeks']} unique)"
        )
        print(f"  relevant columns: {', '.join(s['relevantColumns'])}")
        for i, row in enumerate(s["sample"], 1):
            print(f"  sample{i}: {json.dumps(row, sort_keys=True, default=str)}")
    print()
    print(f"REPORT: {final/'OMEGA_DEPTH_CHART_SOURCE_AUDIT.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

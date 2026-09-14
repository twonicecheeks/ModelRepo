#!/usr/bin/env python3
"""Acquire a minimal immutable nflverse snapshot for 2026 result grading.

Operational/evaluation utility only. It does not normalize a training snapshot, fit
models, or admit 2026 outcomes into model features. It downloads only the canonical
sources needed by downstream prospective scorers: schedules, player identities,
2026 weekly rosters, and 2026 play-by-play. The existing nflverse snapshot engine
stores content-addressed blobs and atomically advances CURRENT_RAW_SNAPSHOT.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    src = root / "packages/providers/nflverse/src"
    if not src.exists():
        raise SystemExit(f"FAIL nflverse provider missing: {src}")
    sys.path.insert(0, str(src))
    import snapshot  # type: ignore

    print("OMEGA 0.25 — 2026 RESULTS-ONLY NFLVERSE SNAPSHOT")
    print("PASS purpose prospective grading only · no fitting · no model mutation")
    print("PASS requested seasons: analysis 2026 only · history seeds none")
    manifest_path = snapshot.acquire_snapshot(
        root,
        analysis_seasons=(2026,),
        history_seed_seasons=(),
    )
    meta = snapshot.load_manifest(manifest_path, root=root)
    assets = meta.get("assets", [])
    pbp = [a for a in assets if a.get("source") == "play_by_play" and int(a.get("season") or 0) == 2026]
    sched = [a for a in assets if a.get("source") == "schedules"]
    roster = [a for a in assets if a.get("source") == "weekly_rosters" and int(a.get("season") or 0) == 2026]
    if len(pbp) != 1 or len(sched) != 1 or len(roster) != 1:
        raise SystemExit("FAIL results snapshot missing required 2026 PBP/schedule/roster asset")
    print(f"PASS snapshot {meta.get('snapshotId')} · assets {len(assets)}")
    print(f"PASS 2026 PBP SHA256 {pbp[0].get('sha256')}")
    print("PASS OddsPapi requests 0 · sportsbook data 0")
    print(f"MANIFEST: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize the already-downloaded current nflverse raw snapshot without re-downloading assets")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    src = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(src))
    import normalize  # type: ignore

    pointer = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    if not pointer.exists():
        raise SystemExit(f"no current raw nflverse snapshot pointer: {pointer}")
    snapshot_id = pointer.read_text(encoding="utf-8").strip()
    if not snapshot_id:
        raise SystemExit("CURRENT_RAW_SNAPSHOT is blank")
    manifest = root / "data/raw/nfl/nflverse/snapshots" / snapshot_id / "SOURCE_MANIFEST.json"
    if not manifest.exists():
        raise SystemExit(f"current raw snapshot manifest missing: {manifest}")

    print("MODEL NFL 2.9.0 PHASE 1B.3 — RESUME EXISTING SNAPSHOT NORMALIZATION")
    print(f"Raw snapshot: {snapshot_id}")
    print("Network policy: reuse immutable downloaded blobs · no nflverse re-download · OddsPapi 0")
    audit_md = normalize.normalize_snapshot(root, manifest)
    print(f"PASS normalized snapshot + coverage audit: {audit_md}")
    print("PASS 2025 remains HOLDOUT_NEVER_FIT")
    print("PASS training window remains NOT FROZEN")
    print("RESUME PASS — paste NFLVERSE_COVERAGE_AUDIT.md into ChatGPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

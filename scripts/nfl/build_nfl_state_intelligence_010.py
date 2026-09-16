#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Build immutable NFL State Intelligence 0.1.0 snapshot from current nflverse raw snapshot")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--manifest", default=None, help="optional explicit SOURCE_MANIFEST.json")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    provider = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(provider))
    import state_intelligence_normalize as normalize  # type: ignore

    if args.manifest:
        manifest = Path(args.manifest).expanduser().resolve()
    else:
        pointer = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
        if not pointer.exists():
            raise SystemExit("No CURRENT_RAW_SNAPSHOT; run scripts/nfl/build_phase1_snapshot.command first")
        snapshot_id = pointer.read_text(encoding="utf-8").strip()
        manifest = root / "data/raw/nfl/nflverse/snapshots" / snapshot_id / "SOURCE_MANIFEST.json"

    print("NFL STATE INTELLIGENCE 0.1.0 — IMMUTABLE SNAPSHOT BUILD")
    print(f"Source manifest: {manifest}")
    print("Policy: coefficient-free · market dependency NO · OddsPapi 0 · frozen OMEGA mutation NO")
    audit = normalize.normalize_state_snapshot(root, manifest)
    print(f"PASS state snapshot: {audit.parent}")
    print(f"PASS audit: {audit}")
    print("PASS no training/refit performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

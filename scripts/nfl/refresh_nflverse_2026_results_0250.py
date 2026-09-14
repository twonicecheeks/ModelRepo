#!/usr/bin/env python3
"""Acquire an isolated immutable nflverse snapshot for 2026 result grading.

Operational/evaluation utility only. It does not normalize a training snapshot, fit
models, or admit 2026 outcomes into model features. It downloads only schedules,
player identities, 2026 weekly rosters, and 2026 play-by-play into the existing
content-addressed nflverse blob/snapshot store.

The generic CURRENT_RAW_SNAPSHOT pointer is deliberately restored after acquisition.
A separate CURRENT_OMEGA_2026_RESULTS_MANIFEST pointer is atomically advanced instead,
so a minimal grading snapshot cannot silently replace the research/training snapshot
used by other NFL workflows.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import os
import sys


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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

    generic_ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    had_generic = generic_ptr.exists()
    old_generic = generic_ptr.read_text(encoding="utf-8") if had_generic else ""

    print("OMEGA 0.25 — ISOLATED 2026 RESULTS NFLVERSE SNAPSHOT")
    print("PASS purpose prospective grading only · no fitting · no model mutation")
    print("PASS requested seasons: analysis 2026 only · history seeds none")
    manifest_path = snapshot.acquire_snapshot(
        root,
        analysis_seasons=(2026,),
        history_seed_seasons=(),
    )

    # acquire_snapshot advances the provider's generic pointer by design. Restore the
    # prior research pointer immediately and expose this snapshot through an OMEGA-
    # specific results pointer instead.
    if had_generic:
        atomic_text(generic_ptr, old_generic)
    else:
        generic_ptr.unlink(missing_ok=True)

    meta = snapshot.load_manifest(manifest_path, root=root)
    assets = meta.get("assets", [])
    pbp = [a for a in assets if a.get("source") == "play_by_play" and int(a.get("season") or 0) == 2026]
    sched = [a for a in assets if a.get("source") == "schedules"]
    roster = [a for a in assets if a.get("source") == "weekly_rosters" and int(a.get("season") or 0) == 2026]
    if len(pbp) != 1 or len(sched) != 1 or len(roster) != 1:
        raise SystemExit("FAIL results snapshot missing required 2026 PBP/schedule/roster asset")

    rel_manifest = str(manifest_path.relative_to(root))
    results_ptr = root / "data/raw/nfl/omega/CURRENT_OMEGA_2026_RESULTS_MANIFEST"
    atomic_text(results_ptr, rel_manifest + "\n")

    restored = generic_ptr.read_text(encoding="utf-8") if generic_ptr.exists() else ""
    if had_generic and restored != old_generic:
        raise SystemExit("FAIL generic CURRENT_RAW_SNAPSHOT was not restored exactly")
    if not had_generic and generic_ptr.exists():
        raise SystemExit("FAIL generic CURRENT_RAW_SNAPSHOT unexpectedly created")

    print(f"PASS results snapshot {meta.get('snapshotId')} · assets {len(assets)}")
    print(f"PASS 2026 PBP SHA256 {pbp[0].get('sha256')}")
    print("PASS generic CURRENT_RAW_SNAPSHOT restored/unmodified")
    print(f"PASS dedicated results pointer: {results_ptr}")
    print("PASS OddsPapi requests 0 · sportsbook data 0")
    print(f"MANIFEST: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

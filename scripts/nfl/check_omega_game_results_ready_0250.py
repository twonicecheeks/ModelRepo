#!/usr/bin/env python3
"""Read-only readiness gate for prospective OMEGA postgame grading."""
from __future__ import annotations

from pathlib import Path
import argparse
import importlib.util

NOT_READY = 75


def load_score_lib(root: Path):
    path = root / "scripts/nfl/score_omega_prospective_eval_0230.py"
    spec = importlib.util.spec_from_file_location("omega_score023_ready", path)
    if spec is None or spec.loader is None:
        raise SystemExit("FAIL cannot load OMEGA 0.23 scorer")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--game-id", required=True)
    ap.add_argument("--source-manifest", default="")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    gid = args.game_id.strip()
    lib = load_score_lib(root)
    try:
        _manifest, meta, pbp_asset, pbp_path, sched_path = lib.locate_source(root, args.source_manifest)
    except SystemExit as exc:
        print(f"NOT_READY source: {exc}")
        return NOT_READY

    if gid not in lib.completed_games_from_schedule(sched_path, {gid}):
        print(f"NOT_READY {gid}: schedules asset does not mark game complete")
        return NOT_READY

    import pyarrow.parquet as pq
    pf = pq.ParquetFile(pbp_path)
    names = set(pf.schema_arrow.names)
    if "game_id" not in names:
        raise SystemExit("FAIL 2026 PBP missing game_id")
    cols = ["game_id"] + (["qtr"] if "qtr" in names else [])
    table = pq.read_table(pbp_path, columns=cols, filters=[("game_id", "=", gid)])
    n = table.num_rows
    if n < 80:
        print(f"NOT_READY {gid}: only {n} PBP rows present")
        return NOT_READY
    if "qtr" in table.column_names:
        qs = [int(x) for x in table.column("qtr").to_pylist() if x is not None]
        if not qs or max(qs) < 4:
            print(f"NOT_READY {gid}: PBP does not reach Q4")
            return NOT_READY
        qmax = max(qs)
    else:
        qmax = "NA"

    print("OMEGA 0.25 — POSTGAME RESULTS READINESS")
    print(f"READY {gid} · PBP rows {n} · max qtr {qmax}")
    print(f"PASS nflverse snapshot {meta.get('snapshotId')} · PBP SHA256 {pbp_asset.get('sha256')}")
    print("PASS readiness only · model writes 0 · refits 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

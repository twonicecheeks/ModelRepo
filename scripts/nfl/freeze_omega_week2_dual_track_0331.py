#!/usr/bin/env python3
"""OMEGA 0.33.1 I/O compatibility shim.

The OMEGA 0.33 freeze logic is intentionally unchanged. nflverse raw assets live in
a SHA256 content-addressed blob store whose paths have no filename extension. The
0.33 freeze's schedule reader keyed only off Path.suffix, so it rejected a valid
`games.csv` blob before any forecast was built.

This shim replaces only that generic asset reader with a content-sniffing reader,
then delegates to the exact 0.33 main(). No model coefficients, features, gates,
probabilities, prior-state rules, row-universe rules, or frozen artifacts change.
"""
from __future__ import annotations

from pathlib import Path
import csv
import importlib.util


def load_base(root: Path):
    path=root/"scripts/nfl/freeze_omega_week2_dual_track_0330.py"
    spec=importlib.util.spec_from_file_location("omega0330_base",path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FAIL cannot load OMEGA 0.33 base: {path}")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_asset_rows(path: Path):
    """Read extensionless content-addressed CSV/Parquet blobs by content."""
    suffix=path.suffix.lower()
    if suffix==".csv":
        with path.open(newline="",encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    if suffix==".parquet":
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    with path.open("rb") as f:
        magic=f.read(4)
    if magic==b"PAR1":
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    try:
        with path.open(newline="",encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except (UnicodeDecodeError,csv.Error) as exc:
        raise SystemExit(f"FAIL unsupported content-addressed asset format: {path} ({exc})") from exc


def main() -> int:
    import argparse
    ap=argparse.ArgumentParser(add_help=False)
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    known,_=ap.parse_known_args()
    root=Path(known.root).expanduser().resolve()
    mod=load_base(root)
    mod.read_asset_rows=read_asset_rows
    return int(mod.main())


if __name__=="__main__":
    raise SystemExit(main())

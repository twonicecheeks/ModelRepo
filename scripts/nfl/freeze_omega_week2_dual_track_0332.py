#!/usr/bin/env python3
"""OMEGA 0.33.2 compatibility shim for Week 2 dual-track freeze.

Repairs a Python local-name collision in the 0.33 base script: a local variable named
`os` (offense family share) shadowed the imported stdlib `os` module, so packaging
failed at `os.replace(staging, final)` after all model calculations had completed.

This shim performs one exact source-level identifier rename in memory before loading
0.33, then applies the already-audited 0.33.1 extensionless-blob reader. No model
coefficients, features, gates, probabilities, prior-state admission rules, trust tags,
or output schemas are changed.
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType
import argparse
import csv


OLD = '''            os = wk1.famshare(off_fam[offense], tuple(fs.FAMILIES), fs.TEAM_WINDOW_GAMES)\n            ds = wk1.famshare(def_fam[defense], tuple(fs.FAMILIES), fs.TEAM_WINDOW_GAMES)\n            raw = {f:max(0.0,0.5*((os[f] if os else league_share[f])+(ds[f] if ds else league_share[f]))) for f in fs.FAMILIES}\n'''
NEW = '''            off_share = wk1.famshare(off_fam[offense], tuple(fs.FAMILIES), fs.TEAM_WINDOW_GAMES)\n            def_share = wk1.famshare(def_fam[defense], tuple(fs.FAMILIES), fs.TEAM_WINDOW_GAMES)\n            raw = {f:max(0.0,0.5*((off_share[f] if off_share else league_share[f])+(def_share[f] if def_share else league_share[f]))) for f in fs.FAMILIES}\n'''


def read_asset_rows(path: Path):
    """Read extensionless content-addressed CSV/Parquet blobs by content."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    if suffix == ".parquet":
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    with path.open("rb") as f:
        magic = f.read(4)
    if magic == b"PAR1":
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise SystemExit(f"FAIL unsupported content-addressed asset format: {path} ({exc})") from exc


def load_patched_base(root: Path):
    path = root / "scripts/nfl/freeze_omega_week2_dual_track_0330.py"
    source = path.read_text(encoding="utf-8")
    n = source.count(OLD)
    if n != 1:
        raise SystemExit(f"FAIL OMEGA 0.33.2 expected exactly one os-shadow block; found {n}")
    patched = source.replace(OLD, NEW, 1)
    if "            os = wk1.famshare(" in patched:
        raise SystemExit("FAIL OMEGA 0.33.2 os-shadow binding remains after patch")
    code = compile(patched, str(path) + "::<0.33.2-os-shadow-fix>", "exec")
    mod = ModuleType("omega0330_base_patched_0332")
    mod.__file__ = str(path)
    mod.__package__ = None
    exec(code, mod.__dict__)
    mod.read_asset_rows = read_asset_rows
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    known, _ = ap.parse_known_args()
    root = Path(known.root).expanduser().resolve()
    mod = load_patched_base(root)
    print("OMEGA 0.33.2 — COMPATIBILITY SHIM")
    print("PASS exact local os-shadow rename applied in memory · model logic unchanged")
    print("PASS extensionless nflverse asset reader retained from 0.33.1")
    return int(mod.main())


if __name__ == "__main__":
    raise SystemExit(main())

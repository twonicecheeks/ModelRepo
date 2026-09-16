#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse
import sys


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build immutable nflverse historical QB depth-chart supplement")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    src = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(src))
    import qb_depth_chart_adapter_011 as adapter
    seasons = adapter.assert_development_only(parse_seasons(args.seasons))
    print("NFL QB STATE 0.1.1 — IMMUTABLE DEPTH-CHART SUPPLEMENT")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    audit = adapter.acquire_and_normalize(root, seasons)
    print(f"PASS normalized QB depth snapshot: {audit.parent}")
    print(f"PASS audit: {audit}")
    print("PASS no model fit performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

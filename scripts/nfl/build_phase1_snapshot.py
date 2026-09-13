#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys


def parse_range(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Acquire and normalize an immutable nflverse Phase 1B research snapshot")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--analysis-seasons", default="2016-2025", help="research coverage window; this does NOT freeze the training window")
    ap.add_argument("--seed-seasons", default=None, help="comma/range override; default = one season before first analysis season")
    ap.add_argument("--plan", action="store_true", help="print source asset plan without downloading")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    src = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(src))
    import snapshot  # type: ignore
    import normalize  # type: ignore

    analysis = parse_range(args.analysis_seasons)
    seeds = parse_range(args.seed_seasons) if args.seed_seasons else [min(analysis) - 1]
    if 2025 not in analysis:
        raise SystemExit("Phase 1B research audit must include untouched 2025 holdout")
    if 2026 in analysis:
        raise SystemExit("2026 is prospective-only and is intentionally excluded from the Phase 1B historical snapshot")

    plan = snapshot.build_asset_plan(analysis, seeds)
    if args.plan:
        print(json.dumps({
            "analysisSeasons": analysis,
            "historySeedSeasons": seeds,
            "trainingWindowFrozen": False,
            "assets": [a.__dict__ for a in plan],
            "oddsPapiRequests": 0,
        }, indent=2))
        return 0

    print("MODEL NFL 2.9.0 PHASE 1B — NFLVERSE SNAPSHOT BUILD")
    print(f"Analysis seasons: {analysis[0]}-{analysis[-1]} (research coverage only; training window NOT frozen)")
    print(f"History seed: {','.join(map(str, seeds))}")
    print("Market/API policy: nflverse source download only · OddsPapi 0")
    manifest = snapshot.acquire_snapshot(root, analysis_seasons=analysis, history_seed_seasons=seeds)
    print(f"PASS immutable source manifest: {manifest}")
    audit_md = normalize.normalize_snapshot(root, manifest)
    print(f"PASS normalized snapshot + coverage audit: {audit_md}")
    print("PASS 2025 remains HOLDOUT_NEVER_FIT")
    print("PASS training window remains NOT FROZEN")
    print("BUILD PASS — paste NFLVERSE_COVERAGE_AUDIT.md into ChatGPT for review before model fitting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

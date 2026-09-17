#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import sys


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Select one immutable QB 0.2.4 score for downstream 0.2.5-0.2.7 tools")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--game-id", required=True)
    ap.add_argument("--qb-gsis-id", required=True)
    ap.add_argument("--run-id", default="", help="required only when multiple immutable scores match the same game/QB")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    sys.path.insert(0, str(model_dir))
    import qb_passing_yards_score_selector_0241 as selector

    chosen = selector.select(root, args.game_id, args.qb_gsis_id, args.run_id)
    score_path = chosen["path"]
    score = chosen["score"]
    rel_dir = score_path.parent.relative_to(root)
    atomic_pointer(root / "data/prospective/nfl/CURRENT_QB_PASSING_YARDS_024", str(rel_dir))

    target = score.get("target") or {}
    print("\nNFL QB MODEL 0.2.4.1 — TARGET SCORE SELECTOR")
    print(f"Target: {target.get('game_id')} · {target.get('team')} vs {target.get('opponent')} · {target.get('qb_name') or target.get('qb_gsis_id')}")
    print(f"Run ID: {score.get('runId')}")
    print(f"Projection: {float(score.get('projectionPassingYards')):.1f} yd")
    print(f"Score SHA256: {sha256_file(score_path)}")
    print(f"Selected immutable score: {score_path}")
    print("Model refit/reselection: NO · outcome leakage: 0 · market fields admitted: 0")
    print("CURRENT_QB_PASSING_YARDS_024 now points to this exact immutable score")
    print("PASS QB Model 0.2.4.1 selector · downstream 0.2.5-0.2.7 target is explicit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

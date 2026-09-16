#!/usr/bin/env python3
"""OMEGA 0.33 hardened Week 2 pregame capture.

Runs the existing OMEGA 0.16 prospective source capture but replaces only the 2025+
ESPN depth-map selection rule. The old capture chose the latest row independently per
player, which can retain a stale player who is absent from the team's newest depth
snapshot. For OMEGA 0.33 we require an exact latest TEAM snapshot as of capture time.

Roster, injury, schedule, research-ready and fail-closed VERIFIED semantics are
otherwise unchanged. This is source hardening, not a model change.
"""
from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
from typing import Any


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("omega016_capture_for_033", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FAIL cannot load base pregame capture: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    root = Path("/Users/abbeyfelix/Developer/MODEL")
    for i, arg in enumerate(sys.argv[:-1]):
        if arg == "--root":
            root = Path(sys.argv[i + 1]).expanduser().resolve()
            break
    mod = load_module(root / "scripts/nfl/capture_omega_tackle_016_2026_pregame.py")
    original_latest_by = mod.latest_by

    def exact_team_snapshot_latest_by(rows: list[dict[str, Any]], key, tskey: str):
        if tskey != "dt":
            return original_latest_by(rows, key, tskey)
        # Base capture has already removed future depth rows before this function is
        # called. Select one exact latest timestamp per team, then build player keys
        # only from that snapshot. Missing players therefore remain missing rather
        # than leaking forward from an older team snapshot.
        latest_team_dt: dict[str, str] = {}
        keyed: list[tuple[dict[str, Any], Any]] = []
        for r in rows:
            k = key(r)
            if not k or not isinstance(k, tuple) or len(k) < 2:
                continue
            team = str(k[0] or "").strip()
            pid = str(k[1] or "").strip()
            dt = str(r.get(tskey) or "").strip()
            if not team or not pid or not dt:
                continue
            keyed.append((r, k))
            if team not in latest_team_dt or dt > latest_team_dt[team]:
                latest_team_dt[team] = dt
        filtered = []
        for r, k in keyed:
            team = str(k[0] or "").strip()
            if str(r.get(tskey) or "").strip() == latest_team_dt.get(team):
                filtered.append(r)
        out = original_latest_by(filtered, key, tskey)
        if rows and not out:
            raise RuntimeError("OMEGA 0.33 exact-team depth snapshot selection emitted zero rows")
        return out

    mod.latest_by = exact_team_snapshot_latest_by
    print("OMEGA 0.33 — hardened pregame capture: current depth uses latest exact TEAM snapshot; stale per-player carry-forward disabled")
    return int(mod.main())


if __name__ == "__main__":
    raise SystemExit(main())

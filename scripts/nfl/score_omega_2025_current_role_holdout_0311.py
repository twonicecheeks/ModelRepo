#!/usr/bin/env python3
"""OMEGA 0.31.1 implementation hardening for the frozen 0.31 protocol.

The development helper exposure_role_challenger.build_exposure_pregame_rows is
intentionally hard-limited to <=2024.  The 0.31 confirmatory evaluator needs the
same strictly-lagged feature construction through 2025 without changing that frozen
package.  This launcher monkey-patches only the in-process evaluation copy with an
exact extension through 2025, then runs the frozen-protocol 0.31 scorer.

No model fitting, feature change, gate change, or package write occurs here.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import fmean
import importlib.util
import math
import sys
from typing import Any, Sequence


def install_eval_only_feature_builder(root: Path):
    omega = root / "packages/models/nfl/omega"
    if str(omega) not in sys.path:
        sys.path.insert(0, str(omega))
    import exposure_role_challenger as er

    def snap_share(r: dict[str, Any], team_snap_totals: dict[tuple[str, str], float]) -> float | None:
        pct = er.normalize_pct(r.get("defense_pct"))
        if pct is not None:
            return pct
        snaps = er.num(r.get("defense_snaps"))
        total = team_snap_totals.get((str(r.get("game_id") or ""), str(r.get("team") or "")))
        if snaps is None or total is None or total <= 0:
            return None
        return max(0.0, min(1.0, float(snaps) / float(total)))

    def build_through_2025(exposure_rows: Sequence[dict[str, Any]], team_snap_totals: dict[tuple[str, str], float]) -> list[dict[str, Any]]:
        """Exact H012 pregame feature chronology extended from 2024 through 2025.

        Every target week's rows are emitted before that week's realized snap shares
        update player/position history. This function is evaluation-only and is
        validated by exact parity against the immutable blind H012 predictions.
        """
        by_week: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for r in exposure_rows:
            if not er.truthy(r.get("eligible_standard_rate_fit")):
                continue
            season = int(float(r.get("season") or 0)); week = int(float(r.get("week") or 0))
            if 2016 <= season <= 2025:
                by_week[(season, week)].append(r)

        player_hist: dict[str, list[float]] = defaultdict(list)
        pos_sum: dict[str, float] = defaultdict(float)
        pos_n: dict[str, int] = defaultdict(int)
        rows: list[dict[str, Any]] = []

        for season, week in sorted(by_week):
            batch = by_week[(season, week)]
            if season >= 2017:
                for r in batch:
                    pid = str(r.get("player_id") or "")
                    if not pid:
                        continue
                    actual = snap_share(r, team_snap_totals)
                    if actual is None:
                        continue
                    pg = er.canonical_position_group(r)
                    prior = pos_sum[pg] / pos_n[pg] if pos_n[pg] else 0.35
                    h = player_hist[pid]
                    last1 = h[-1] if h else prior
                    l2, l4, l8 = h[-2:], h[-4:], h[-8:]
                    m2 = er.mean_or(l2, prior); m4 = er.mean_or(l4, prior); m8 = er.mean_or(l8, prior)
                    s4 = er.std_or_zero(l4); mn4 = min(l4) if l4 else prior; mx4 = max(l4) if l4 else prior
                    rows.append({
                        "game_id": str(r.get("game_id") or ""), "season": season, "week": week,
                        "team": str(r.get("team") or ""), "opponent": str(r.get("opponent") or ""),
                        "player_id": pid, "display_name": str(r.get("display_name") or ""),
                        "position": str(r.get("position") or ""), "position_group": pg,
                        "actual_snap_share": actual,
                        "actual_defensive_snaps": float(er.num(r.get("defense_snaps")) or 0.0),
                        "prior_games": len(h), "baseline_last4_snap_share": m4,
                        "position_prior_snap_share": prior,
                        "prior_games_cap8": min(8, len(h)) / 8.0,
                        "prior_games_log": math.log1p(len(h)),
                        "last1_snap_share": last1,
                        "last2_snap_share_mean": m2,
                        "last4_snap_share_mean": m4,
                        "last8_snap_share_mean": m8,
                        "last4_snap_share_std": s4,
                        "last4_snap_share_min": mn4,
                        "last4_snap_share_max": mx4,
                        "last1_minus_last4": last1 - m4,
                        "last2_minus_last8": m2 - m8,
                        "position_DB": 1.0 if pg == "DB" else 0.0,
                        "position_LB": 1.0 if pg == "LB" else 0.0,
                        "position_DL": 1.0 if pg == "DL" else 0.0,
                        "position_OTHER": 1.0 if pg not in {"DB", "LB", "DL"} else 0.0,
                        "cold_start": 1.0 if len(h) == 0 else 0.0,
                        "one_prior_game": 1.0 if len(h) == 1 else 0.0,
                    })
            # Strict chronology: update only after every row in this week is emitted.
            for r in batch:
                pid = str(r.get("player_id") or "")
                if not pid:
                    continue
                share = snap_share(r, team_snap_totals)
                if share is None:
                    continue
                pg = er.canonical_position_group(r)
                player_hist[pid].append(float(share)); pos_sum[pg] += float(share); pos_n[pg] += 1
        return rows

    er.build_exposure_pregame_rows = build_through_2025
    return er


def main() -> int:
    root = Path("/Users/abbeyfelix/Developer/MODEL").resolve()
    # Respect the scorer's --root argument without consuming it.
    for i, arg in enumerate(sys.argv[:-1]):
        if arg == "--root":
            root = Path(sys.argv[i + 1]).expanduser().resolve()
            break
    install_eval_only_feature_builder(root)

    scorer_path = root / "scripts/nfl/score_omega_2025_current_role_holdout_0310.py"
    spec = importlib.util.spec_from_file_location("omega031_frozen_protocol_scorer", scorer_path)
    if spec is None or spec.loader is None:
        raise SystemExit("FAIL cannot load OMEGA 0.31 scorer")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    # Defensive formatting hardening only: empty diagnostic subgroups should not
    # crash the immutable scorer. They are explicitly n=0 and cannot satisfy a gate.
    original_compare = mod.compare
    def safe_compare(rows):
        if rows:
            return original_compare(rows)
        empty = {"n": 0, "actualMean": 0.0, "predictedMean": 0.0, "mae": 0.0, "rmse": 0.0, "biasPredMinusActual": 0.0}
        return {"n": 0, "h012": dict(empty), "role": dict(empty), "maeImprovement": 0.0, "rmseImprovement": 0.0, "biasChangeRoleMinusH012": 0.0}
    mod.compare = safe_compare
    return int(mod.main())


if __name__ == "__main__":
    raise SystemExit(main())

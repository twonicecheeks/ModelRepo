"""QB Model 0.2.4.1 — deterministic selector for immutable 0.2.4 scores.

This helper exists because the legacy CURRENT_QB_PASSING_YARDS_024 pointer is singular
while a live slate may contain multiple QBs. Selection is exact on game_id + GSIS ID.
If more than one immutable score matches, the caller must provide run_id; no silent
latest-wins behavior is permitted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

VERSION = "0.2.4.1"
LINEAGE = "nfl-qb-passing-yards-target-score-selector-v0.2.4.1-2026-09-17"


def validate_score(score: dict[str, Any], game_id: str, qb_gsis_id: str) -> None:
    if str(score.get("version")) != "0.2.4":
        raise ValueError("selector requires QB 0.2.4 score")
    if score.get("status") != "PROSPECTIVE_SHADOW_SCORE_FROZEN_0.2.1":
        raise ValueError("selector score status drift")
    if score.get("frozenCandidate") != "MODEL_A_DIRECT":
        raise ValueError("selector frozen candidate drift")
    if score.get("coefficientRefitPerformed") is not False or score.get("candidateReselectionPerformed") is not False:
        raise ValueError("selector refuses mutated score")
    if int(score.get("targetOrLater2026OutcomeRowsAdmitted") or 0) != 0:
        raise ValueError("selector detected target/later outcome leakage")
    if int(score.get("marketPriceFieldsAdmitted") or 0) != 0:
        raise ValueError("selector requires market-free 0.2.4 score")
    target = score.get("target") or {}
    if str(target.get("game_id") or "") != str(game_id).strip():
        raise ValueError("selector game mismatch")
    if str(target.get("qb_gsis_id") or "") != str(qb_gsis_id).strip():
        raise ValueError("selector QB mismatch")


def discover(root: Path, game_id: str, qb_gsis_id: str) -> list[dict[str, Any]]:
    base = root / "data/prospective/nfl/qb_passing_yards_024"
    matches: list[dict[str, Any]] = []
    if not base.exists():
        return matches
    for path in sorted(base.glob("*/NFL_QB_PASSING_YARDS_ASOF_SCORE.json")):
        try:
            score = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"cannot read immutable QB 0.2.4 score {path}: {exc}") from exc
        target = score.get("target") or {}
        if str(target.get("game_id") or "") != str(game_id).strip():
            continue
        if str(target.get("qb_gsis_id") or "") != str(qb_gsis_id).strip():
            continue
        validate_score(score, game_id, qb_gsis_id)
        matches.append({"path": path, "score": score})
    return matches


def select(root: Path, game_id: str, qb_gsis_id: str, run_id: str = "") -> dict[str, Any]:
    matches = discover(root, game_id, qb_gsis_id)
    if run_id:
        matches = [m for m in matches if str((m["score"] or {}).get("runId") or "") == str(run_id).strip()]
    if not matches:
        suffix = f" run_id={run_id}" if run_id else ""
        raise FileNotFoundError(f"no immutable QB 0.2.4 score for {game_id} {qb_gsis_id}{suffix}")
    if len(matches) != 1:
        runs = [str((m["score"] or {}).get("runId") or m["path"].parent.name) for m in matches]
        raise ValueError("multiple immutable QB 0.2.4 scores match; rerun with --run-id exactly one of: " + ", ".join(runs))
    return matches[0]

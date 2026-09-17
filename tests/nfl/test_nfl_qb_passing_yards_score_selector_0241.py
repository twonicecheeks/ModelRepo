#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
import qb_passing_yards_score_selector_0241 as s


def score(run_id: str, qb: str) -> dict:
    return {
        "version": "0.2.4",
        "runId": run_id,
        "status": "PROSPECTIVE_SHADOW_SCORE_FROZEN_0.2.1",
        "frozenCandidate": "MODEL_A_DIRECT",
        "coefficientRefitPerformed": False,
        "candidateReselectionPerformed": False,
        "targetOrLater2026OutcomeRowsAdmitted": 0,
        "marketPriceFieldsAdmitted": 0,
        "target": {"game_id": "2026_02_DET_BUF", "qb_gsis_id": qb},
    }


def write(root: Path, run_id: str, payload: dict) -> None:
    d = root / "data/prospective/nfl/qb_passing_yards_024" / run_id
    d.mkdir(parents=True, exist_ok=False)
    (d / "NFL_QB_PASSING_YARDS_ASOF_SCORE.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write(root, "A", score("A", "00-0034857"))
        write(root, "G", score("G", "00-0033106"))
        a = s.select(root, "2026_02_DET_BUF", "00-0034857")
        assert a["score"]["runId"] == "A"
        g = s.select(root, "2026_02_DET_BUF", "00-0033106")
        assert g["score"]["runId"] == "G"
        write(root, "A2", score("A2", "00-0034857"))
        try:
            s.select(root, "2026_02_DET_BUF", "00-0034857")
            raise AssertionError("ambiguous target should fail closed")
        except ValueError:
            pass
        a2 = s.select(root, "2026_02_DET_BUF", "00-0034857", "A2")
        assert a2["score"]["runId"] == "A2"
        bad = score("BAD", "00-0030000"); bad["targetOrLater2026OutcomeRowsAdmitted"] = 1
        write(root, "BAD", bad)
        try:
            s.select(root, "2026_02_DET_BUF", "00-0030000")
            raise AssertionError("leaky score should fail")
        except ValueError:
            pass
    print("PASS NFL QB Model 0.2.4.1 selector contracts · exact target · ambiguity fails closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

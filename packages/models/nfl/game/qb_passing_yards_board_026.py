"""NFL QB Model 0.2.6 — multi-book passing-yards board evaluation helpers.

Consumes one frozen 0.2.4 prospective score and multiple quoted half-yard markets.
No model refit/reselection is allowed. Market rows remain downstream diagnostics;
PROPSMADNESS_REFERENCE is reference-only and never execution truth.
"""
from __future__ import annotations

from typing import Any

VERSION = "0.2.6"
LINEAGE = "nfl-qb-passing-yards-multibook-shadow-board-v0.2.6-2026-09-16"


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def parse_optional_price(v: str) -> int | None:
    s = clean(v)
    if not s or s.upper() in {"NA", "NONE", "NULL", "-"}:
        return None
    return int(s)


def parse_quote(text: str, q25: Any) -> dict[str, Any]:
    """Parse BOOK|LINE|OVER|UNDER, allowing NA for a missing side."""
    parts = [p.strip() for p in str(text).split("|")]
    if len(parts) != 4:
        raise ValueError("quote must be BOOK|LINE|OVER|UNDER")
    book, raw_line, raw_over, raw_under = parts
    if not book:
        raise ValueError("quote book is blank")
    line = q25.assert_half_yard_line(float(raw_line))
    over = parse_optional_price(raw_over)
    under = parse_optional_price(raw_under)
    if over is None and under is None:
        raise ValueError("quote must contain at least one side price")
    if over is not None:
        over = q25.validate_american(over)
    if under is not None:
        under = q25.validate_american(under)
    return {"book": book, "line": line, "overAmerican": over, "underAmerican": under}


def add_probability_ci(side: dict[str, Any], ci95: list[float], price: int | None, q25: Any) -> dict[str, Any]:
    out = dict(side)
    out["modelProbabilityCi95"] = [float(ci95[0]), float(ci95[1])]
    if price is None:
        out["expectedRoiCi95"] = None
        out["expectedRoiPctCi95"] = None
        out["positiveEvAcrossProbabilityCi95"] = None
        return out
    lo = q25.expected_roi(float(ci95[0]), price)
    hi = q25.expected_roi(float(ci95[1]), price)
    out["expectedRoiCi95"] = [lo, hi]
    out["expectedRoiPctCi95"] = [100.0 * lo, 100.0 * hi]
    out["positiveEvAcrossProbabilityCi95"] = lo > 0.0
    return out


def shadow_disposition(side: dict[str, Any]) -> str:
    """Diagnostic only; never authorizes execution."""
    ev = side.get("expectedRoi")
    ci = side.get("expectedRoiCi95")
    if ev is None:
        return "UNPRICED"
    if ci is not None and float(ci[0]) > 0.0:
        return "ROBUST_POSITIVE_SHADOW"
    if float(ev) > 0.0:
        return "POINT_POSITIVE_SHADOW"
    return "NEGATIVE_EV_SHADOW"


def best_priced_side(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        for side_name in ("OVER", "UNDER"):
            side = row["sides"][side_name]
            if side.get("expectedRoi") is None:
                continue
            candidates.append({
                "book": row["book"], "line": row["line"], "side": side_name,
                "offeredAmerican": side["offeredAmerican"],
                "expectedRoi": side["expectedRoi"],
                "expectedRoiPct": side["expectedRoiPct"],
                "expectedRoiPctCi95": side.get("expectedRoiPctCi95"),
                "shadowDisposition": side.get("shadowDisposition"),
            })
    if not candidates:
        return None
    return max(candidates, key=lambda r: (float(r["expectedRoi"]), r["book"], r["side"]))


if __name__ == "__main__":
    print(f"NFL QB passing-yards board helpers {VERSION} · {LINEAGE}")

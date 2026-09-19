"""OMEGA 0.35.0 — postgame market-calibration helpers.

Grades frozen downstream OMEGA market-comparison rows against realized T+A without
refitting or mutating the underlying forecast. The goal is to audit the exact
issues exposed by DET@BUF Week 2:

* extreme nominal EV calibration,
* control-vs-role-shadow probability quality,
* role-state / operational-filter value,
* position-group error concentration,
* side-agreement stability,
* price-realized ROI as a descriptive downstream metric.

This module is postgame-only. It must never feed target-game outcomes back into the
frozen forecast that produced the row.
"""
from __future__ import annotations

from collections import defaultdict
from math import log
from statistics import fmean
from typing import Any, Iterable
import math

VERSION = "0.35.0"
LINEAGE = "omega-postgame-market-calibration-v0.35.0-det-buf-2026-09-17"


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _clip(p: float) -> float:
    return min(1.0 - 1e-12, max(1e-12, float(p)))


def american_profit_per_unit(odds: Any) -> float | None:
    x = _num(odds)
    if x is None or x == 0:
        return None
    return x / 100.0 if x > 0 else 100.0 / abs(x)


def side_price(row: dict[str, Any], side: str) -> float | None:
    side = str(side or "").upper()
    direct = _num(row.get("over_odds_american" if side == "OVER" else "under_odds_american"))
    if direct is not None:
        return direct
    one_side = str(row.get("one_sided_side") or "").upper()
    if one_side == side:
        return _num(row.get("one_sided_odds_american"))
    return None


def side_probability(row: dict[str, Any], prefix: str, side: str) -> float | None:
    side = str(side or "").upper()
    key = f"{prefix}p_{'over' if side == 'OVER' else 'under'}"
    p = _num(row.get(key))
    return p if p is not None and 0.0 <= p <= 1.0 else None


def outcome_side(actual_xtc: float, line: float) -> str:
    if actual_xtc > line:
        return "OVER"
    if actual_xtc < line:
        return "UNDER"
    return "PUSH"


def ev_bin(ev: Any) -> str:
    x = _num(ev)
    if x is None:
        return "EV_MISSING"
    if x < 0.05:
        return "EV_LT_5"
    if x < 0.10:
        return "EV_5_10"
    if x < 0.20:
        return "EV_10_20"
    if x < 0.35:
        return "EV_20_35"
    return "EV_35_PLUS"


def probability_bin(p: Any) -> str:
    x = _num(p)
    if x is None:
        return "P_MISSING"
    lo = int(min(9, max(0, math.floor(x * 10))))
    hi = lo + 1
    return f"P_{lo*10:02d}_{hi*10:02d}"


def grade_row(row: dict[str, Any], actual_xtc: float) -> dict[str, Any]:
    line = _num(row.get("line"))
    if line is None:
        raise ValueError("OMEGA calibration row missing line")
    actual_side = outcome_side(float(actual_xtc), line)

    cb_side = str(row.get("control_best_side") or "").upper()
    rb_side = str(row.get("role_shadow_best_side") or "").upper()
    cp = side_probability(row, "control_", cb_side) if cb_side in {"OVER", "UNDER"} else None
    rp = side_probability(row, "role_shadow_", rb_side) if rb_side in {"OVER", "UNDER"} else None
    c_hit = None if actual_side == "PUSH" or cb_side not in {"OVER", "UNDER"} else int(cb_side == actual_side)
    r_hit = None if actual_side == "PUSH" or rb_side not in {"OVER", "UNDER"} else int(rb_side == actual_side)

    c_brier = None if cp is None or c_hit is None else (cp - c_hit) ** 2
    r_brier = None if rp is None or r_hit is None else (rp - r_hit) ** 2
    c_ll = None if cp is None or c_hit is None else -(c_hit * log(_clip(cp)) + (1-c_hit) * log(_clip(1-cp)))
    r_ll = None if rp is None or r_hit is None else -(r_hit * log(_clip(rp)) + (1-r_hit) * log(_clip(1-rp)))

    price = side_price(row, cb_side) if cb_side in {"OVER", "UNDER"} else None
    payout = american_profit_per_unit(price)
    realized_roi = None if payout is None or c_hit is None else (payout if c_hit else -1.0)

    over_y = None if actual_side == "PUSH" else int(actual_side == "OVER")
    c_over = _num(row.get("control_p_over"))
    r_over = _num(row.get("role_shadow_p_over"))
    c_over_brier = None if over_y is None or c_over is None else (c_over - over_y) ** 2
    r_over_brier = None if over_y is None or r_over is None else (r_over - over_y) ** 2

    status = str(row.get("overlay_operational_status") or row.get("operational_status") or "")
    role_state = str(row.get("overlay_role_state") or row.get("role_state") or "")
    quote_class = str(row.get("market_quote_classification") or "")
    clean_role = role_state in {"ROLE_ALIGNED", "STARTER_CONFLICT_RESOLVED_TEAM_DEPTH_CHART"}
    executable = quote_class == "EXECUTABLE_OFFER" or str(row.get("market_source") or "").endswith("table-api")

    out = dict(row)
    out.update({
        "actual_xtc": float(actual_xtc),
        "actual_side": actual_side,
        "control_selected_probability": cp,
        "role_shadow_selected_probability": rp,
        "control_selected_hit": c_hit,
        "role_shadow_selected_hit": r_hit,
        "control_selected_brier": c_brier,
        "role_shadow_selected_brier": r_brier,
        "control_selected_log_loss": c_ll,
        "role_shadow_selected_log_loss": r_ll,
        "control_over_brier": c_over_brier,
        "role_shadow_over_brier": r_over_brier,
        "control_selected_price_american": price,
        "control_realized_roi": realized_roi,
        "control_ev_bin": ev_bin(row.get("control_best_ev")),
        "control_probability_bin": probability_bin(cp),
        "clean_role_state": clean_role,
        "executable_quote": executable,
        "final_market_eligible": status == "MARKET_ELIGIBLE_CONTROL_TRACK",
        "quarantined_or_reference": (
            "REVIEW" in status or "QUARANTIN" in status or "REFERENCE_ONLY" in status or "NO_ACTION" in status
        ),
    })
    return out


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hit = [int(r["control_selected_hit"]) for r in rows if r.get("control_selected_hit") is not None]
    role_hit = [int(r["role_shadow_selected_hit"]) for r in rows if r.get("role_shadow_selected_hit") is not None]
    cb = [float(r["control_selected_brier"]) for r in rows if r.get("control_selected_brier") is not None]
    rb = [float(r["role_shadow_selected_brier"]) for r in rows if r.get("role_shadow_selected_brier") is not None]
    cll = [float(r["control_selected_log_loss"]) for r in rows if r.get("control_selected_log_loss") is not None]
    rll = [float(r["role_shadow_selected_log_loss"]) for r in rows if r.get("role_shadow_selected_log_loss") is not None]
    roi = [float(r["control_realized_roi"]) for r in rows if r.get("control_realized_roi") is not None]
    probs = [float(r["control_selected_probability"]) for r in rows if r.get("control_selected_probability") is not None and r.get("control_selected_hit") is not None]
    return {
        "rows": len(rows),
        "gradedSelectedSides": len(hit),
        "controlHitRate": fmean(hit) if hit else None,
        "roleShadowHitRate": fmean(role_hit) if role_hit else None,
        "controlMeanSelectedProbability": fmean(probs) if probs else None,
        "controlBrier": fmean(cb) if cb else None,
        "roleShadowBrier": fmean(rb) if rb else None,
        "controlLogLoss": fmean(cll) if cll else None,
        "roleShadowLogLoss": fmean(rll) if rll else None,
        "realizedFlatUnitRoi": fmean(roi) if roi else None,
        "pricedRows": len(roi),
    }


def _group(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(key) or "MISSING")].append(r)
    return {k: _metric_summary(v) for k, v in sorted(groups.items())}


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(r) for r in rows]
    clean = [r for r in rows if r.get("clean_role_state") and r.get("executable_quote") and not r.get("quarantined_or_reference")]
    filtered_out = [r for r in rows if r.get("quarantined_or_reference") or not r.get("clean_role_state")]
    eligible = [r for r in rows if r.get("final_market_eligible")]
    extreme = [r for r in rows if r.get("control_ev_bin") == "EV_35_PLUS"]
    extm = _metric_summary(extreme)
    ext_n = int(extm["gradedSelectedSides"])
    calibration_status = "SAMPLE_INSUFFICIENT" if ext_n < 50 else "REVIEW_CALIBRATION"

    return {
        "version": VERSION,
        "lineage": LINEAGE,
        "all": _metric_summary(rows),
        "cleanRoleExecutableNotQuarantined": _metric_summary(clean),
        "filteredOutOrRoleConflict": _metric_summary(filtered_out),
        "finalMarketEligible": _metric_summary(eligible),
        "byControlEvBin": _group(rows, "control_ev_bin"),
        "byControlProbabilityBin": _group(rows, "control_probability_bin"),
        "byPositionGroup": _group(rows, "position_group"),
        "byRoleState": _group(rows, "overlay_role_state" if any(r.get("overlay_role_state") for r in rows) else "role_state"),
        "byOperationalStatus": _group(rows, "overlay_operational_status" if any(r.get("overlay_operational_status") for r in rows) else "operational_status"),
        "byTracksAgree": _group(rows, "tracks_agree_side"),
        "extremeEv35Plus": {
            **extm,
            "calibrationStatus": calibration_status,
            "automaticProbabilityCompressionAllowed": False,
            "interpretation": "Do not recalibrate from a single game or small bucket. Accumulate prospective graded rows first.",
        },
        "operationalFilterDiagnostic": {
            "cleanRows": len(clean),
            "filteredRows": len(filtered_out),
            "interpretation": "Compare prospectively across a large sample; this diagnostic does not retroactively promote or suppress rows.",
        },
        "modelRefitPerformed": False,
        "frozenOmegaMutation": False,
        "marketFieldsUsedAsForecastFeatures": False,
    }


if __name__ == "__main__":
    print(f"OMEGA {VERSION} · {LINEAGE}")

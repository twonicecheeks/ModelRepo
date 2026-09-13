"""Downstream NFL market comparison math.

This module MUST NOT be imported by the independent probability fitter. Market
prices enter only after an independent model probability has already been created.
"""
from __future__ import annotations
from typing import Any

VERSION = "0.1.0"


def american_to_implied(odds: float) -> float:
    o = float(odds)
    if o == 0:
        raise ValueError("American odds cannot be zero")
    return 100.0 / (o + 100.0) if o > 0 else (-o) / ((-o) + 100.0)


def american_profit_multiple(odds: float) -> float:
    o = float(odds)
    if o == 0:
        raise ValueError("American odds cannot be zero")
    return o / 100.0 if o > 0 else 100.0 / (-o)


def two_way_no_vig(side_odds: float, other_odds: float) -> float:
    a = american_to_implied(side_odds); b = american_to_implied(other_odds)
    if a + b <= 0:
        raise ValueError("invalid market")
    return a / (a + b)


def expected_roi(model_probability: float, offered_odds: float) -> float:
    p = float(model_probability)
    if not 0 <= p <= 1:
        raise ValueError("probability outside [0,1]")
    win = american_profit_multiple(offered_odds)
    return p * win - (1.0 - p)


def compare_market(model_probability: float, side_odds: float, other_odds: float) -> dict[str, Any]:
    """Compare an independent probability against a two-way market downstream."""
    p = float(model_probability); mv = two_way_no_vig(side_odds, other_odds)
    return {"modelProbability": p, "marketNoVigProbability": mv, "edgeProbabilityPoints": 100.0*(p-mv),
            "expectedROI": expected_roi(p, side_odds), "offeredOdds": float(side_odds), "otherSideOdds": float(other_odds)}

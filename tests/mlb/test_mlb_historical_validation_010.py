from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "packages/models/mlb/evaluation"
sys.path.insert(0, str(MODEL_DIR))

import historical_validation_010 as m


def ml(game, season, st, p, y, odds=None, close=None, variant="PRODUCTION"):
    return {
        "game_id": game,
        "game_date": f"{season}-06-01",
        "season": season,
        "season_type": st,
        "market_type": "ML",
        "model_probability": p,
        "actual_win": y,
        "market_odds": odds,
        "closing_odds": close,
        "model_variant": variant,
        "selection_team": "X",
        "stage": "VERIFIED",
        "thesis": "CONFIRMED",
    }


def k(game, season, st, p, xk, ak, side="OVER", line=4.5, odds=None):
    return {
        "game_id": game,
        "game_date": f"{season}-06-02",
        "season": season,
        "season_type": st,
        "market_type": "K",
        "model_probability": p,
        "pitcher": "P",
        "side": side,
        "line": line,
        "xk": xk,
        "actual_k": ak,
        "market_odds": odds,
        "model_variant": "PRODUCTION",
        "stage": "READY_FOR_K_TRUST",
        "thesis": "MIXED",
    }


def main():
    assert abs(m.american_to_decimal(-110) - 1.909090909) < 1e-8
    assert abs(m.american_to_decimal(150) - 2.5) < 1e-12
    assert m.unit_profit(-110, 1) > 0
    assert m.unit_profit(-110, 0) == -1

    rows = [
        ml("g1", 2024, "REG", 0.7, 1, -110, -130),
        ml("g2", 2024, "REG", 0.4, 0, 120, 110),
        ml("g3", 2024, "POST", 0.6, 0, -105, -115),
        ml("g4", 2024, "POST", 0.8, 1, -150, -170),
    ]
    s = m.summarize(rows)
    assert s["n"] == 4 and s["scored_n"] == 4
    assert 0 < s["brier"] < 1
    assert s["raw_implied_clv"]["mean_probability_points"] > 0

    kr = [
        k("k1", 2024, "REG", 0.6, 5.5, 6, odds=-110),
        k("k2", 2025, "POST", 0.55, 4.0, 3, side="UNDER", line=4.5, odds=100),
    ]
    ks = m.summarize(kr)
    assert abs(ks["xk"]["bias"] - 0.25) < 1e-12
    assert ks["betting"]["profit_units"] > 0

    push = k("k3", 2025, "POST", 0.5, 4.0, 4, side="OVER", line=4.0, odds=-110)
    ps = m.summarize([push])
    assert ps["scored_n"] == 0
    assert ps["betting"]["profit_units"] == 0


    xk_only = {
        "game_id": "kx1",
        "game_date": "2025-10-03",
        "season": 2025,
        "season_type": "POST",
        "market_type": "K",
        "evaluation_mode": "XK_ONLY",
        "pitcher": "PX",
        "xk": 6.2,
        "actual_k": 7,
        "model_variant": "POST_USAGE_PROXY",
        "stage": "RESEARCH",
        "thesis": "WORKLOAD_PROXY",
    }
    xs = m.summarize([xk_only])
    assert xs["n"] == 1 and xs["scored_n"] == 0
    assert abs(xs["xk"]["mae"] - 0.8) < 1e-12
    assert "brier" not in xs
    m.validate_row(xk_only)

    variants = [
        ml("p1", 2025, "POST", 0.55, 1, variant="BASE"),
        ml("p1", 2025, "POST", 0.65, 1, variant="CHALL"),
    ]
    pc = m.paired_variant_comparison(variants, "BASE", "CHALL")
    assert pc["matched_n"] == 1
    assert pc["challenger_minus_baseline_brier"] < 0

    fa = m.full_audit(rows + kr)
    assert fa["rows"] == 6
    assert "brier" in fa["postseason_shift"]
    assert "xk_bias" in fa["postseason_shift"]
    assert "2024" in fa["season"] and "2025" in fa["season"]

    print("PASS MLB historical validation 0.1.4")


if __name__ == "__main__":
    main()

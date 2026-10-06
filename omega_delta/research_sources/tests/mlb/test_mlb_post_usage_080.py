from pathlib import Path
import importlib.util
import math

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/mlb/evaluate_mlb_post_usage_080.py"
spec = importlib.util.spec_from_file_location("postusage080", PATH)
m = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(m)


def krow(season, game_id, pid, xk=5.0, actual=4.0, workload="REGULAR_SEASON_STARTS"):
    return {
        "game_id": str(game_id),
        "game_date": f"{season}-10-01",
        "season": season,
        "season_type": "POST",
        "market_type": "K",
        "evaluation_mode": "XK_ONLY",
        "pitcher": f"P{pid}",
        "xk": xk,
        "actual_k": actual,
        "workload_proxy_source": workload,
        "k_projection": {
            "officialMlbId": str(pid),
            "components": {
                "expectedBF": 24.0,
                "expectedOuts": 17.0,
                "matchupK": 25.0,
                "structuralK": 6.0,
                "recentK": 5.0,
                "seasonK": 4.5,
                "blendWeights": {"structural": 0.70, "recent": 0.20, "season": 0.10},
            },
        },
    }


def main():
    assert m.ip_to_outs("5.2") == 17
    assert m.ip_to_outs("6.0") == 18
    assert m.ip_to_outs("3.1") == 10

    targets = [
        {
            "season": 2024, "game_id": "1",
            "away": {"starter": {"mlb_id": "10", "batters_faced": 22, "innings_pitched": "5.2"}},
            "home": {"starter": {"mlb_id": "20", "batters_faced": 25, "innings_pitched": "6.0"}},
        }
    ]
    idx = m.target_workload_index(targets)
    assert idx[(2024, "1", "10")] == {"bf": 22.0, "outs": 17.0}
    assert idx[(2024, "1", "20")] == {"bf": 25.0, "outs": 18.0}

    reg = {
        (2015, "10"): [{"bf": 24.0, "outs": 18.0}],
        (2016, "10"): [{"bf": 25.0, "outs": 18.0}],
        (2016, "20"): [{"bf": 22.0, "outs": 16.0}],
    }
    post = {
        (2015, "10"): [{"bf": 21.0, "outs": 15.0}],
        (2016, "10"): [{"bf": 22.0, "outs": 16.0}],
        (2016, "20"): [{"bf": 20.0, "outs": 14.0}],
    }
    ratios = m.matched_pitcher_season_ratios(reg, post)
    assert len(ratios) == 3
    factors = m.expanding_factors(ratios, [2015, 2016, 2017])
    assert factors[2015]["status"] == "WARMUP_NO_PRIOR_POSTSEASON"
    assert factors[2016]["training_seasons"] == [2015]
    assert factors[2017]["training_seasons"] == [2015, 2016]
    assert factors[2016]["bf_factor"] == 21.0 / 24.0

    row = krow(2020, "g", "10")
    xk, diag = m.usage_adjusted_xk(row, 0.90)
    expected_bf = 21.6
    structural = expected_bf * 0.25
    expected = 0.70 * structural + 0.20 * 5.0 + 0.10 * 4.5
    assert math.isclose(diag["adjusted_expected_bf"], expected_bf)
    assert math.isclose(xk, expected)

    base = [krow(2019, "a", "1", 5.0, 4.0), krow(2020, "b", "2", 6.0, 4.0)]
    chall = []
    for r in base:
        c = dict(r)
        c["xk"] = r["xk"] - 0.5
        c["model_variant"] = m.CHALLENGER_VARIANT
        chall.append(c)
    comp = m.paired_bootstrap(base, chall, reps=200, seed=1)
    assert comp["matched_n"] == 2
    assert comp["challenger"]["mae"] < comp["baseline"]["mae"]
    assert comp["challenger_minus_baseline"]["bias"] < 0

    print("PASS MLB postseason usage challenger 0.8.0")


if __name__ == "__main__":
    main()


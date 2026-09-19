from pathlib import Path
import importlib.util
import math

ROOT = Path(__file__).resolve().parents[2]
P090 = ROOT / "scripts/mlb/evaluate_mlb_post_usage_mechanisms_090.py"
P080 = ROOT / "scripts/mlb/evaluate_mlb_post_usage_080.py"

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(m)
    return m

m = load(P090, "postusage090")
v080 = load(P080, "postusage080")

def row():
    return {
        "game_id": "1",
        "game_date": "2024-10-01",
        "season": 2024,
        "season_type": "POST",
        "market_type": "K",
        "evaluation_mode": "XK_ONLY",
        "pitcher": "P",
        "xk": 6.0,
        "actual_k": 5.0,
        "workload_proxy_source": "REGULAR_SEASON_STARTS",
        "k_projection": {
            "officialMlbId": "10",
            "components": {
                "expectedBF": 24.0,
                "expectedOuts": 17.0,
                "expectedHits": 5.0,
                "expectedWalks": 1.7,
                "matchupK": 25.0,
                "structuralK": 6.0,
                "recentK": 5.0,
                "seasonK": 4.5,
                "blendWeights": {"structural": 0.70, "recent": 0.20, "season": 0.10},
            },
        },
    }

def main():
    r = row()
    xk, d = m.outs_adjusted_xk(r, 0.88)
    adjusted_outs = 17.0 * 0.88
    adjusted_bf = adjusted_outs + 5.0 + 1.7 + 0.30
    structural = adjusted_bf * 0.25
    expected = 0.70 * structural + 0.20 * 5.0 + 0.10 * 4.5
    assert math.isclose(d["adjusted_expected_outs"], adjusted_outs)
    assert math.isclose(d["adjusted_expected_bf"], adjusted_bf)
    assert math.isclose(xk, expected)

    # BF and OUTS mechanisms should be distinct for the same factor value.
    bf_xk, _ = v080.usage_adjusted_xk(r, 0.88)
    assert not math.isclose(xk, bf_xk)

    print("PASS MLB postseason usage mechanism bakeoff 0.9.0")

if __name__ == "__main__":
    main()

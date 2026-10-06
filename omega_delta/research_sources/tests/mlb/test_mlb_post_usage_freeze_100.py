from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/mlb/freeze_mlb_post_usage_100.py"
spec = importlib.util.spec_from_file_location("freeze100", PATH)
m = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(m)


def candidate():
    return {
        "model_variant": "POST_USAGE_OUTS",
        "factor_field": "outs_ratio",
        "factor_value_for_2026_prospective": 0.868312345,
        "training_seasons": list(range(2015, 2026)),
        "training_pitcher_seasons": 364,
        "freeze_status": "CANDIDATE_REQUIRES_EXPLICIT_FREEZE",
        "prospective_test_season": 2026,
        "k_outcomes_used_to_learn_factor": False,
    }


def audit():
    return {
        "status": "HISTORICAL_DEVELOPMENT_BAKEOFF_NOT_FRESH_VALIDATION",
        "historical_development_selection": {"selected": "POST_USAGE_OUTS"},
        "freeze_candidate": candidate(),
        "production_model_mutation": False,
        "model_refit_performed": False,
    }


def main():
    c = m.validate_candidate(audit())
    assert c["training_pitcher_seasons"] == 364
    s = m.stable_spec(c, "corehash", "audithash")
    assert s["model_variant"] == "POST_USAGE_OUTS"
    assert s["factor_field"] == "outs_ratio"
    assert s["factor_value"] == 0.868312345
    assert s["prospective_test_season"] == 2026
    assert s["same_2026_postseason_usage_used"] is False

    bad = audit()
    bad["freeze_candidate"] = dict(candidate())
    bad["freeze_candidate"]["k_outcomes_used_to_learn_factor"] = True
    try:
        m.validate_candidate(bad)
        raise AssertionError("expected K-outcome contamination rejection")
    except ValueError:
        pass

    bad = audit()
    bad["historical_development_selection"] = {"selected": "POST_USAGE_BF"}
    try:
        m.validate_candidate(bad)
        raise AssertionError("expected mechanism mismatch rejection")
    except ValueError:
        pass

    print("PASS MLB postseason usage freeze 1.0.0")


if __name__ == "__main__":
    main()


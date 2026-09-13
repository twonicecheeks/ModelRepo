#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))
import research_model as rm

# Feature vector must be symmetric and market-independent.
row = {
    "home_rest_days": "8", "away_rest_days": "6", "neutral_site": "false",
    "home_games_available": "3", "away_games_available": "2",
    "home_moneyline": "-150", "spread_line": "-3.5",  # must be ignored
}
for horizon in rm.HORIZONS:
    for i, metric in enumerate(rm.TEAM_METRICS):
        row[f"home_{horizon}_{metric}"] = str(1.0 + i / 100)
        row[f"away_{horizon}_{metric}"] = str(0.5 + i / 100)
vec1 = rm.vectorize_feature_row(row)
row["home_moneyline"] = "+900"
row["spread_line"] = "+17.5"
vec2 = rm.vectorize_feature_row(row)
assert vec1 == vec2
assert len(vec1) == len(rm.expanded_feature_names())
assert vec1[0] == 2.0 and vec1[1] == 0.0

# Missingness must be explicit rather than silently becoming a performance value.
missing = dict(row)
missing["home_prior_season_off_dropback_epa"] = ""
vm = rm.vectorize_feature_row(missing)
idx = rm.expanded_feature_names().index("prior_season_off_dropback_epa_diff")
assert vm[idx] is None
assert vm[idx + 1] == 1.0

# Synthetic signal: positive home-minus-away efficiency should map to higher home win probability.
def make(gid, season, week, xsignal, y):
    r = {
        "game_id": gid, "season": str(season), "week": str(week), "game_type": "REG",
        "home_team": "H", "away_team": "A", "home_rest_days": "7", "away_rest_days": "7",
        "neutral_site": "false", "home_games_available": str(max(0, week-1)), "away_games_available": str(max(0, week-1)),
    }
    for horizon in rm.HORIZONS:
        for metric in rm.TEAM_METRICS:
            r[f"home_{horizon}_{metric}"] = str(xsignal)
            r[f"away_{horizon}_{metric}"] = "0"
    return r, y

rows=[]; targets={}
for season in range(2016, 2025):
    for week in range(1, 13):
        sig = 1.0 if week % 2 else -1.0
        y = 1 if sig > 0 else 0
        r, yy = make(f"{season}_{week:02d}_A_H", season, week, sig, y)
        rows.append(r); targets[r["game_id"]]=yy
examples=rm.examples_from_rows(rows,targets,allowed_seasons=set(range(2016,2025)))
model=rm.fit_logistic(examples,l2=0.1,max_iter=500)
pos=next(e for e in examples if e.y==1); neg=next(e for e in examples if e.y==0)
assert model.predict_proba(pos.x) > 0.8, model.predict_proba(pos.x)
assert model.predict_proba(neg.x) < 0.2, model.predict_proba(neg.x)

wf=rm.walk_forward_l2(examples,validation_seasons=[2021,2022,2023,2024],l2_grid=[0.03,0.1])
assert wf["selectedL2"] in (0.03,0.1)
assert all(f["season"] <= 2024 for c in wf["candidates"] for f in c["folds"])

ys=[0,1,1,0]; ps=[0.1,0.8,0.7,0.2]
assert rm.brier_score(ys,ps) < 0.1
assert rm.log_loss(ys,ps) < 0.4
assert rm.accuracy(ys,ps) == 1.0

# Holdout constant is explicit; Phase 2A is not a holdout evaluator.
assert rm.HOLDOUT_SEASON == 2025
assert rm.CALIBRATION_STATUS == "DEVELOPMENT_ONLY_HOLDOUT_UNTOUCHED"
print("PASS NFL Phase 2A research model: market isolation, explicit missingness, deterministic L2 logistic, chronological validation")

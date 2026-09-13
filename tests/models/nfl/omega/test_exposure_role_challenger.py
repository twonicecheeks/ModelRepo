import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
MOD = ROOT / "packages/models/nfl/omega/exposure_role_challenger.py"
spec = importlib.util.spec_from_file_location("er", MOD)
er = importlib.util.module_from_spec(spec)
sys.modules["er"] = er
spec.loader.exec_module(er)


def row(game, season, week, pid, pct, team="A", pg="LB"):
    return {
        "game_id": game, "season": season, "week": week, "team": team, "opponent": "B",
        "player_id": pid, "display_name": pid, "position": pg, "position_group": pg,
        "defense_snaps": pct*60, "defense_pct": pct,
        "eligible_standard_rate_fit": 1,
    }


class ExposureRoleTests(unittest.TestCase):
    def test_cold_start_uses_prior_only_fallback(self):
        rows=[row("2016_01_B_A",2016,1,"seed",.8), row("2017_01_B_A",2017,1,"new",.9)]
        totals={(r["game_id"],r["team"]):60.0 for r in rows}
        out=er.build_exposure_pregame_rows(rows,totals)
        r=next(x for x in out if x["player_id"]=="new")
        self.assertEqual(r["prior_games"],0)
        self.assertAlmostEqual(r["last1_snap_share"],r["position_prior_snap_share"])
        self.assertAlmostEqual(r["last4_snap_share_mean"],r["position_prior_snap_share"])

    def test_target_outcome_does_not_enter_features(self):
        base=[row("2016_01_B_A",2016,1,"p",.4), row("2017_01_B_A",2017,1,"p",.9)]
        alt=[dict(x) for x in base]
        alt[-1]["defense_pct"]=.1; alt[-1]["defense_snaps"]=6
        totals={(r["game_id"],r["team"]):60.0 for r in base}
        a=er.build_exposure_pregame_rows(base,totals)[0]
        b=er.build_exposure_pregame_rows(alt,totals)[0]
        for name in er.FEATURE_NAMES:
            self.assertAlmostEqual(float(a[name]),float(b[name]))
        self.assertNotEqual(a["actual_snap_share"],b["actual_snap_share"])

    def test_ridge_predictions_are_bounded(self):
        rows=[]
        for i in range(40):
            y=0.1+0.02*i
            r={name:0.0 for name in er.FEATURE_NAMES}
            r["last1_snap_share"]=min(1,y)
            r["last4_snap_share_mean"]=min(1,y)
            r["actual_snap_share"]=min(1,y)
            rows.append(r)
        m=er.fit_ridge(rows,.1)
        lo={name:-100.0 for name in er.FEATURE_NAMES}
        hi={name:100.0 for name in er.FEATURE_NAMES}
        self.assertGreaterEqual(m.predict(lo),0.0)
        self.assertLessEqual(m.predict(hi),1.0)

    def test_2024_cannot_change_l2_selection(self):
        rows=[]
        for year in range(2017,2025):
            for i in range(20):
                r={name:0.0 for name in er.FEATURE_NAMES}
                x=(i%10)/10
                r["season"]=year; r["last1_snap_share"]=x; r["last4_snap_share_mean"]=x
                r["baseline_last4_snap_share"]=x; r["actual_snap_share"]=x
                rows.append(r)
        a,_=er.choose_l2(rows)
        altered=[dict(r) for r in rows]
        for r in altered:
            if r["season"]==2024: r["actual_snap_share"]=1.0-r["actual_snap_share"]
        b,_=er.choose_l2(altered)
        self.assertEqual(a,b)

if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/mlb/acquire_mlb_historical_outcomes_030.py"
spec = importlib.util.spec_from_file_location("outcomes030", PATH)
m = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(m)


def player(pid, name, gs, k, ip, bf, pitches):
    return {
        "person": {"id": int(pid), "fullName": name},
        "stats": {
            "pitching": {
                "gamesStarted": gs,
                "strikeOuts": k,
                "inningsPitched": ip,
                "battersFaced": bf,
                "numberOfPitches": pitches,
                "hits": 5,
                "runs": 2,
                "earnedRuns": 2,
                "baseOnBalls": 1,
            }
        },
    }


def main():
    assert m.parse_seasons("2024-2025,2023") == [2023, 2024, 2025]

    schedule = {
        "gamePk": 999001,
        "officialDate": "2025-10-08",
        "gameDate": "2025-10-08T23:08:00Z",
        "season": "2025",
        "gameType": "D",
        "status": {"abstractGameState": "Final", "codedGameState": "F"},
        "teams": {
            "away": {"team": {"id": 1, "name": "Away Club"}, "score": 3},
            "home": {"team": {"id": 2, "name": "Home Club"}, "score": 5},
        },
    }
    box = {
        "teams": {
            "away": {
                "pitchers": [101, 102],
                "players": {
                    "ID101": player("101", "Away Starter", 1, 7, "5.2", 23, 92),
                    "ID102": player("102", "Away Reliever", 0, 2, "2.1", 8, 31),
                },
            },
            "home": {
                "pitchers": [201, 202],
                "players": {
                    "ID201": player("201", "Home Starter", 1, 5, "6.0", 24, 88),
                    "ID202": player("202", "Home Reliever", 0, 3, "3.0", 10, 36),
                },
            },
        }
    }

    row = m.game_target(schedule, box)
    assert row["season_type"] == "POST"
    assert row["actual_home_win"] == 1
    assert row["away"]["starter"]["mlb_id"] == "101"
    assert row["away"]["starter"]["strikeouts"] == 7
    assert row["home"]["starter"]["mlb_id"] == "201"
    assert row["home"]["starter"]["pitches"] == 88
    assert row["source_role"] == "OUTCOME_TARGET_ONLY"
    assert row["outcome_is_postgame_only"] is True

    print("PASS MLB historical outcomes parser 0.3.0")


if __name__ == "__main__":
    main()

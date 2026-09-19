from pathlib import Path
from urllib.parse import parse_qs, urlparse
import importlib.util
import ssl

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/mlb/acquire_mlb_regular_control_070.py"
spec = importlib.util.spec_from_file_location("regular070", PATH)
m = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(m)

def q(url):
    return parse_qs(urlparse(url).query, keep_blank_values=True)

def pitcher(pid, name, gs=1, k=5):
    return {
        "person": {"id": int(pid), "fullName": name},
        "stats": {"pitching": {
            "gamesStarted": gs, "strikeOuts": k, "inningsPitched": "5.0",
            "battersFaced": 21, "numberOfPitches": 84, "hits": 4,
            "earnedRuns": 2, "baseOnBalls": 1,
        }},
    }

def main():
    s = q(m.schedule_url(2024))
    assert s["gameTypes"] == ["R"]
    assert s["season"] == ["2024"]

    r = q(m.savant_recon_url(2024, "pitcher"))
    assert r["year"] == ["2024"]
    assert r["type"] == ["pitcher"]
    for key in ("strikeout", "pitch_count", "in_zone_swing", "out_zone_swing_miss"):
        assert key in r["selections"][0]

    d = q(m.statcast_day_url(2024, "2024-09-29"))
    assert d["hfGT"] == ["R|"]
    assert d["game_date_gt"] == ["2024-09-29"]
    assert d["game_date_lt"] == ["2024-09-29"]
    assert d["type"] == ["details"]

    cert = ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED")
    assert m.certificate_verify_error(cert)

    g = {
        "gamePk": 123,
        "officialDate": "2024-09-29",
        "gameDate": "2024-09-29T19:05:00Z",
        "season": "2024",
        "status": {"abstractGameState": "Final", "codedGameState": "F"},
        "venue": {"id": 1, "name": "Park"},
        "teams": {
            "away": {"team": {"id": 10, "name": "Away"}, "score": 2},
            "home": {"team": {"id": 20, "name": "Home"}, "score": 4},
        },
    }
    box = {"teams": {
        "away": {"pitchers": [101], "players": {"ID101": pitcher(101, "A")}},
        "home": {"pitchers": [201], "players": {"ID201": pitcher(201, "H")}},
    }}
    row = m.control_target(g, box, {10}, __import__("datetime").date(2024, 9, 29))
    assert row["season_type"] == "REG"
    assert row["control_match_quality"] == "ONE_POSTSEASON_TEAM"
    assert row["actual_home_win"] == 1
    assert row["away"]["starter"]["mlb_id"] == "101"


    # Duplicate schedule representations collapse to one gamePk and preserve
    # the earliest game placement while retaining the most complete final row.
    dup_a = dict(g)
    dup_b = dict(g)
    dup_a["officialDate"] = "2024-09-28"
    dup_a["gameDate"] = "2024-09-28T19:05:00Z"
    dup_b["officialDate"] = "2024-09-29"
    dup_b["gameDate"] = "2024-09-29T19:05:00Z"
    deduped, removed = m.dedupe_schedule_games([dup_b, dup_a])
    assert removed == 1
    assert len(deduped) == 1
    assert deduped[0]["officialDate"] == "2024-09-28"

    tie_g = dict(g)
    tie_g["teams"] = {
        "away": {"team": {"id": 10, "name": "Away"}, "score": 3},
        "home": {"team": {"id": 20, "name": "Home"}, "score": 3},
    }
    tie = m.control_target(tie_g, box, {10}, __import__("datetime").date(2024, 9, 29))
    assert tie["outcome_tied"] is True
    assert tie["actual_home_win"] is None

    print("PASS MLB late regular control acquisition 0.7.4")

if __name__ == "__main__":
    main()

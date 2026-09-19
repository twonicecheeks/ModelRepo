from pathlib import Path
from urllib.parse import parse_qs, urlparse
import importlib.util
import json
import ssl
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/mlb/acquire_mlb_postseason_priors_040.py"
spec = importlib.util.spec_from_file_location("priors040", PATH)
m = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(m)


def q(url):
    return parse_qs(urlparse(url).query, keep_blank_values=True)


def main():
    s = q(m.savant_custom_url(2024, "pitcher"))
    assert s["year"] == ["2024"]
    assert s["type"] == ["pitcher"]
    assert s["csv"] == ["true"]
    assert "xwoba" in s["selections"][0]
    assert "whiff_percent" in s["selections"][0]

    f = q(m.fangraphs_wrc_url(2024))
    assert f["season"] == ["2024"]
    assert f["season1"] == ["2024"]
    assert f["postseason"] == [""]

    p = q(m.park_url(2024, 3))
    assert p["year"] == ["2024"]
    assert p["rolling"] == ["3"]

    r = q(m.roster_url(147, 2024, "2024-10-05"))
    assert r["season"] == ["2024"]
    assert r["date"] == ["2024-10-05"]

    t = q(m.team_pitching_url(147, 2024))
    assert t["gameType"] == ["R"]
    assert t["teamId"] == ["147"]

    g = q(m.player_game_log_url("543037", 2024))
    assert g["stats"] == ["gameLog"]
    assert g["group"] == ["pitching"]
    assert g["season"] == ["2024"]
    assert g["gameType"] == ["R"]

    assert m.prior_date("2024-10-01") == "2024-09-30"
    cert = ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED")
    assert m.certificate_verify_error(cert)
    assert not m.certificate_verify_error(RuntimeError("other error"))

    m.validate_payload(
        "savant_csv",
        b"last_name,first_name,player_id,year,pa,k_percent,whiff_percent\nCole,Gerrit,543037,2024,95,25,30\n",
    )
    m.validate_payload("fangraphs_json", b'{"data":[{"PA":10}]}')
    m.validate_payload("mlb_json", b'{"stats":[],"copyright":"x"}')
    m.validate_payload("park_html", b"<html><body>Statcast Park Factors</body></html>")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        d = root / "data/normalized/mlb/historical_outcomes_030/run"
        d.mkdir(parents=True)
        out = d / "MLB_HISTORICAL_OUTCOMES.jsonl"
        out.write_text(json.dumps({"season_type":"POST"}) + "\n", encoding="utf-8")
        pointer = root / "data/normalized/mlb/CURRENT_HISTORICAL_OUTCOMES_030"
        pointer.write_text("data/normalized/mlb/historical_outcomes_030/run\n", encoding="utf-8")
        assert m.resolve_outcomes(root, None) == out

    print("PASS MLB postseason priors acquisition 0.4.0")


if __name__ == "__main__":
    main()

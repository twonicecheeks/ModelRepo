#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/nfl/build_omega_week2_gameday_overlay_0342.py"
spec = importlib.util.spec_from_file_location("omega0342", SCRIPT)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def row(status="PRELIMINARY_NO_AUTHORITATIVE_INACTIVE_OVERLAY", role="ROLE_ALIGNED", quote="EXECUTABLE_OFFER"):
    return {"operational_status": status, "role_state": role, "market_quote_classification": quote}


assert m.parse_game_teams("2026_02_DET_BUF") == ("DET", "BUF")
assert m.parse_pair("BUF|Terrel Bernard", "starter") == ("BUF", "Terrel Bernard")

role, status = m.classify(row(), final_inactives=False, inactive=False, starter_confirmed=False)
assert role == "ROLE_ALIGNED" and status == "PRELIMINARY_NO_AUTHORITATIVE_INACTIVE_OVERLAY"

role, status = m.classify(row(role="STARTER_CONFLICT_REVIEW"), final_inactives=False, inactive=False, starter_confirmed=True)
assert role == "STARTER_CONFLICT_RESOLVED_TEAM_DEPTH_CHART"
assert status == "PRELIMINARY_NO_AUTHORITATIVE_INACTIVE_OVERLAY_STARTER_CONFIRMED"

role, status = m.classify(row(role="STARTER_CONFLICT_REVIEW"), final_inactives=True, inactive=False, starter_confirmed=True)
assert status == "MARKET_ELIGIBLE_CONTROL_TRACK"

role, status = m.classify(row(), final_inactives=True, inactive=True, starter_confirmed=False)
assert status == "NO_ACTION_CONFIRMED_INACTIVE"

role, status = m.classify(row(quote="REFERENCE_ONLY_NON_EXECUTABLE"), final_inactives=True, inactive=False, starter_confirmed=False)
assert status == "REFERENCE_ONLY_NOT_EXECUTABLE"

role, status = m.classify(row(status="NO_ACTION_SETTLEMENT_UNRESOLVED"), final_inactives=True, inactive=False, starter_confirmed=False)
assert status == "NO_ACTION_SETTLEMENT_UNRESOLVED"

role, status = m.classify(row(role="REVIEW_BACKUP_CONFLICT"), final_inactives=True, inactive=False, starter_confirmed=False)
assert status == "QUARANTINED_BACKUP_CONFLICT"

role, status = m.classify(row(role="STARTER_CONFLICT_REVIEW"), final_inactives=True, inactive=False, starter_confirmed=False)
assert status == "REVIEW_STARTER_CONFLICT"

print("PASS OMEGA 0.34.2 game-day overlay contracts · final inactives required to lift gate · starter conflicts exact-source only")

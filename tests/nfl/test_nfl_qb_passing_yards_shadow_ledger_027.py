#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/models/nfl/game"))

import qb_passing_yards_market_025 as q25
import qb_passing_yards_shadow_ledger_027 as q27


def main() -> int:
    now = datetime(2026, 9, 17, 1, 0, 0, tzinfo=timezone.utc)
    fresh = q27.classify_freshness((now - timedelta(minutes=5)).isoformat(), now)
    aging = q27.classify_freshness((now - timedelta(minutes=30)).isoformat(), now)
    stale = q27.classify_freshness((now - timedelta(hours=2)).isoformat(), now)
    assert fresh["freshnessStatus"] == "FRESH_DIRECT"
    assert aging["freshnessStatus"] == "AGING_DIRECT"
    assert stale["freshnessStatus"] == "STALE_DIRECT"

    try:
        q27.parse_aware_timestamp("2026-09-16T20:00:00")
        raise AssertionError("naive timestamp should fail")
    except ValueError:
        pass

    try:
        q27.classify_freshness((now + timedelta(minutes=10)).isoformat(), now)
        raise AssertionError("future timestamp beyond tolerance should fail")
    except ValueError:
        pass

    target = {
        "game_id": "2026_02_CIN_HOU",
        "team": "CIN",
        "opponent": "HOU",
        "qb_gsis_id": "00-0036442",
        "qb_name": "Joe Burrow",
    }
    cap = q27.capture_payload(
        target=target,
        book="FanDuel",
        line=q25.assert_half_yard_line(249.5),
        over_price=q25.validate_american(-114),
        under_price=q25.validate_american(-114),
        captured_at="2026-09-16T20:43:48-04:00",
        verification_method="DIRECT_BOOK_APP",
        availability_status="EXECUTABLE_TO_USER",
    )
    assert cap["containsModelFields"] is False
    assert cap["referenceOnly"] is False
    assert cap["source"] == "DIRECT_SPORTSBOOK_CAPTURE"
    assert len(q27.sha256_object(cap)) == 64

    assert q27.shadow_status("POINT_POSITIVE_SHADOW", "FRESH_DIRECT", "EXECUTABLE_TO_USER") == "FRESH_POINT_POSITIVE_SHADOW"
    assert q27.shadow_status("ROBUST_POSITIVE_SHADOW", "AGING_DIRECT", "DISPLAYED_DIRECT") == "AGING_ROBUST_POSITIVE_SHADOW"
    assert q27.shadow_status("POINT_POSITIVE_SHADOW", "STALE_DIRECT", "EXECUTABLE_TO_USER") == "STALE_MARKET_REFERENCE"
    assert q27.shadow_status("POINT_POSITIVE_SHADOW", "FRESH_DIRECT", "UNKNOWN") == "DIRECT_AVAILABILITY_UNCONFIRMED"

    prev = dict(cap)
    prev["capturedAt"] = "2026-09-16T20:00:00-04:00"
    prev["line"] = 250.5
    prev["overAmerican"] = -110
    prev["underAmerican"] = -120
    mov = q27.movement_summary(cap, prev, q25)
    assert mov["hasPreviousSameBookCapture"] is True
    assert abs(mov["lineDelta"] + 1.0) < 1e-12
    assert mov["interpretation"] == "DESCRIPTIVE_MARKET_MOVEMENT_ONLY_NO_SHARP_MONEY_CLAIM"

    assert q27.clv_tracking_eligible("FRESH_DIRECT", "EXECUTABLE_TO_USER") is True
    assert q27.clv_tracking_eligible("AGING_DIRECT", "DISPLAYED_DIRECT") is True
    assert q27.clv_tracking_eligible("STALE_DIRECT", "EXECUTABLE_TO_USER") is False
    assert q27.clv_tracking_eligible("FRESH_DIRECT", "UNKNOWN") is False

    print("PASS NFL QB Model 0.2.7 shadow ledger contracts · explicit timestamp · immutable direct capture · freshness/CLV gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

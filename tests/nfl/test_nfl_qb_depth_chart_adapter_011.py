#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import sys
ROOT=Path(__file__).resolve().parents[2] if "__file__" in globals() else Path.cwd()
P=ROOT/"packages/providers/nflverse/src/qb_depth_chart_adapter_011.py"
sys.path.insert(0, str(P.parent))
spec=importlib.util.spec_from_file_location("m",P); m=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(m)
assert m.assert_development_only([2016,2024])==(2016,2024)
try: m.assert_development_only([2025])
except ValueError as e: assert "sealed 2025" in str(e)
else: raise AssertionError("2025 must remain sealed")
r=m.normalize_legacy_row({"season":2024,"club_code":"KAN","week":3,"game_type":"REG","depth_team":1,"gsis_id":"00-1","position":"QB","depth_position":"QB","full_name":"A QB"})
assert r and r["team"]=="KC" and r["depth_rank"]==1 and r["source_schema"]=="LEGACY_WEEKLY_PRE2025"
r2=m.normalize_modern_row({"dt":"2026-09-16T12:00:00Z","team":"KC","player_name":"A QB","gsis_id":"00-1","pos_abb":"QB","pos_rank":1})
assert r2 and r2["depth_rank"]==1 and r2["as_of"].startswith("2026-")
assert m.normalize_legacy_row({"position":"WR","depth_position":"WR","club_code":"KC"}) is None
print("PASS NFL QB State 0.1.1 depth adapter contracts · 2025 acquisition sealed")

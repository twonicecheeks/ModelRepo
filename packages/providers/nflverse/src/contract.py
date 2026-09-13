"""MODEL NFL Phase 1B nflverse source contract.

Pure standard-library helpers. Network acquisition and parquet normalization live in
separate modules. This module owns canonical source identity, historical split rules,
team-history normalization, and leakage/market-isolation policy.
"""
from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any

CONTRACT_VERSION = "0.2.0"
PHASE = "MODEL_2.9.0_NFL_PHASE1B_SNAPSHOT"
HOLDOUT_SEASON = 2025
PROSPECTIVE_SEASON = 2026
RESEARCH_ANALYSIS_SEASONS = tuple(range(2016, 2026))
HISTORY_SEED_SEASONS = (2015,)

GAME_ID_RE = re.compile(r"^(?P<season>\d{4})_(?P<week>\d{2})_(?P<away>[A-Z0-9]+)_(?P<home>[A-Z0-9]+)$")

FORBIDDEN_MARKET_FIELDS = frozenset({
    "away_moneyline", "home_moneyline", "spread_line",
    "away_spread_odds", "home_spread_odds", "total_line",
    "under_odds", "over_odds",
})
FORBIDDEN_CURRENT_GAME_OUTCOME_FIELDS = frozenset({
    "away_score", "home_score", "result", "total", "overtime",
})
FORBIDDEN_INDEPENDENT_FEATURE_FIELDS = FORBIDDEN_MARKET_FIELDS | FORBIDDEN_CURRENT_GAME_OUTCOME_FIELDS

# Provider-layer current-franchise history keys. Raw nflverse game_id is NEVER
# rewritten. These mappings mirror nflreadr's current-location convention for the
# modern aliases/relocations relevant to the research window.
TEAM_ABBR_CURRENT = {
    "ARZ": "ARI", "PHO": "ARI", "CRD": "ARI",
    "BLT": "BAL", "CLV": "CLE", "GNB": "GB",
    "JAC": "JAX", "KAN": "KC", "LVR": "LV", "OAK": "LV",
    "LAR": "LA", "STL": "LA", "SL": "LA",
    "SD": "LAC", "SDG": "LAC", "NWE": "NE", "NOR": "NO",
    "SFO": "SF", "TAM": "TB", "WSH": "WAS",
}


class SourceSpec:
    __slots__ = ("name", "required_for_phase1", "minimum_season", "url", "url_template", "status")

    def __init__(self, *, name: str, required_for_phase1: bool, minimum_season: int | None, url: str | None = None, url_template: str | None = None, status: str | None = None):
        self.name = name
        self.required_for_phase1 = required_for_phase1
        self.minimum_season = minimum_season
        self.url = url
        self.url_template = url_template
        self.status = status

    def url_for_season(self, season: int | None = None) -> str:
        if self.url:
            return self.url
        if not self.url_template:
            raise ValueError(f"source {self.name} has no URL contract")
        if season is None:
            raise ValueError(f"source {self.name} requires a season")
        if self.minimum_season is not None and season < self.minimum_season:
            raise ValueError(f"source {self.name} starts at {self.minimum_season}, not {season}")
        return self.url_template.format(season=int(season))


def contract_path() -> Path:
    return Path(__file__).resolve().parents[1] / "NFLVERSE_DATA_CONTRACT.json"


def load_contract() -> dict[str, Any]:
    data = json.loads(contract_path().read_text(encoding="utf-8"))
    if data.get("contractVersion") != CONTRACT_VERSION:
        raise ValueError("nflverse contract version drift")
    if data.get("projectPhase") != PHASE:
        raise ValueError("nflverse phase drift")
    return data


def source_specs() -> dict[str, SourceSpec]:
    raw = load_contract()["sources"]
    out: dict[str, SourceSpec] = {}
    for name, spec in raw.items():
        out[name] = SourceSpec(
            name=name,
            required_for_phase1=bool(spec.get("requiredForPhase1")),
            minimum_season=spec.get("minimumSeason"),
            url=spec.get("url"),
            url_template=spec.get("urlTemplate"),
            status=spec.get("status"),
        )
    return out


def normalize_team_abbr(value: str) -> str:
    team = str(value or "").strip().upper()
    if not team:
        raise ValueError("empty NFL team abbreviation")
    return TEAM_ABBR_CURRENT.get(team, team)


def canonical_game_id(season: int, week: int, away_team: str, home_team: str) -> str:
    """Build a raw nflverse-format game id without relocation normalization."""
    season = int(season)
    week = int(week)
    away = str(away_team).strip().upper()
    home = str(home_team).strip().upper()
    if not (1990 <= season <= 2100):
        raise ValueError("season out of range")
    if not (1 <= week <= 30):
        raise ValueError("week out of range")
    if not away or not home or away == home:
        raise ValueError("invalid NFL teams")
    return f"{season}_{week:02d}_{away}_{home}"


def parse_game_id(game_id: str) -> dict[str, Any]:
    m = GAME_ID_RE.match(str(game_id).strip())
    if not m:
        raise ValueError(f"invalid nflverse game_id: {game_id}")
    g = m.groupdict()
    return {"season": int(g["season"]), "week": int(g["week"]), "away_team": g["away"], "home_team": g["home"]}


def assert_independent_feature_names(names: list[str] | tuple[str, ...] | set[str]) -> None:
    lowered = {str(x).strip().lower() for x in names}
    bad = sorted(lowered & FORBIDDEN_INDEPENDENT_FEATURE_FIELDS)
    if bad:
        raise ValueError("forbidden market/outcome field(s) in independent features: " + ", ".join(bad))


def season_role(season: int) -> str:
    season = int(season)
    if season == HOLDOUT_SEASON:
        return "HOLDOUT_NEVER_FIT"
    if season == PROSPECTIVE_SEASON:
        return "PROSPECTIVE_ONLY"
    if season in HISTORY_SEED_SEASONS:
        return "HISTORY_SEED_ONLY"
    if season < HOLDOUT_SEASON:
        return "DEVELOPMENT_CANDIDATE"
    return "FUTURE"


if __name__ == "__main__":
    c = load_contract()
    print(f"PASS nflverse contract {c['contractVersion']} · {c['projectPhase']}")

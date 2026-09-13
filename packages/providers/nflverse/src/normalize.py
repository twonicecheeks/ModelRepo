"""Deterministic nflverse Phase 1B normalization and coverage audit."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import os
import shutil
from typing import Any, Iterable

try:
    import pyarrow.parquet as pq
except Exception as exc:  # pragma: no cover - environment guard
    pq = None
    _PYARROW_IMPORT_ERROR = exc
else:
    _PYARROW_IMPORT_ERROR = None

try:
    from .contract import (
        CONTRACT_VERSION,
        FORBIDDEN_INDEPENDENT_FEATURE_FIELDS,
        HOLDOUT_SEASON,
        HISTORY_SEED_SEASONS,
        RESEARCH_ANALYSIS_SEASONS,
        assert_independent_feature_names,
        normalize_team_abbr,
        parse_game_id,
        season_role,
    )
    from .snapshot import load_manifest, sha256_file
except ImportError:
    from contract import (
        CONTRACT_VERSION, FORBIDDEN_INDEPENDENT_FEATURE_FIELDS, HOLDOUT_SEASON,
        HISTORY_SEED_SEASONS, RESEARCH_ANALYSIS_SEASONS,
        assert_independent_feature_names, normalize_team_abbr, parse_game_id, season_role,
    )
    from snapshot import load_manifest, sha256_file

NORMALIZATION_SCHEMA_VERSION = "1.0.1"

PBP_REQUIRED_COLUMNS = (
    "game_id", "season", "week", "posteam", "defteam", "qb_dropback", "rush",
    "epa", "success", "cpoe", "sack", "yards_gained", "interception",
    "fumble_lost",
)
PBP_SEMANTIC_COLUMNS = ("no_play", "qb_kneel", "play_type")
PLAYER_COLUMNS = ("gsis_id", "display_name", "position", "position_group", "latest_team")
QB_ROSTER_COLUMNS = (
    "season", "week", "team", "gsis_id", "full_name", "position",
    "depth_chart_position", "status", "game_type",
)
GAME_IDENTITY_FIELDS = (
    "game_id", "season", "game_type", "week", "gameday", "weekday", "gametime",
    "source_away_team", "source_home_team", "away_team", "home_team",
    "location", "away_rest", "home_rest",
)
GAME_TARGET_FIELDS = ("game_id", "home_score", "away_score", "home_win", "home_margin")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _int(v: Any) -> int | None:
    x = _num(v)
    return None if x is None else int(x)


def _clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    fieldnames = list(fieldnames)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: "" if row.get(k) is None else row.get(k) for k in fieldnames})


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")


def _parquet_rows(path: Path, columns: Iterable[str]) -> list[dict[str, Any]]:
    if pq is None:
        raise RuntimeError(f"pyarrow is required for nflverse parquet normalization: {_PYARROW_IMPORT_ERROR}")
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    missing = [c for c in columns if c not in names]
    if missing:
        raise ValueError(f"{path.name} missing required parquet column(s): {', '.join(missing)}")
    return pf.read(columns=list(columns)).to_pylist()


def _pbp_schema_plan(names: Iterable[str]) -> dict[str, Any]:
    """Resolve nflverse PBP schema drift without weakening play filtering.

    `no_play` has not been stable as a standalone exported column across nflverse
    releases. `play_type` is the canonical semantic fallback: nflfastR defines
    `play_type == "no_play"` for nullified plays and `play_type == "qb_kneel"`
    for kneels. We fail closed unless each exclusion can be represented either by
    its native flag or by `play_type`.
    """
    names = set(names)
    missing = [c for c in PBP_REQUIRED_COLUMNS if c not in names]
    if missing:
        raise ValueError("missing required PBP column(s): " + ", ".join(missing))
    if "no_play" not in names and "play_type" not in names:
        raise ValueError("PBP schema cannot identify nullified plays: need no_play or play_type")
    if "qb_kneel" not in names and "play_type" not in names:
        raise ValueError("PBP schema cannot identify QB kneels: need qb_kneel or play_type")
    selected = list(PBP_REQUIRED_COLUMNS)
    selected.extend(c for c in PBP_SEMANTIC_COLUMNS if c in names and c not in selected)
    return {
        "columns": selected,
        "noPlaySource": "no_play" if "no_play" in names else "play_type",
        "qbKneelSource": "qb_kneel" if "qb_kneel" in names else "play_type",
    }


def _adapt_pbp_semantics(row: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    r = dict(row)
    play_type = _clean(r.get("play_type")).lower()
    if plan["noPlaySource"] == "play_type":
        r["no_play"] = 1 if play_type == "no_play" else 0
    if plan["qbKneelSource"] == "play_type":
        r["qb_kneel"] = 1 if play_type == "qb_kneel" else 0
    return r


def _pbp_parquet_rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if pq is None:
        raise RuntimeError(f"pyarrow is required for nflverse parquet normalization: {_PYARROW_IMPORT_ERROR}")
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    try:
        plan = _pbp_schema_plan(names)
    except ValueError as exc:
        raise ValueError(f"{path.name} {exc}") from exc
    rows = pf.read(columns=plan["columns"]).to_pylist()
    return [_adapt_pbp_semantics(r, plan) for r in rows], plan


def _load_core(root: Path):
    p = root / "packages/models/nfl/game/historical_feature_core.py"
    spec = importlib.util.spec_from_file_location("model_nfl_hist_core_phase1b", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _asset_index(manifest: dict[str, Any]) -> dict[tuple[str, int | None], dict[str, Any]]:
    out: dict[tuple[str, int | None], dict[str, Any]] = {}
    for a in manifest["assets"]:
        key = (a["source"], a.get("season"))
        if key in out:
            raise ValueError(f"duplicate snapshot asset: {key}")
        out[key] = a
    return out


def _normalize_schedule(root: Path, asset: dict[str, Any], seasons: set[int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    blob = root / asset["blobPath"]
    identities: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    market_columns_seen: set[str] = set()
    seen: set[str] = set()
    with blob.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("schedule CSV has no header")
        required = {"game_id", "season", "game_type", "week", "away_team", "home_team"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise ValueError("schedule missing required field(s): " + ", ".join(missing))
        market_columns_seen = set(reader.fieldnames) & {
            "away_moneyline", "home_moneyline", "spread_line", "away_spread_odds",
            "home_spread_odds", "total_line", "under_odds", "over_odds",
        }
        for raw in reader:
            season = _int(raw.get("season"))
            if season not in seasons:
                continue
            game_id = _clean(raw.get("game_id"))
            if not game_id or game_id in seen:
                raise ValueError(f"blank/duplicate schedule game_id: {game_id!r}")
            seen.add(game_id)
            parsed = parse_game_id(game_id)
            week = _int(raw.get("week"))
            source_away = _clean(raw.get("away_team")).upper()
            source_home = _clean(raw.get("home_team")).upper()
            if parsed["season"] != season or parsed["week"] != week:
                raise ValueError(f"game_id season/week mismatch: {game_id}")
            if parsed["away_team"] != source_away or parsed["home_team"] != source_home:
                raise ValueError(f"game_id team mismatch: {game_id} vs {source_away}@{source_home}")
            home_score, away_score = _num(raw.get("home_score")), _num(raw.get("away_score"))
            margin = None if home_score is None or away_score is None else home_score - away_score
            home_win = None if margin is None or margin == 0 else (1 if margin > 0 else 0)
            identities.append({
                "game_id": game_id,
                "season": season,
                "game_type": _clean(raw.get("game_type")),
                "week": week,
                "gameday": _clean(raw.get("gameday")),
                "weekday": _clean(raw.get("weekday")),
                "gametime": _clean(raw.get("gametime")),
                "source_away_team": source_away,
                "source_home_team": source_home,
                "away_team": normalize_team_abbr(source_away),
                "home_team": normalize_team_abbr(source_home),
                "location": _clean(raw.get("location")),
                "away_rest": _num(raw.get("away_rest")),
                "home_rest": _num(raw.get("home_rest")),
            })
            targets.append({
                "game_id": game_id,
                "home_score": home_score,
                "away_score": away_score,
                "home_win": home_win,
                "home_margin": margin,
            })
    identities.sort(key=lambda r: (r["season"], r["week"], r["gameday"], r["game_id"]))
    targets.sort(key=lambda r: r["game_id"])
    return identities, targets, {"sourceMarketColumnsObserved": sorted(market_columns_seen)}


def _normalize_players(root: Path, asset: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = _parquet_rows(root / asset["blobPath"], PLAYER_COLUMNS)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    missing_gsis = 0
    for r in raw:
        gsis = _clean(r.get("gsis_id"))
        if not gsis:
            missing_gsis += 1
            continue
        if gsis in seen:
            raise ValueError(f"players gsis_id primary-key duplicate: {gsis}")
        seen.add(gsis)
        latest = _clean(r.get("latest_team"))
        rows.append({
            "gsis_id": gsis,
            "display_name": _clean(r.get("display_name")),
            "position": _clean(r.get("position")),
            "position_group": _clean(r.get("position_group")),
            "latest_team": normalize_team_abbr(latest) if latest else "",
        })
    rows.sort(key=lambda r: r["gsis_id"])
    return rows, {"rawRows": len(raw), "usablePrimaryKeyRows": len(rows), "missingGsisRows": missing_gsis}


def _normalize_qb_rosters(root: Path, assets: dict[tuple[str, int | None], dict[str, Any]], seasons: list[int], player_ids: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    missing_gsis = 0
    unresolved = 0
    for season in seasons:
        raw = _parquet_rows(root / assets[("weekly_rosters", season)]["blobPath"], QB_ROSTER_COLUMNS)
        for r in raw:
            pos = _clean(r.get("position")).upper()
            dcp = _clean(r.get("depth_chart_position")).upper()
            if pos != "QB" and dcp != "QB":
                continue
            gsis = _clean(r.get("gsis_id"))
            if not gsis:
                missing_gsis += 1
            elif gsis not in player_ids:
                unresolved += 1
            team_raw = _clean(r.get("team")).upper()
            row = {
                "season": _int(r.get("season")),
                "week": _int(r.get("week")),
                "source_team": team_raw,
                "team": normalize_team_abbr(team_raw),
                "gsis_id": gsis,
                "full_name": _clean(r.get("full_name")),
                "position": pos,
                "depth_chart_position": dcp,
                "status": _clean(r.get("status")),
                "game_type": _clean(r.get("game_type")),
            }
            key = tuple(row[k] for k in ("season", "week", "team", "gsis_id", "full_name", "status", "game_type"))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    rows.sort(key=lambda r: (r["season"] or 0, r["week"] or 0, r["team"], r["gsis_id"], r["full_name"]))
    return rows, {
        "qbRosterRows": len(rows),
        "missingGsisRows": missing_gsis,
        "gsisNotResolvedInPlayers": unresolved,
        "resolvedGsisPct": round(100.0 * (len(rows) - missing_gsis - unresolved) / len(rows), 4) if rows else None,
    }


def _normalize_team_metrics(root: Path, assets: dict[tuple[str, int | None], dict[str, Any]], seasons: list[int], core) -> tuple[list[dict[str, Any]], dict[int, int]]:
    out: list[dict[str, Any]] = []
    rows_by_season: dict[int, int] = {}
    for season in seasons:
        pbp_path = root / assets[("play_by_play", season)]["blobPath"]
        raw, schema_plan = _pbp_parquet_rows(pbp_path)
        print(
            f"PASS PBP schema {season}: no_play={schema_plan['noPlaySource']} · "
            f"qb_kneel={schema_plan['qbKneelSource']}"
        )
        for r in raw:
            if r.get("posteam"):
                r["posteam"] = normalize_team_abbr(r["posteam"])
            if r.get("defteam"):
                r["defteam"] = normalize_team_abbr(r["defteam"])
        agg = core.aggregate_pbp_to_team_games(raw)
        for r in agg:
            r["team"] = normalize_team_abbr(r["team"])
            if r.get("opponent"):
                r["opponent"] = normalize_team_abbr(r["opponent"])
        agg.sort(key=lambda r: (r["season"], r["week"], r["game_id"], r["team"]))
        rows_by_season[season] = len(agg)
        out.extend(agg)
    out.sort(key=lambda r: (r["season"], r["week"], r["game_id"], r["team"]))
    return out, rows_by_season


def _feature_rows(core, identities: list[dict[str, Any]], targets: list[dict[str, Any]], team_metrics: list[dict[str, Any]], analysis_seasons: set[int]) -> list[dict[str, Any]]:
    targets_by_game = {r["game_id"]: r for r in targets}
    games: list[dict[str, Any]] = []
    for g in identities:
        t = targets_by_game[g["game_id"]]
        games.append({**g, "home_score": t["home_score"], "away_score": t["away_score"]})
    built = core.build_pregame_feature_rows(games, team_metrics)
    built = [r for r in built if r["season"] in analysis_seasons]
    out: list[dict[str, Any]] = []
    for r in built:
        assert_independent_feature_names(set(r["features"]))
        row = {
            "game_id": r["game_id"], "season": r["season"], "week": r["week"],
            "game_type": r["game_type"], "gameday": r["gameday"],
            "away_team": r["away_team"], "home_team": r["home_team"],
            "feature_state": r["feature_state"], "split_state": r["split_state"],
        }
        row.update(r["features"])
        if set(row) & FORBIDDEN_INDEPENDENT_FEATURE_FIELDS:
            raise ValueError("forbidden market/outcome field leaked into normalized feature row")
        out.append(row)
    out.sort(key=lambda r: (r["season"], r["week"], r["gameday"], r["game_id"]))
    return out


def _coverage_audit(
    identities: list[dict[str, Any]], targets: list[dict[str, Any]], team_metrics: list[dict[str, Any]],
    features: list[dict[str, Any]], schedule_meta: dict[str, Any], players_meta: dict[str, Any],
    qb_meta: dict[str, Any], rows_by_season: dict[int, int], analysis_seasons: list[int], seed_seasons: list[int],
) -> dict[str, Any]:
    targets_by_game = {r["game_id"]: r for r in targets}
    tm_counts = Counter(r["game_id"] for r in team_metrics)
    feature_names = sorted(set().union(*(set(r) for r in features)) - {
        "game_id", "season", "week", "game_type", "gameday", "away_team", "home_team", "feature_state", "split_state"
    }) if features else []
    missing_overall = {}
    for name in feature_names:
        missing = sum(1 for r in features if r.get(name) in (None, ""))
        missing_overall[name] = {
            "missing": missing,
            "rows": len(features),
            "missingPct": round(100.0 * missing / len(features), 4) if features else None,
        }
    by_season: dict[str, Any] = {}
    for season in analysis_seasons:
        games = [g for g in identities if g["season"] == season]
        fs = [r for r in features if r["season"] == season]
        labels = [targets_by_game[g["game_id"]] for g in games]
        complete_labels = sum(1 for t in labels if t["home_win"] is not None)
        two_sided = sum(1 for g in games if tm_counts[g["game_id"]] == 2)
        by_season[str(season)] = {
            "games": len(games),
            "regularSeasonGames": sum(1 for g in games if g["game_type"] == "REG"),
            "featureRows": len(fs),
            "completeLabels": complete_labels,
            "gamesWithTwoTeamMetricRows": two_sided,
            "splitRole": season_role(season),
        }
    top_missing = sorted(
        ({"field": k, **v} for k, v in missing_overall.items()),
        key=lambda x: (-float(x["missingPct"] or 0), x["field"]),
    )[:20]
    week1 = [r for r in features if r["week"] == 1]
    prior_fields = [n for n in feature_names if "prior_season_" in n]
    prior_missing = sum(1 for r in week1 for n in prior_fields if r.get(n) in (None, ""))
    prior_cells = len(week1) * len(prior_fields)
    return {
        "auditVersion": "1.0.1",
        "generatedAt": _utc_now(),
        "analysisSeasons": analysis_seasons,
        "historySeedSeasons": seed_seasons,
        "trainingWindowFrozen": False,
        "holdoutSeason": HOLDOUT_SEASON,
        "marketIsolation": {
            **schedule_meta,
            "normalizedFeatureMarketFieldsPresent": sorted(set(feature_names) & set(FORBIDDEN_INDEPENDENT_FEATURE_FIELDS)),
            "pass": not (set(feature_names) & set(FORBIDDEN_INDEPENDENT_FEATURE_FIELDS)),
        },
        "players": players_meta,
        "qbRosterIdentity": qb_meta,
        "pbpTeamMetricRowsBySeason": {str(k): v for k, v in sorted(rows_by_season.items())},
        "bySeason": by_season,
        "featureFieldCount": len(feature_names),
        "featureRows": len(features),
        "week1PriorCoverage": {
            "week1Rows": len(week1),
            "priorFieldsPerRow": len(prior_fields),
            "nonMissingPct": round(100.0 * (prior_cells - prior_missing) / prior_cells, 4) if prior_cells else None,
        },
        "topMissingFeatureFields": top_missing,
        "allFeatureMissingness": missing_overall,
    }


def _audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# MODEL NFL 2.9.0 Phase 1B — nflverse Coverage Audit", "",
        f"Generated: {audit['generatedAt']}", "",
        "This is a research coverage report, not a fitted-model report. The training window remains **NOT FROZEN**.", "",
        "## Integrity", "",
        f"- Market isolation: **{'PASS' if audit['marketIsolation']['pass'] else 'FAIL'}**",
        f"- Holdout: **{audit['holdoutSeason']} — NEVER FIT**",
        f"- Week 1 prior-field non-missing coverage: **{audit['week1PriorCoverage']['nonMissingPct']}%**",
        f"- QB roster gsis_id resolution into players: **{audit['qbRosterIdentity']['resolvedGsisPct']}%**",
        "", "## Season coverage", "",
        "| Season | Role | Games | REG | Feature rows | Complete labels | 2-side PBP metrics |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for season, r in audit["bySeason"].items():
        lines.append(f"| {season} | {r['splitRole']} | {r['games']} | {r['regularSeasonGames']} | {r['featureRows']} | {r['completeLabels']} | {r['gamesWithTwoTeamMetricRows']} |")
    lines += ["", "## Highest feature missingness", ""]
    for r in audit["topMissingFeatureFields"][:12]:
        lines.append(f"- `{r['field']}`: {r['missingPct']}% ({r['missing']}/{r['rows']})")
    lines += ["", "## Interpretation", "",
              "Do not fit coefficients from this report alone. Review missingness, relocation continuity, label exceptions, and holdout isolation first.", ""]
    return "\n".join(lines)


def normalize_snapshot(root: Path, manifest_path: Path) -> Path:
    root = Path(root).resolve()
    manifest = load_manifest(manifest_path, root=root)
    analysis = [int(x) for x in manifest["analysisSeasons"]]
    seeds = [int(x) for x in manifest["historySeedSeasons"]]
    seasons = sorted(set(analysis) | set(seeds))
    assets = _asset_index(manifest)
    required = [("schedules", None), ("players", None)] + [
        (kind, season) for season in seasons for kind in ("weekly_rosters", "play_by_play")
    ]
    missing = [x for x in required if x not in assets]
    if missing:
        raise ValueError(f"snapshot missing required asset(s): {missing}")

    core = _load_core(root)
    identities_all, targets_all, schedule_meta = _normalize_schedule(root, assets[("schedules", None)], set(seasons))
    identities = [r for r in identities_all if r["season"] in set(analysis)]
    targets = [r for r in targets_all if r["game_id"] in {g["game_id"] for g in identities}]
    players, players_meta = _normalize_players(root, assets[("players", None)])
    qbs, qb_meta = _normalize_qb_rosters(root, assets, seasons, {r["gsis_id"] for r in players})
    team_metrics, rows_by_season = _normalize_team_metrics(root, assets, seasons, core)
    # Feature builder needs seed-season schedule rows only to create feature rows for
    # them, but we immediately filter output to analysis seasons. Their team metrics
    # are what provide the explicit prior-season warmup for 2016.
    all_targets_by_game = {r["game_id"]: r for r in targets_all}
    feature_games = [g for g in identities_all if g["season"] in set(seasons)]
    feature_targets = [all_targets_by_game[g["game_id"]] for g in feature_games]
    features = _feature_rows(core, feature_games, feature_targets, team_metrics, set(analysis))

    audit = _coverage_audit(
        identities, targets, team_metrics, features, schedule_meta, players_meta, qb_meta,
        rows_by_season, analysis, seeds,
    )
    if not audit["marketIsolation"]["pass"]:
        raise RuntimeError("market isolation audit failed")

    snapshot_id = manifest["snapshotId"]
    out_root = root / "data/normalized/nfl/phase1" / snapshot_id
    staging = out_root.parent / ("." + snapshot_id + ".staging")
    if out_root.exists() or staging.exists():
        raise FileExistsError(f"normalized snapshot already exists: {snapshot_id}")
    staging.mkdir(parents=True)
    try:
        _write_csv(staging / "game_identity.csv", identities, GAME_IDENTITY_FIELDS)
        _write_csv(staging / "game_targets.csv", targets, GAME_TARGET_FIELDS)
        player_fields = ("gsis_id", "display_name", "position", "position_group", "latest_team")
        _write_csv(staging / "player_identity.csv", players, player_fields)
        qb_fields = ("season", "week", "source_team", "team", "gsis_id", "full_name", "position", "depth_chart_position", "status", "game_type")
        _write_csv(staging / "qb_roster_weekly.csv", qbs, qb_fields)
        tm_fields = ("game_id", "season", "week", "team", "opponent") + tuple(core.DEFAULT_TEAM_METRICS)
        _write_csv(staging / "team_game_metrics.csv", team_metrics, tm_fields)
        feature_meta = ("game_id", "season", "week", "game_type", "gameday", "away_team", "home_team", "feature_state", "split_state")
        feature_names = sorted(set().union(*(set(r) for r in features)) - set(feature_meta)) if features else []
        _write_csv(staging / "pregame_features.csv", features, feature_meta + tuple(feature_names))
        _write_jsonl(staging / "pregame_features.jsonl", features)
        (staging / "NFLVERSE_COVERAGE_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        (staging / "NFLVERSE_COVERAGE_AUDIT.md").write_text(_audit_markdown(audit), encoding="utf-8")

        output_files = []
        for p in sorted(staging.iterdir()):
            if p.is_file():
                output_files.append({"filename": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size})
        norm_manifest = {
            "normalizationSchemaVersion": NORMALIZATION_SCHEMA_VERSION,
            "createdAt": _utc_now(),
            "sourceSnapshotId": snapshot_id,
            "sourceManifest": str(Path(manifest_path).resolve().relative_to(root)),
            "contractVersion": CONTRACT_VERSION,
            "analysisSeasons": analysis,
            "historySeedSeasons": seeds,
            "trainingWindowFrozen": False,
            "holdoutSeason": HOLDOUT_SEASON,
            "oddsPapiRequests": 0,
            "outputFiles": output_files,
        }
        (staging / "NORMALIZATION_MANIFEST.json").write_text(json.dumps(norm_manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, out_root)
        ptr_tmp = root / "data/normalized/nfl/.CURRENT_PHASE1_SNAPSHOT.tmp"
        ptr = root / "data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"
        ptr.parent.mkdir(parents=True, exist_ok=True)
        ptr_tmp.write_text(snapshot_id + "\n", encoding="utf-8")
        os.replace(ptr_tmp, ptr)
        return out_root / "NFLVERSE_COVERAGE_AUDIT.md"
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

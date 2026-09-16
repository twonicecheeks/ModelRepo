#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import importlib.util
import json
import os
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def load_module(root: Path):
    path = root / "packages/models/nfl/game/state_component_persistence_research.py"
    spec = importlib.util.spec_from_file_location("nfl_state_component_persistence_013", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def load_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def pct(v):
    return "NA" if v is None else f"{100.0 * v:.2f}%"


def pp(v):
    return "NA" if v is None else f"{100.0 * v:+.2f} pp"


def main() -> int:
    ap = argparse.ArgumentParser(description="Development-only State Intelligence component persistence audit")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    ap.add_argument("--min-prior-third-downs", type=int, default=20)
    ap.add_argument("--min-prior-exposed-dropbacks", type=int, default=20)
    ap.add_argument("--bootstrap-reps", type=int, default=1000)
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model = load_module(root)
    seasons = list(model.assert_development_only(parse_seasons(args.seasons)))

    pointer = root / "data/normalized/nfl/CURRENT_NFL_STATE_INTELLIGENCE"
    if not pointer.exists():
        raise FileNotFoundError("CURRENT_NFL_STATE_INTELLIGENCE missing; build State Intelligence 0.1.0 first")
    state_dir = root / pointer.read_text(encoding="utf-8").strip()
    audit_path = state_dir / "NFL_STATE_INTELLIGENCE_AUDIT.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("marketDependency") is not False or audit.get("frozenOmegaMutation") is not False:
        raise ValueError("state-intelligence audit boundary drift")
    if audit.get("trainingOrRefitPerformed") is not False:
        raise ValueError("state-intelligence source unexpectedly reports training/refit")

    rows: list[dict] = []
    rows_by_season: dict[int, int] = {}
    for season in seasons:
        path = state_dir / f"NFL_STATE_INTELLIGENCE_SNAPS_{season}.jsonl"
        if not path.exists():
            raise FileNotFoundError(path)
        season_rows = load_jsonl(path)
        rows_by_season[season] = len(season_rows)
        rows.extend(season_rows)
        print(f"PASS {season} · snaps {len(season_rows):,}")

    records = model.build_persistence_records(
        rows,
        min_prior_third_downs=args.min_prior_third_downs,
        min_prior_exposed_dropbacks=args.min_prior_exposed_dropbacks,
    )
    if not records["offense"] or not records["defense"]:
        raise ValueError("component persistence audit produced no usable pregame records")

    summary = model.summarize_persistence(records)
    bootstrap = model.cluster_bootstrap_persistence(records, reps=args.bootstrap_reps)

    off_season = [
        v["offense"]["high_minus_low"]
        for _s, v in sorted(summary["by_season"].items())
        if v["offense"]["high_minus_low"] is not None
    ]
    def_season = [
        v["defense"]["high_minus_low"]
        for _s, v in sorted(summary["by_season"].items())
        if v["defense"]["high_minus_low"] is not None
    ]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/state_intelligence_013" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    result = {
        "version": model.VERSION,
        "lineage": model.LINEAGE,
        "createdAt": utc_now(),
        "runId": run_id,
        "sourceSnapshotId": audit.get("sourceSnapshotId"),
        "sourceStateDirectory": str(state_dir.relative_to(root)),
        "developmentSeasons": seasons,
        "sealedHoldoutSeason": 2025,
        "prospectiveSeason": 2026,
        "holdoutOpened": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "trainingOrRefitPerformed": False,
        "minimumPriorThirdDowns": args.min_prior_third_downs,
        "minimumPriorExposedDropbacks": args.min_prior_exposed_dropbacks,
        "sourceRowsBySeason": rows_by_season,
        "offensePregameRecords": len(records["offense"]),
        "defensePregameRecords": len(records["defense"]),
        "summary": summary,
        "clusterBootstrap": bootstrap,
        "seasonDirection": {
            "offensePositivePersistenceSeasons": sum(1 for x in off_season if x > 0),
            "offenseSeasonsEvaluated": len(off_season),
            "defensePositivePersistenceSeasons": sum(1 for x in def_season if x > 0),
            "defenseSeasonsEvaluated": len(def_season),
        },
    }
    json_path = out_dir / "NFL_STATE_COMPONENT_PERSISTENCE_AUDIT.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    off = summary["offense"]["groups"]
    deff = summary["defense"]["groups"]
    off_ci = bootstrap["offense_exposure_high_minus_low"]
    def_ci = bootstrap["defense_exposed_sack_high_minus_low"]

    lines = [
        "NFL STATE INTELLIGENCE 0.1.3 — STATE-COMPONENT PERSISTENCE AUDIT",
        "",
        f"Source snapshot: {audit.get('sourceSnapshotId')}",
        f"Development seasons: {seasons[0]}-{seasons[-1]}",
        "2025 holdout: SEALED / NOT READ",
        "2026 prospective: NOT READ",
        f"Offense pregame records: {len(records['offense']):,}",
        f"Defense pregame records: {len(records['defense']):,}",
        f"Minimum prior offense third downs: {args.min_prior_third_downs}",
        f"Minimum prior defense exposed dropbacks: {args.min_prior_exposed_dropbacks}",
        f"Game-cluster bootstrap reps: {args.bootstrap_reps:,}",
        "",
        "OFFENSE: lagged exposure propensity -> next-game environment",
        f"  LOW prior-exposure tier: next-game exposure {pct(off['LOW']['exposure_rate'])} · "
        f"3D sack {pct(off['LOW']['third_down_sack_rate'])} · conversion {pct(off['LOW']['third_down_conversion_rate'])} "
        f"(games={off['LOW']['games']:,})",
        f"  MID prior-exposure tier: next-game exposure {pct(off['MID']['exposure_rate'])} · "
        f"3D sack {pct(off['MID']['third_down_sack_rate'])} · conversion {pct(off['MID']['third_down_conversion_rate'])} "
        f"(games={off['MID']['games']:,})",
        f"  HIGH prior-exposure tier: next-game exposure {pct(off['HIGH']['exposure_rate'])} · "
        f"3D sack {pct(off['HIGH']['third_down_sack_rate'])} · conversion {pct(off['HIGH']['third_down_conversion_rate'])} "
        f"(games={off['HIGH']['games']:,})",
        f"  HIGH minus LOW next-game exposure: {pp(off_ci['observed'])} "
        f"[{pp(off_ci['ci95_low'])}, {pp(off_ci['ci95_high'])}]",
        f"  Season direction: positive persistence in {result['seasonDirection']['offensePositivePersistenceSeasons']}/"
        f"{result['seasonDirection']['offenseSeasonsEvaluated']} development seasons",
        "",
        "DEFENSE: lagged exposed-state sack conversion -> next-game exposed sack rate",
        f"  LOW prior exposed-sack tier: next-game exposed sack {pct(deff['LOW']['exposed_sack_rate'])} "
        f"(games={deff['LOW']['games']:,}, exposed dropbacks={deff['LOW']['exposed_dropbacks']:,})",
        f"  MID prior exposed-sack tier: next-game exposed sack {pct(deff['MID']['exposed_sack_rate'])} "
        f"(games={deff['MID']['games']:,}, exposed dropbacks={deff['MID']['exposed_dropbacks']:,})",
        f"  HIGH prior exposed-sack tier: next-game exposed sack {pct(deff['HIGH']['exposed_sack_rate'])} "
        f"(games={deff['HIGH']['games']:,}, exposed dropbacks={deff['HIGH']['exposed_dropbacks']:,})",
        f"  HIGH minus LOW next-game exposed sack rate: {pp(def_ci['observed'])} "
        f"[{pp(def_ci['ci95_low'])}, {pp(def_ci['ci95_high'])}]",
        f"  Season direction: positive persistence in {result['seasonDirection']['defensePositivePersistenceSeasons']}/"
        f"{result['seasonDirection']['defenseSeasonsEvaluated']} development seasons",
        "",
        "Interpretation guard: this tests whether the two state components are stable enough to be pregame primitives.",
        "It does not fit a betting model and does not promote a feature by itself.",
        "",
        f"JSON: {json_path}",
    ]
    txt_path = out_dir / "NFL_STATE_COMPONENT_PERSISTENCE_AUDIT.txt"
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    current = root / "data/models/nfl/CURRENT_STATE_INTELLIGENCE_013"
    current.parent.mkdir(parents=True, exist_ok=True)
    tmp = current.with_name("." + current.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
    os.replace(tmp, current)

    print()
    print(txt_path.read_text(encoding="utf-8"))
    print("PASS development-only component persistence audit · 2025 holdout sealed · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

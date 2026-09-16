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
    path = root / "packages/models/nfl/game/state_mechanism_research.py"
    spec = importlib.util.spec_from_file_location("nfl_state_mechanism_011", path)
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
    ap = argparse.ArgumentParser(description="Development-only M04/M05/M19/M30 early-down mechanism diagnostic")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
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

    audits_by_season = {int(x["season"]): x for x in audit.get("seasons", [])}
    required_optional = {"drive", "success", "first_down"}
    for season in seasons:
        if season not in audits_by_season:
            raise ValueError(f"requested development season absent from state snapshot: {season}")
        available = set(audits_by_season[season].get("optionalColumnsAvailable", []))
        missing = sorted(required_optional - available)
        if missing:
            raise ValueError(f"season {season} cannot support M04 mechanism audit; missing columns: {', '.join(missing)}")

    records: list[dict] = []
    rows_by_season: dict[int, int] = {}
    series_by_season: dict[int, int] = {}
    for season in seasons:
        path = state_dir / f"NFL_STATE_INTELLIGENCE_SNAPS_{season}.jsonl"
        if not path.exists():
            raise FileNotFoundError(path)
        rows = load_jsonl(path)
        rows_by_season[season] = len(rows)
        season_records = model.build_series_records(rows)
        series_by_season[season] = len(season_records)
        records.extend(season_records)
        print(f"PASS {season} · snaps {len(rows):,} · first-down series {len(season_records):,}")

    if not records:
        raise ValueError("no eligible first-down series produced")

    summary = model.summarize_records(records)
    bootstrap = model.cluster_bootstrap_differences(records, reps=args.bootstrap_reps)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/state_intelligence_011" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    result = {
        "version": model.VERSION,
        "lineage": model.LINEAGE,
        "createdAt": utc_now(),
        "runId": run_id,
        "sourceStateDirectory": str(state_dir.relative_to(root)),
        "sourceStateAudit": str(audit_path.relative_to(root)),
        "sourceSnapshotId": audit.get("sourceSnapshotId"),
        "developmentSeasons": seasons,
        "sealedHoldoutSeason": 2025,
        "prospectiveSeason": 2026,
        "holdoutOpened": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "trainingOrRefitPerformed": False,
        "mechanism": "M04/M05/M19/M30 first-down result -> later down/distance -> structural pressure exposure -> conversion environment",
        "filters": {
            "competitiveState": "COMPETITIVE only",
            "footballTendencyEligible": True,
            "scrimmageIntents": sorted(model.SCRIMMAGE_INTENTS),
            "firstDownOutcome": "nflverse success flag on first-down series opener",
        },
        "sourceRowsBySeason": rows_by_season,
        "eligibleSeriesBySeason": series_by_season,
        "eligibleSeriesTotal": len(records),
        "summary": summary,
        "clusterBootstrap": bootstrap,
    }
    json_path = out_dir / "NFL_STATE_M04_MECHANISM_AUDIT.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    fail = summary["overall"]["failure"]
    succ = summary["overall"]["success"]
    diffs = bootstrap["failure_minus_success"]
    lines = [
        "NFL STATE INTELLIGENCE 0.1.1 — EARLY-DOWN MECHANISM AUDIT",
        "",
        f"Source snapshot: {audit.get('sourceSnapshotId')}",
        f"Development seasons: {seasons[0]}-{seasons[-1]}",
        "2025 holdout: SEALED / NOT READ",
        "2026 prospective: NOT READ",
        f"Eligible first-down series: {len(records):,}",
        f"Game-cluster bootstrap reps: {args.bootstrap_reps:,}",
        "",
        "Observed conditional rates",
        f"  2nd-and-long+ after failed first down: {pct(fail['second_long_plus_rate'])}",
        f"  2nd-and-long+ after successful first down: {pct(succ['second_long_plus_rate'])}",
        f"  Reach 3rd down after failed first down: {pct(fail['reach_third_rate'])}",
        f"  Reach 3rd down after successful first down: {pct(succ['reach_third_rate'])}",
        f"  3rd-down elevated/high exposure after failed first down: {pct(fail['third_elevated_plus_rate'])}",
        f"  3rd-down elevated/high exposure after successful first down: {pct(succ['third_elevated_plus_rate'])}",
        f"  3rd-down sack rate on dropbacks after failed first down: {pct(fail['third_dropback_sack_rate'])}",
        f"  3rd-down sack rate on dropbacks after successful first down: {pct(succ['third_dropback_sack_rate'])}",
        f"  3rd-down conversion after failed first down: {pct(fail['third_conversion_rate'])}",
        f"  3rd-down conversion after successful first down: {pct(succ['third_conversion_rate'])}",
        f"  Series first-down conversion after failed first down: {pct(fail['series_first_down_rate'])}",
        f"  Series first-down conversion after successful first down: {pct(succ['series_first_down_rate'])}",
        "",
        "Failure minus success · game-cluster 95% CI",
    ]
    for metric, values in diffs.items():
        lines.append(
            f"  {metric}: {pp(values['observed'])} "
            f"[{pp(values['ci95_low'])}, {pp(values['ci95_high'])}]"
        )
    lines += [
        "",
        "Interpretation guard: this is a coefficient-free historical mechanism diagnostic, not a betting model.",
        "No feature is promoted by this run alone; stability, opponent interaction, and out-of-sample challenger testing remain required.",
        "",
        f"JSON: {json_path}",
    ]
    txt_path = out_dir / "NFL_STATE_M04_MECHANISM_AUDIT.txt"
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    current = root / "data/models/nfl/CURRENT_STATE_INTELLIGENCE_011"
    current.parent.mkdir(parents=True, exist_ok=True)
    tmp = current.with_name("." + current.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
    os.replace(tmp, current)

    print()
    print(txt_path.read_text(encoding="utf-8"))
    print("PASS development-only M04 mechanism audit · 2025 holdout sealed · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

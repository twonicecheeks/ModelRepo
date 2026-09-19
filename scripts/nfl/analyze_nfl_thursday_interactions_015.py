#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import sys
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


def load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def pct(v):
    return "NA" if v is None else f"{100.0*float(v):.2f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description="Development-only Thursday interaction research audit")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    sys.path.insert(0, str(model_dir))
    import thursday_interaction_research_015 as th

    seasons = list(th.assert_development_only(parse_seasons(args.seasons)))
    ptr = root / "data/normalized/nfl/CURRENT_NFL_STATE_INTELLIGENCE"
    if not ptr.exists():
        raise FileNotFoundError("CURRENT_NFL_STATE_INTELLIGENCE missing; build State Intelligence first")
    state_dir = root / ptr.read_text(encoding="utf-8").strip()
    audit_path = state_dir / "NFL_STATE_INTELLIGENCE_AUDIT.json"
    if not audit_path.exists():
        raise FileNotFoundError(audit_path)
    state_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if state_audit.get("marketDependency") is not False or state_audit.get("frozenOmegaMutation") is not False:
        raise ValueError("State Intelligence integrity boundary drift")

    rows: list[dict] = []
    per_season: list[dict] = []
    for season in seasons:
        p = state_dir / f"NFL_STATE_INTELLIGENCE_SNAPS_{season}.jsonl"
        if not p.exists():
            raise FileNotFoundError(p)
        sr = load_jsonl(p)
        rows.extend(sr)
        ssum = th.summarize_game_interactions(sr)
        per_season.append({
            "season": season,
            "snapRows": len(sr),
            "games": ssum["games"],
            "responseDriveScoreRate": ssum["response_drives"]["score_rate"],
            "lateDownScrambleConversions": ssum["qb_scramble_drive_survival"]["late_down_scramble_conversions"],
            "explosivePlays20Plus": ssum["explosive_concentration"]["explosive_plays_20_plus"],
            "nullifiedImpactEvents": len(ssum["nullified_impact_events"]),
            "highLeveragePenaltyCandidates": ssum["penalty_leverage"]["high_leverage_candidates"],
        })
        print(f"PASS {season} · snaps {len(sr):,} · games {ssum['games']:,}")

    summary = th.summarize_game_interactions(rows)
    game_team = th.build_historical_game_team_records(rows)

    paired = [
        r for r in game_team
        if r.get("early_down_run_success_rate") is not None and r.get("high_exposure_dropback_rate") is not None
    ]
    if paired:
        hi = [r for r in paired if float(r["early_down_run_success_rate"]) >= 0.5]
        lo = [r for r in paired if float(r["early_down_run_success_rate"]) < 0.5]
        hi_exp = sum(float(r["high_exposure_dropback_rate"]) for r in hi) / len(hi) if hi else None
        lo_exp = sum(float(r["high_exposure_dropback_rate"]) for r in lo) / len(lo) if lo else None
    else:
        hi = lo = []
        hi_exp = lo_exp = None

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/state_intelligence_015" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    result = {
        "version": th.VERSION,
        "lineage": th.LINEAGE,
        "createdAt": utc_now(),
        "runId": run_id,
        "sourceStateDirectory": str(state_dir.relative_to(root)),
        "sourceSnapshotId": state_audit.get("sourceSnapshotId"),
        "developmentSeasons": seasons,
        "sealedHoldoutSeason": 2025,
        "prospectiveSeason": 2026,
        "holdoutOpened": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "trainingOrRefitPerformed": False,
        "discoverySource": "DET@BUF 2026-09-17 drive ledger + prior DEN@KC state ledger; historical validation uses only 2016-2024 by default",
        "summary": summary,
        "gameTeamRows": len(game_team),
        "perSeason": per_season,
        "earlyDownRunVsExposureDiagnostic": {
            "n": len(paired),
            "earlyRunSuccessGe50N": len(hi),
            "earlyRunSuccessLt50N": len(lo),
            "highExposureDropbackRateWhenEarlyRunSuccessGe50": hi_exp,
            "highExposureDropbackRateWhenEarlyRunSuccessLt50": lo_exp,
            "differenceGe50MinusLt50": None if hi_exp is None or lo_exp is None else hi_exp - lo_exp,
            "interpretation": "Descriptive only; tests M22/M24/M34 that offensive structure/run success changes later pressure exposure. No coefficient is fit.",
        },
        "dataGaps": th.DATA_GAPS,
        "nextGate": "REVIEW_HISTORICAL_DIAGNOSTICS_THEN_BUILD_PAIRED_CHALLENGERS_ONLY_FOR_SUPPORTED_FEATURES",
    }
    json_path = out_dir / "NFL_THURSDAY_INTERACTION_RESEARCH.json"
    json_path.write_text(json.dumps(result, indent=2) + "
", encoding="utf-8")

    exp = summary["explosive_concentration"]
    response = summary["response_drives"]
    scramble = summary["qb_scramble_drive_survival"]
    penalty = summary["penalty_leverage"]
    cx = summary["containment_x_explosive_suppression_proxy"]
    lines = [
        "NFL STATE INTELLIGENCE 0.1.5 — THURSDAY INTERACTION RESEARCH",
        "",
        f"Source snapshot: {state_audit.get('sourceSnapshotId')}",
        f"Development seasons: {seasons[0]}-{seasons[-1]}",
        "2025 holdout: SEALED / NOT READ",
        "2026 prospective: NOT READ BY THIS RESEARCH RUN",
        "Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO · refit NO",
        "",
        "THURSDAY FACTORS NOW MEASURABLE FROM CURRENT PBP",
        f"  Late-down scramble conversions: {scramble['late_down_scramble_conversions']:,}",
        f"  Drives containing a scramble: {scramble['drives_with_scramble']:,}",
        f"  Explosive plays 20+: {exp['explosive_plays_20_plus']:,}",
        f"  Response drives: {response['n']:,} · score rate {pct(response['score_rate'])}",
        f"  Nullified high-impact events: {len(summary['nullified_impact_events']):,}",
        f"  High-leverage penalty candidates: {penalty['high_leverage_candidates']:,}",
        f"  Containment+explosive-suppression proxy drives: {cx['drives_with_no_late_down_scramble_conversion_and_no_20_plus_play']:,} · score rate {pct(cx['scoring_rate_on_those_drives'])}",
        "",
        "EARLY-DOWN RUN SUCCESS -> LATER PRESSURE EXPOSURE DIAGNOSTIC",
        f"  game-team rows: {len(paired):,}",
        f"  high-exposure DB rate when early-run success >=50%: {pct(hi_exp)}",
        f"  high-exposure DB rate when early-run success <50%: {pct(lo_exp)}",
        f"  difference: {'NA' if hi_exp is None or lo_exp is None else f'{100*(hi_exp-lo_exp):+.3f} pp'}",
        "",
        "EXPLICIT DATA GAPS — NOT FABRICATED",
    ]
    lines.extend(f"  {k}: {v}" for k, v in th.DATA_GAPS.items())
    lines += [
        "",
        "Interpretation guard:",
        "  These are descriptive research diagnostics, not new production coefficients.",
        "  Any supported factor must beat the existing baseline in a paired chronological challenger before promotion.",
        "  Tracking-dependent findings remain data requirements, not PBP proxies disguised as truth.",
        "",
        f"JSON: {json_path}",
    ]
    txt_path = out_dir / "NFL_THURSDAY_INTERACTION_RESEARCH.txt"
    txt_path.write_text("
".join(lines) + "
", encoding="utf-8")

    current = root / "data/models/nfl/CURRENT_STATE_INTELLIGENCE_015"
    current.parent.mkdir(parents=True, exist_ok=True)
    tmp = current.with_name("." + current.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "
", encoding="utf-8")
    os.replace(tmp, current)

    print()
    print(txt_path.read_text(encoding="utf-8"))
    print("PASS State 0.1.5 Thursday research · 2025 sealed · 2026 excluded · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import sys
import uuid

try:
    import pyarrow.parquet as pq
except Exception as exc:
    raise SystemExit(f"pyarrow required; run scripts/nfl/bootstrap_phase1_python.command: {exc}")


def parse_seasons(text: str) -> list[int]:
    text = text.strip()
    if "-" in text:
        a, b = (int(x) for x in text.split("-", 1))
        if a > b:
            raise ValueError("season range must be ascending")
        return list(range(a, b + 1))
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def load_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def play_key(game_id, play_id) -> tuple[str, float | None]:
    try:
        p = round(float(play_id), 6)
    except Exception:
        p = None
    return str(game_id or ""), p


def asset_index(manifest: dict) -> dict[tuple[str, int | None], dict]:
    return {(str(a.get("source") or ""), a.get("season")): dict(a) for a in manifest.get("assets", [])}


def main() -> int:
    ap = argparse.ArgumentParser(description="NFL QB State 0.1.8 official-stat reconciliation audit")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    sys.path.insert(0, str(model_dir))
    import qb_semantic_reconciliation_018 as q18

    seasons = q18.assert_development_only(parse_seasons(args.seasons))
    season_set = set(seasons)

    raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    prior_ptr = root / "data/models/nfl/CURRENT_QB_STATE_017"
    if not raw_ptr.exists() or not prior_ptr.exists():
        raise FileNotFoundError("required raw/QB State 0.1.7 pointer missing")
    sid = raw_ptr.read_text(encoding="utf-8").strip()
    prior_dir = root / prior_ptr.read_text(encoding="utf-8").strip()
    prior_audit = json.loads((prior_dir / "NFL_QB_SEMANTIC_HARDENING_AUDIT.json").read_text(encoding="utf-8"))
    prior_rows = load_jsonl(prior_dir / "NFL_QB_SEMANTIC_HARDENING_ROWS.jsonl")

    if prior_audit.get("sourceSnapshotId") != sid:
        raise ValueError("QB State 0.1.7/raw snapshot mismatch")
    if prior_audit.get("holdoutOpened") is not False:
        raise ValueError("QB State 0.1.7 holdout boundary drift")
    if prior_audit.get("modelFitAuthorizedForNextVersion") is not False:
        raise ValueError("QB State 0.1.7 unexpectedly authorized model fitting")
    if prior_audit.get("disposition") != "PASSING_RESIDUAL_REQUIRES_REVIEW":
        raise ValueError("0.1.8 expected 0.1.7 PASSING_RESIDUAL_REQUIRES_REVIEW blocker")

    blocked = [
        r for r in prior_rows
        if int(r.get("season") or 0) in season_set
        and str(r.get("hardening_class") or "") == "UNEXPLAINED_NONFUMBLE"
    ]
    if not blocked:
        raise ValueError("no unexplained non-fumble residual rows found to reconcile")

    wanted = {play_key(r.get("game_id"), r.get("play_id")) for r in blocked}
    manifest = json.loads((root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    assets = asset_index(manifest)

    fields = {
        "game_id", "play_id", "season", "week", "posteam", "desc",
        "passer_player_id", "receiver_player_id", "receiver_player_name",
        "passing_yards", "receiving_yards", "lateral_receiving_yards",
        "air_yards", "yards_after_catch", "yards_gained",
        "lateral_reception", "lateral_receiver_player_id", "lateral_receiver_player_name",
        "fumble", "fumble_lost", "fumble_out_of_bounds",
        "penalty", "penalty_yards", "no_play", "complete_pass",
    }
    raw_by_key: dict[tuple[str, float | None], dict] = {}
    schema_presence = {}
    for season in seasons:
        season_keys = {k for k in wanted if k[0].startswith(f"{season}_")}
        if not season_keys:
            continue
        asset = assets.get(("play_by_play", season))
        if not asset:
            raise ValueError(f"raw snapshot missing play_by_play {season}")
        pf = pq.ParquetFile(root / asset["blobPath"])
        names = set(pf.schema_arrow.names)
        cols = sorted(fields & names)
        schema_presence[str(season)] = cols
        for row in pf.read(columns=cols).to_pylist():
            key = play_key(row.get("game_id"), row.get("play_id"))
            if key in season_keys:
                raw_by_key[key] = dict(row)
        print(f"PASS reconciliation source {season} · rows matched {sum(1 for k in season_keys if k in raw_by_key)}/{len(season_keys)}")

    missing = [k for k in wanted if k not in raw_by_key]
    if missing:
        raise ValueError(f"could not rematch {len(missing)} reconciliation row(s) to raw PBP")

    reconciled = []
    unresolved = 0
    official_coherent = 0
    for prior in blocked:
        key = play_key(prior.get("game_id"), prior.get("play_id"))
        raw = raw_by_key[key]
        rec = dict(prior)
        for k, v in raw.items():
            rec[k] = v
        cls = q18.reconciliation_class(raw)
        detail = q18.official_receiving_reconciliation(raw)
        rec["reconciliation_class"] = cls
        rec["official_reconciliation"] = detail
        if cls == "UNRESOLVED_OFFICIAL_STAT_MISMATCH":
            unresolved += 1
        else:
            official_coherent += 1
        reconciled.append(rec)

    prior_conflicts = int((prior_audit.get("dropbackConflictHardening") or {}).get("nonReviewConflicts") or 0)
    authorized = q18.model_fit_authorized(
        prior_nonreview_conflicts=prior_conflicts,
        unresolved_rows=unresolved,
        reconciled_rows=official_coherent,
    )
    disposition = (
        "SEMANTICS_HARDENED_WITH_RARE_EVENT_QUARANTINE"
        if authorized
        else "OFFICIAL_STAT_RECONCILIATION_REQUIRES_REVIEW"
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/qb_state_018" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    rows_path = out_dir / "NFL_QB_SEMANTIC_RECONCILIATION_ROWS.jsonl"
    with rows_path.open("w", encoding="utf-8") as f:
        for row in sorted(reconciled, key=lambda r: (int(r.get("season") or 0), int(r.get("week") or 0), str(r.get("game_id") or ""), float(r.get("play_id") or -1))):
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    report = {
        "version": q18.VERSION,
        "lineage": q18.LINEAGE,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceSnapshotId": sid,
        "sourceQbState017Directory": str(prior_dir.relative_to(root)),
        "developmentSeasons": list(seasons),
        "sealedHoldoutSeason": 2025,
        "holdoutOpened": False,
        "prospectiveSeason": 2026,
        "prospectiveRead": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "modelFitPerformed": False,
        "rowsReviewed": len(reconciled),
        "officialStatCoherentRows": official_coherent,
        "unresolvedOfficialStatRows": unresolved,
        "priorNonReviewDropbackConflicts": prior_conflicts,
        "policy": "retain official nflverse passing_yards/receiving_yards as statistical targets; quarantine rare rows where air_yards + YAC disagrees from air/YAC component fits; never rewrite official totals",
        "sourceFieldPresenceBySeason": schema_presence,
        "disposition": disposition,
        "modelFitAuthorizedForNextVersion": authorized,
        "authorizationScope": "development-only chronological QB challenger; 2025 remains sealed; replay conflicts and lateral/fumble/air-YAC mismatch rows remain quarantined from component fits",
    }
    audit_path = out_dir / "NFL_QB_SEMANTIC_RECONCILIATION_AUDIT.json"
    audit_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    ptr = root / "data/models/nfl/CURRENT_QB_STATE_018"
    ptr.parent.mkdir(parents=True, exist_ok=True)
    tmp = ptr.with_name("." + ptr.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
    os.replace(tmp, ptr)

    print("\nNFL QB STATE 0.1.8 — OFFICIAL-STAT RECONCILIATION AUDIT")
    print(f"Source snapshot: {sid}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print(f"\nRows requiring reconciliation: {len(reconciled)}")
    for r in reconciled:
        d = str(r.get("desc") or "")
        if len(d) > 220:
            d = d[:217] + "..."
        detail = r["official_reconciliation"]
        print(
            f"  {r.get('game_id')} · {r.get('posteam') or r.get('team')} · play {r.get('play_id')} · "
            f"pass {detail.get('passing_yards')} · rec {detail.get('receiving_yards')} · "
            f"lat rec {detail.get('lateral_receiving_yards')} · air {r.get('air_yards')} · "
            f"YAC {r.get('yards_after_catch')} · class {r.get('reconciliation_class')}"
        )
        print(f"    {d}")
    print(f"\nOfficial-stat coherent: {official_coherent}/{len(reconciled)}")
    print(f"Unresolved official-stat mismatch: {unresolved}")
    print(f"Disposition: {disposition}")
    print(f"MODEL-FIT AUTHORIZATION FOR NEXT VERSION: {'YES' if authorized else 'NO'}")
    print("  official totals remain authoritative; rare component anomalies remain quarantined")
    print(f"Rows: {rows_path}")
    print(f"Audit: {audit_path}")
    print("PASS QB State 0.1.8 semantic reconciliation · no model fit performed · 2025 sealed · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

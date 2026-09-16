#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
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


def asset_index(manifest: dict) -> dict[tuple[str, int | None], dict]:
    return {(str(a.get("source") or ""), a.get("season")): dict(a) for a in manifest.get("assets", [])}


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


def main() -> int:
    ap = argparse.ArgumentParser(description="NFL QB State 0.1.7 semantic hardening audit")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    sys.path.insert(0, str(model_dir))
    import qb_semantic_hardening_017 as q17

    seasons = q17.assert_development_only(parse_seasons(args.seasons))
    season_set = set(seasons)

    raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    prior_ptr = root / "data/models/nfl/CURRENT_QB_STATE_016"
    if not raw_ptr.exists() or not prior_ptr.exists():
        raise FileNotFoundError("required raw/QB State 0.1.6 pointer missing")
    sid = raw_ptr.read_text(encoding="utf-8").strip()
    prior_dir = root / prior_ptr.read_text(encoding="utf-8").strip()
    prior_audit_path = prior_dir / "NFL_QB_SEMANTIC_ANOMALY_AUDIT.json"
    prior_rows_path = prior_dir / "NFL_QB_SEMANTIC_ANOMALY_ROWS.jsonl"
    prior_audit = json.loads(prior_audit_path.read_text(encoding="utf-8"))
    if prior_audit.get("sourceSnapshotId") != sid:
        raise ValueError("QB State 0.1.6/raw snapshot mismatch")
    if prior_audit.get("holdoutOpened") is not False:
        raise ValueError("QB State 0.1.6 holdout boundary drift")
    if prior_audit.get("modelFitAuthorized") is not False:
        raise ValueError("QB State 0.1.6 unexpectedly authorized model fitting")

    anomaly_rows = load_jsonl(prior_rows_path)
    anomaly_rows = [r for r in anomaly_rows if int(r.get("season") or 0) in season_set]
    wanted = {play_key(r.get("game_id"), r.get("play_id")) for r in anomaly_rows}

    manifest = json.loads((root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    assets = asset_index(manifest)

    extra_fields = {
        "game_id", "play_id", "season", "week", "posteam", "desc",
        "sack", "qb_scramble", "pass_attempt", "rush_attempt", "yards_gained",
        "passing_yards", "air_yards", "yards_after_catch", "lateral_reception",
        "fumble", "fumble_lost", "fumble_out_of_bounds",
        "fumble_recovery_1_team", "fumble_recovery_1_player_id", "fumble_recovery_1_yards",
        "fumble_recovery_2_team", "fumble_recovery_2_player_id", "fumble_recovery_2_yards",
    }
    raw_by_key: dict[tuple[str, float | None], dict] = {}
    schema_presence: dict[str, list[str]] = {}
    for season in seasons:
        season_keys = {k for k in wanted if k[0].startswith(f"{season}_")}
        if not season_keys:
            continue
        asset = assets.get(("play_by_play", season))
        if not asset:
            raise ValueError(f"raw snapshot missing play_by_play {season}")
        path = root / asset["blobPath"]
        pf = pq.ParquetFile(path)
        names = set(pf.schema_arrow.names)
        if not {"game_id", "play_id"}.issubset(names):
            raise ValueError(f"{path.name} missing game_id/play_id")
        cols = sorted(extra_fields & names)
        schema_presence[str(season)] = cols
        for row in pf.read(columns=cols).to_pylist():
            key = play_key(row.get("game_id"), row.get("play_id"))
            if key in season_keys:
                raw_by_key[key] = dict(row)
        print(f"PASS hardening source {season} · anomaly rows matched {sum(1 for k in season_keys if k in raw_by_key)}/{len(season_keys)}")

    missing_keys = sorted(k for k in wanted if k not in raw_by_key)
    if missing_keys:
        raise ValueError(f"could not rematch {len(missing_keys)} anomaly play(s) to raw PBP")

    enriched = []
    conflict_total = conflict_review = conflict_nonreview = 0
    residual_counter = Counter()
    residual_yards = defaultdict(float)
    fumble_evidence_counts = Counter()

    for anomaly in anomaly_rows:
        key = play_key(anomaly.get("game_id"), anomaly.get("play_id"))
        raw = raw_by_key[key]
        rec = dict(anomaly)
        for field in sorted(extra_fields):
            if field in raw and field not in rec:
                rec[field] = raw.get(field)

        kind = str(anomaly.get("kind") or "")
        if kind == "DROPBACK_CONFLICT":
            conflict_total += 1
            review = q17.replay_review_evidence(raw)
            rec["hardening_class"] = "REPLAY_REVIEW_FLAG_CONFLICT" if review else "NONREVIEW_FLAG_CONFLICT"
            rec["review_evidence"] = review
            if review:
                conflict_review += 1
            else:
                conflict_nonreview += 1

        elif kind == "PASSING_YARD_UNEXPLAINED_NONLATERAL":
            cls = q17.classify_nonlateral_residual(raw)
            rec["hardening_class"] = cls
            ev = q17.fumble_evidence(raw)
            rec["fumble_evidence"] = ev
            residual_counter[cls] += 1
            resid = anomaly.get("residual_yards")
            if resid is not None:
                residual_yards[cls] += float(resid)
            for k, v in ev.items():
                if k != "any" and v:
                    fumble_evidence_counts[k] += 1

        elif kind == "PASSING_YARD_LATERAL_RECEPTION":
            rec["hardening_class"] = "LATERAL_RECEPTION"
        else:
            rec["hardening_class"] = "UNCHANGED"
        enriched.append(rec)

    prior_drop = prior_audit.get("dropbackAnomalies", {})
    other_dropbacks = int(prior_drop.get("otherRows") or 0)
    unexplained_nonfumble = int(residual_counter["UNEXPLAINED_NONFUMBLE"])
    disp = q17.disposition(
        other_dropbacks=other_dropbacks,
        conflict_rows=conflict_total,
        nonreview_conflicts=conflict_nonreview,
        unexplained_nonfumble=unexplained_nonfumble,
    )
    authorized = q17.model_fit_authorized(disp)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/qb_state_017" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    rows_path = out_dir / "NFL_QB_SEMANTIC_HARDENING_ROWS.jsonl"
    with rows_path.open("w", encoding="utf-8") as f:
        for row in sorted(enriched, key=lambda r: (int(r.get("season") or 0), int(r.get("week") or 0), str(r.get("game_id") or ""), float(r.get("play_id") or -1), str(r.get("kind") or ""))):
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    report = {
        "version": q17.VERSION,
        "lineage": q17.LINEAGE,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceSnapshotId": sid,
        "sourceQbState016Directory": str(prior_dir.relative_to(root)),
        "developmentSeasons": list(seasons),
        "sealedHoldoutSeason": 2025,
        "holdoutOpened": False,
        "prospectiveSeason": 2026,
        "prospectiveRead": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "modelFitPerformed": False,
        "dropbackConflictHardening": {
            "conflicts": conflict_total,
            "replayReviewEvidence": conflict_review,
            "nonReviewConflicts": conflict_nonreview,
            "policy": "quarantine replay sack+scramble conflicts from mutually-exclusive component outcome fits; retain authoritative team-game total dropback target",
        },
        "nonlateralPassingResidualHardening": {
            "rows": sum(residual_counter.values()),
            "fumbleSequence": int(residual_counter["FUMBLE_SEQUENCE"]),
            "unexplainedNonfumble": unexplained_nonfumble,
            "residualYardsFumbleSequence": residual_yards["FUMBLE_SEQUENCE"],
            "residualYardsUnexplainedNonfumble": residual_yards["UNEXPLAINED_NONFUMBLE"],
            "fumbleEvidenceCounts": dict(fumble_evidence_counts),
            "policy": "official passing_yards remains the settlement target; clean air+YAC component fits may quarantine lateral/fumble residual completions rather than rewriting official yards",
        },
        "sourceFieldPresenceBySeason": schema_presence,
        "disposition": disp,
        "modelFitAuthorizedForNextVersion": authorized,
        "authorizationScope": "development-only chronological QB challenger; 2025 remains sealed; rare-event quarantine must be preserved",
    }
    audit_path = out_dir / "NFL_QB_SEMANTIC_HARDENING_AUDIT.json"
    audit_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    ptr = root / "data/models/nfl/CURRENT_QB_STATE_017"
    ptr.parent.mkdir(parents=True, exist_ok=True)
    tmp = ptr.with_name("." + ptr.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
    os.replace(tmp, ptr)

    print("\nNFL QB STATE 0.1.7 — SEMANTIC HARDENING AUDIT")
    print(f"Source snapshot: {sid}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print("\nDROPBACK CONFLICT HARDENING")
    print(f"  sack+scramble conflicts: {conflict_total}")
    print(f"  replay/challenge evidence: {conflict_review}/{conflict_total}")
    print(f"  non-review conflicts: {conflict_nonreview}")
    print("  policy: quarantine from component outcome fits; keep total dropback target")
    print("\nNONLATERAL AIR+YAC RESIDUAL HARDENING")
    print(f"  rows: {sum(residual_counter.values())}")
    print(f"  fumble-linked: {residual_counter['FUMBLE_SEQUENCE']} · residual yards {residual_yards['FUMBLE_SEQUENCE']:.1f}")
    print(f"  unexplained non-fumble: {unexplained_nonfumble} · residual yards {residual_yards['UNEXPLAINED_NONFUMBLE']:.1f}")
    if fumble_evidence_counts:
        print("  fumble evidence: " + " · ".join(f"{k} {v}" for k, v in sorted(fumble_evidence_counts.items())))
    print(f"\nDisposition: {disp}")
    print(f"MODEL-FIT AUTHORIZATION FOR NEXT VERSION: {'YES' if authorized else 'NO'}")
    print("  authorization is development-only; 2025 remains sealed; rare-event quarantine is mandatory")
    print(f"Rows: {rows_path}")
    print(f"Audit: {audit_path}")
    print("PASS QB State 0.1.7 semantic hardening · no model fit performed · 2025 sealed · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

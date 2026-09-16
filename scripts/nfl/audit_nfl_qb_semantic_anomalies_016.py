#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
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


def pct(n: int | float, d: int | float) -> float | None:
    return None if not d else 100.0 * float(n) / float(d)


def asset_index(manifest: dict) -> dict[tuple[str, int | None], dict]:
    return {(str(a.get("source") or ""), a.get("season")): dict(a) for a in manifest.get("assets", [])}


def main() -> int:
    ap = argparse.ArgumentParser(description="NFL QB State 0.1.6 semantic anomaly attribution audit")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--seasons", default="2016-2024")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    model_dir = root / "packages/models/nfl/game"
    provider_dir = root / "packages/providers/nflverse/src"
    sys.path.insert(0, str(model_dir))
    sys.path.insert(0, str(provider_dir))
    import qb_target_semantics_015 as q15
    import qb_semantic_anomaly_audit_016 as q16
    import contract

    seasons = q16.assert_development_only(parse_seasons(args.seasons))
    season_set = set(seasons)

    raw_ptr = root / "data/raw/nfl/nflverse/CURRENT_RAW_SNAPSHOT"
    phase_ptr = root / "data/normalized/nfl/CURRENT_PHASE1_SNAPSHOT"
    target_ptr = root / "data/normalized/nfl/CURRENT_NFL_QB_TARGETS_015"
    if not raw_ptr.exists() or not phase_ptr.exists() or not target_ptr.exists():
        raise FileNotFoundError("required raw/Phase1/QB-target pointer missing")
    sid = raw_ptr.read_text(encoding="utf-8").strip()
    if phase_ptr.read_text(encoding="utf-8").strip() != sid:
        raise ValueError("Phase1/raw snapshot mismatch")

    target_dir = root / target_ptr.read_text(encoding="utf-8").strip()
    prior_audit = json.loads((target_dir / "NFL_QB_TARGET_SEMANTICS_AUDIT.json").read_text(encoding="utf-8"))
    if prior_audit.get("holdoutOpened") is not False:
        raise ValueError("0.1.5 holdout boundary drift")
    if prior_audit.get("sourceSnapshotId") != sid:
        raise ValueError("0.1.5/raw source snapshot mismatch")

    manifest = json.loads((root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    assets = asset_index(manifest)
    phase1 = root / "data/normalized/nfl/phase1" / sid

    reg_games: set[str] = set()
    with (phase1 / "game_identity.csv").open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if int(r.get("season") or 0) in season_set and str(r.get("game_type") or "").upper() == "REG":
                reg_games.add(str(r["game_id"]))

    sack_flagged = 0
    sack_with_pass = 0
    conflict_rows: list[dict] = []
    other_rows: list[dict] = []
    completion_class = Counter()
    residual_yards = defaultdict(float)
    residual_rows: list[dict] = []
    decomposable_completions = 0

    for season in seasons:
        asset = assets.get(("play_by_play", season))
        if not asset:
            raise ValueError(f"raw snapshot missing play_by_play {season}")
        path = root / asset["blobPath"]
        pf = pq.ParquetFile(path)
        names = set(pf.schema_arrow.names)
        must = set(q15.REQUIRED_PBP_FIELDS)
        missing = sorted(must - names)
        if missing:
            raise ValueError(f"{path.name} missing 0.1.6 audit fields: {', '.join(missing)}")
        extra = {
            "play_id", "no_play", "desc", "lateral_reception", "fumble", "aborted_play",
            "passer_player_name", "rusher_player_name", "receiver_player_name",
        }
        cols = list(q15.REQUIRED_PBP_FIELDS) + sorted((set(q15.OPTIONAL_PBP_FIELDS) | extra) & names - set(q15.REQUIRED_PBP_FIELDS))
        rows = pf.read(columns=cols).to_pylist()
        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in rows:
            gid = str(r.get("game_id") or "")
            if gid not in reg_games:
                continue
            team_raw = str(r.get("posteam") or "").strip().upper()
            if not team_raw:
                continue
            rr = dict(r)
            rr["posteam"] = contract.normalize_team_abbr(team_raw)
            grouped[(gid, rr["posteam"])].append(rr)

        season_conflicts = season_other = season_residual = 0
        for (gid, team), grows in grouped.items():
            starter, _, _ = q15.observed_qb_labels(grows)
            if not starter:
                continue
            for row in grows:
                qid = q15.qb_identity_on_dropback(row)
                if q15.structural_dropback(row) and qid == starter:
                    if q16.flag(row.get("sack")):
                        sack_flagged += 1
                        if q16.flag(row.get("pass_attempt")):
                            sack_with_pass += 1
                    outcome = q15.dropback_outcome(row)
                    if outcome in {"CONFLICT", "OTHER"}:
                        rec = {
                            "kind": f"DROPBACK_{outcome}",
                            "season": season,
                            "week": int(float(row.get("week") or 0)),
                            "game_id": gid,
                            "team": team,
                            "play_id": q16.num(row.get("play_id")),
                            "qb_gsis_id": starter,
                            "pass_attempt": q16.num(row.get("pass_attempt")),
                            "sack": q16.num(row.get("sack")),
                            "qb_scramble": q16.num(row.get("qb_scramble")),
                            "rush_attempt": q16.num(row.get("rush_attempt")),
                            "yards_gained": q16.num(row.get("yards_gained")),
                            "play_type": q16.clean(row.get("play_type")),
                            "aborted_play": q16.num(row.get("aborted_play")),
                            "desc": q16.clean(row.get("desc")),
                        }
                        if outcome == "CONFLICT":
                            conflict_rows.append(rec)
                            season_conflicts += 1
                        else:
                            other_rows.append(rec)
                            season_other += 1

                passer = q16.clean(row.get("passer_player_id"))
                if (
                    q15.settlement_pass_attempt(row)
                    and passer == starter
                    and q16.flag(row.get("complete_pass"))
                ):
                    resid = q16.completion_residual(row)
                    cls = q16.residual_class(row)
                    completion_class[cls] += 1
                    if resid is not None:
                        decomposable_completions += 1
                        residual_yards[cls] += resid
                    if cls not in {"EXACT", "MISSING_COMPONENT"}:
                        rec = {
                            "kind": f"PASSING_YARD_{cls}",
                            "season": season,
                            "week": int(float(row.get("week") or 0)),
                            "game_id": gid,
                            "team": team,
                            "play_id": q16.num(row.get("play_id")),
                            "qb_gsis_id": starter,
                            "passing_yards": q16.num(row.get("passing_yards")),
                            "air_yards": q16.num(row.get("air_yards")),
                            "yards_after_catch": q16.num(row.get("yards_after_catch")),
                            "residual_yards": resid,
                            "lateral_reception": q16.num(row.get("lateral_reception")),
                            "fumble": q16.num(row.get("fumble")),
                            "receiver_player_name": q16.clean(row.get("receiver_player_name")),
                            "desc": q16.clean(row.get("desc")),
                        }
                        residual_rows.append(rec)
                        season_residual += 1
        print(
            f"PASS anomaly scan {season} · conflicts {season_conflicts} · OTHER {season_other} · "
            f"nonzero air/YAC residual completions {season_residual}"
        )

    corrected_sack_pct = pct(sack_with_pass, sack_flagged)
    nonzero_residuals = completion_class["LATERAL_RECEPTION"] + completion_class["UNEXPLAINED_NONLATERAL"]
    unexplained = completion_class["UNEXPLAINED_NONLATERAL"]
    if other_rows:
        disposition = "STRUCTURAL_OTHER_REQUIRES_REVIEW"
    elif unexplained:
        disposition = "NONLATERAL_PASSING_RESIDUAL_REQUIRES_REVIEW"
    else:
        disposition = "ANOMALIES_ATTRIBUTED_READY_FOR_SEMANTIC_HARDENING"

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/nfl/qb_state_016" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    anomalies_path = out_dir / "NFL_QB_SEMANTIC_ANOMALY_ROWS.jsonl"
    with anomalies_path.open("w", encoding="utf-8") as f:
        for row in sorted(conflict_rows + other_rows + residual_rows, key=lambda r: (r["season"], r["week"], r["game_id"], r.get("play_id") or -1, r["kind"])):
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    report = {
        "version": q16.VERSION,
        "lineage": q16.LINEAGE,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceSnapshotId": sid,
        "sourceTarget015Directory": str(target_dir.relative_to(root)),
        "developmentSeasons": list(seasons),
        "sealedHoldoutSeason": 2025,
        "holdoutOpened": False,
        "prospectiveSeason": 2026,
        "prospectiveRead": False,
        "marketDependency": False,
        "oddsPapiRequests": 0,
        "frozenOmegaMutation": False,
        "modelFitPerformed": False,
        "correctedSackSemantics": {
            "sackFlaggedStarterStructuralDropbacks": sack_flagged,
            "alsoPassAttempt": sack_with_pass,
            "pct": corrected_sack_pct,
            "note": "0.1.5 denominator used only unambiguous SACK outcomes while numerator also counted sack+scramble conflicts; 0.1.6 uses the same sack-flagged universe in numerator and denominator.",
        },
        "dropbackAnomalies": {
            "sackScrambleConflictRows": len(conflict_rows),
            "otherRows": len(other_rows),
        },
        "passingYardResidualAttribution": {
            "decomposableCompletions": decomposable_completions,
            "exact": completion_class["EXACT"],
            "lateralReception": completion_class["LATERAL_RECEPTION"],
            "unexplainedNonlateral": completion_class["UNEXPLAINED_NONLATERAL"],
            "missingComponent": completion_class["MISSING_COMPONENT"],
            "nonzeroResiduals": nonzero_residuals,
            "residualYardsByClass": dict(residual_yards),
        },
        "disposition": disposition,
        "modelFitAuthorized": False,
    }
    audit_path = out_dir / "NFL_QB_SEMANTIC_ANOMALY_AUDIT.json"
    audit_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    ptr = root / "data/models/nfl/CURRENT_QB_STATE_016"
    ptr.parent.mkdir(parents=True, exist_ok=True)
    tmp = ptr.with_name("." + ptr.name + ".tmp")
    tmp.write_text(str(out_dir.relative_to(root)) + "\n", encoding="utf-8")
    os.replace(tmp, ptr)

    print("\nNFL QB STATE 0.1.6 — SEMANTIC ANOMALY ATTRIBUTION AUDIT")
    print(f"Source snapshot: {sid}")
    print(f"Development seasons: {seasons[0]}-{seasons[-1]}")
    print("2025 holdout: SEALED / NOT READ")
    print("2026 prospective: NOT READ")
    print("Market dependency: NO · OddsPapi 0 · frozen OMEGA mutation NO")
    print("\nCORRECTED SACK / PASS_ATTEMPT SEMANTICS")
    print(f"  sack-flagged starter structural dropbacks: {sack_flagged:,}")
    print(f"  also pass_attempt: {sack_with_pass:,}/{sack_flagged:,} ({corrected_sack_pct:.4f}%)")
    print("  note: 0.1.5's >100% rate was a denominator bookkeeping mismatch, not a source impossibility")
    print("\nDROPBACK ANOMALIES")
    print(f"  sack+scramble CONFLICT rows: {len(conflict_rows):,}")
    print(f"  OTHER structural dropbacks: {len(other_rows):,}")
    for r in conflict_rows[:10]:
        d = r.get("desc") or ""
        if len(d) > 150: d = d[:147] + "..."
        print(f"    {r['game_id']} · {r['team']} · play {r.get('play_id')} · {r['qb_gsis_id']} · yards {r.get('yards_gained')} · {d}")
    print("\nAIR + YAC RESIDUAL ATTRIBUTION")
    print(f"  decomposable completions: {decomposable_completions:,}")
    print(f"  exact: {completion_class['EXACT']:,}")
    print(f"  nonzero residual: {nonzero_residuals:,}")
    print(f"    lateral_reception: {completion_class['LATERAL_RECEPTION']:,} · residual yards {residual_yards['LATERAL_RECEPTION']:.1f}")
    print(f"    unexplained non-lateral: {unexplained:,} · residual yards {residual_yards['UNEXPLAINED_NONLATERAL']:.1f}")
    if unexplained:
        print("  first unexplained non-lateral rows:")
        samples = [r for r in residual_rows if r["kind"] == "PASSING_YARD_UNEXPLAINED_NONLATERAL"][:10]
        for r in samples:
            d = r.get("desc") or ""
            if len(d) > 150: d = d[:147] + "..."
            print(f"    {r['game_id']} · {r['team']} · play {r.get('play_id')} · resid {r.get('residual_yards')} · {d}")
    print(f"\nDisposition: {disposition}")
    print("MODEL-FIT AUTHORIZATION: NO — diagnostic attribution only")
    print(f"Anomaly rows: {anomalies_path}")
    print(f"Audit: {audit_path}")
    print("PASS QB State 0.1.6 anomaly attribution · 2025 sealed · frozen OMEGA untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

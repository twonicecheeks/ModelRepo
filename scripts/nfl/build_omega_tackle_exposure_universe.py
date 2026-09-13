#!/usr/bin/env python3
"""Build OMEGA 0.1.1 full defensive exposure universe without opening 2025.

This is a foundation hardening step, not a fitted model. It fixes a critical
selection-bias risk: the 0.1 player-game table only contains players who received at
least one tackle credit. Zero-credit defensive player-games must exist before any
count/rate model can be fit.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import argparse, csv, hashlib, json, os, shutil, sys
from typing import Any

DEV_SEASONS = set(range(2016, 2025))
HOLDOUT = 2025
SCHEMA = "OMEGA_TACKLE_EXPOSURE_UNIVERSE_0.1.1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def latest_snap_manifest(root: Path, sid: str) -> Path:
    base = root / "data/raw/nfl/nflverse/phase2c_context/snapshots"
    candidates: list[tuple[str, Path]] = []
    for p in base.glob("*/SOURCE_MANIFEST.json") if base.exists() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("sourcePhase1SnapshotId") == sid:
                candidates.append((str(d.get("createdAt") or ""), p))
        except Exception:
            pass
    if not candidates:
        raise SystemExit("FAIL matching Phase2C snap-count manifest not found")
    return max(candidates)[1]


def load_player_meta(root: Path, source_manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    import pyarrow.parquet as pq
    a = next((x for x in source_manifest.get("assets", []) if x.get("source") == "players"), None)
    if not a:
        raise SystemExit("FAIL Phase1 players asset missing")
    path = root / a["blobPath"]
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    need = {"gsis_id", "display_name", "position", "position_group"}
    if not need.issubset(names):
        raise SystemExit(f"FAIL players schema missing {sorted(need - names)}")
    cols = ["gsis_id", "display_name", "position", "position_group"] + (["pfr_id"] if "pfr_id" in names else [])
    rows = pf.read(columns=cols).to_pylist()
    by_gsis, pfr_to_gsis = {}, {}
    for r in rows:
        gsis = str(r.get("gsis_id") or "").strip()
        if not gsis:
            continue
        pfr = str(r.get("pfr_id") or "").strip()
        by_gsis[gsis] = {
            "display_name": str(r.get("display_name") or ""),
            "position": str(r.get("position") or ""),
            "position_group": str(r.get("position_group") or ""),
            "pfr_id": pfr,
        }
        if pfr:
            pfr_to_gsis[pfr] = gsis
    return by_gsis, pfr_to_gsis


def load_snap_rows(root: Path, manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import pyarrow.parquet as pq
    d = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = [x for x in d.get("assets", []) if x.get("source") == "snap_counts" and int(x.get("season") or 0) in DEV_SEASONS]
    out: list[dict[str, Any]] = []
    aliases_seen: dict[str, str | None] = {"st_snaps": None, "st_pct": None}
    for a in assets:
        path = root / a["blobPath"]
        pf = pq.ParquetFile(path)
        names = set(pf.schema_arrow.names)
        req = {"game_id", "season", "game_type", "week", "team", "opponent", "player", "pfr_player_id", "position", "defense_snaps", "defense_pct"}
        miss = req - names
        if miss:
            raise SystemExit(f"FAIL {path.name} missing snap columns {sorted(miss)}")
        st_snaps = next((c for c in ("special_teams_snaps", "st_snaps") if c in names), None)
        st_pct = next((c for c in ("special_teams_pct", "st_pct") if c in names), None)
        aliases_seen["st_snaps"] = aliases_seen["st_snaps"] or st_snaps
        aliases_seen["st_pct"] = aliases_seen["st_pct"] or st_pct
        cols = list(req) + ([st_snaps] if st_snaps else []) + ([st_pct] if st_pct else [])
        for r in pf.read(columns=cols).to_pylist():
            if int(r.get("season") or 0) == HOLDOUT:
                raise SystemExit("FAIL 2025 snap row entered OMEGA 0.1.1")
            if str(r.get("game_type") or "") != "REG":
                continue
            if st_snaps:
                r["special_teams_snaps"] = r.get(st_snaps)
            if st_pct:
                r["special_teams_pct"] = r.get(st_pct)
            out.append(r)
    return out, {"assets": len(assets), "rows": len(out), "aliases": aliases_seen}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "packages/models/nfl/omega"))
    import exposure_universe as eu

    ptr = root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_FOUNDATION"
    if not ptr.exists():
        raise SystemExit("FAIL CURRENT_OMEGA_TACKLE_FOUNDATION missing")
    sid = ptr.read_text(encoding="utf-8").strip()
    foundation = root / "data/normalized/nfl/omega_tackle" / sid
    event_path = foundation / "omega_tackle_credit_events.csv"
    audit_path = foundation / "OMEGA_TACKLE_FOUNDATION_AUDIT.json"
    if not event_path.exists() or not audit_path.exists():
        raise SystemExit("FAIL OMEGA 0.1 foundation outputs missing")
    fa = json.loads(audit_path.read_text(encoding="utf-8"))
    if fa.get("omegaHoldoutPbpRowsRead") != 0 or fa.get("omegaHoldoutTackleOutcomesRead") != 0:
        raise SystemExit("FAIL 0.1 foundation holdout integrity is not clean")
    if fa.get("marketFieldsRead") != 0 or fa.get("oddsPapiRequests") != 0:
        raise SystemExit("FAIL market contamination detected in 0.1 foundation")

    phase1_manifest_path = root / "data/raw/nfl/nflverse/snapshots" / sid / "SOURCE_MANIFEST.json"
    phase1_manifest = json.loads(phase1_manifest_path.read_text(encoding="utf-8"))
    player_meta, pfr_to_gsis = load_player_meta(root, phase1_manifest)
    snap_manifest_path = latest_snap_manifest(root, sid)
    snap_rows, snap_audit = load_snap_rows(root, snap_manifest_path)

    game_rows = read_csv(root / "data/normalized/nfl/phase1" / sid / "game_identity.csv")
    games = {r["game_id"]: r for r in game_rows if int(r.get("season") or 0) in DEV_SEASONS and r.get("game_type") == "REG"}
    events = read_csv(event_path)
    if any(int(e.get("season") or 0) == HOLDOUT for e in events):
        raise SystemExit("FAIL 2025 event row detected")
    event_groups = eu.aggregate_event_player_games(events)
    expanded, xa = eu.build_expanded_rows(
        snap_rows, event_groups, pfr_to_gsis=pfr_to_gsis, player_meta=player_meta, allowed_game_ids=set(games)
    )
    # Backfill game metadata for event-only rows and validate no holdout/postseason.
    for r in expanded:
        gm = games.get(r["game_id"], {})
        if not r.get("season"):
            r["season"] = int(gm.get("season") or 0)
            r["week"] = int(gm.get("week") or 0)
            r["game_type"] = gm.get("game_type") or ""
            if not r.get("opponent"):
                team = r.get("team")
                r["opponent"] = gm.get("away_team") if team == gm.get("home_team") else gm.get("home_team")
        if int(r.get("season") or 0) == HOLDOUT:
            raise SystemExit("FAIL 2025 expanded row detected")
        if r.get("game_type") != "REG":
            raise SystemExit("FAIL postseason/non-REG expanded row detected")

    expected_standard = sum(int(e.get("combined_credit_unit") or 1) for e in events if int(e.get("is_standard_def_scrimmage_credit") or 0))
    observed_standard = sum(int(r.get("combined_standard_def_scrimmage") or 0) for r in expanded)
    if expected_standard != observed_standard:
        raise SystemExit(f"FAIL standard-credit reconciliation {observed_standard} != {expected_standard}")

    resolved_snap_rows = [r for r in expanded if r.get("exposure_source") == "SNAP_COUNTS" and int(r.get("identity_resolved") or 0)]
    zero_rows = [r for r in resolved_snap_rows if int(r.get("combined_standard_def_scrimmage") or 0) == 0]

    outbase = root / "data/normalized/nfl/omega_tackle_exposure"
    out = outbase / sid
    if out.exists():
        raise SystemExit(f"Refusing overwrite immutable OMEGA exposure universe: {out}")
    staging = outbase / ("." + sid + ".staging")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        write_csv(staging / "omega_tackle_exposure_player_games.csv", expanded)
        audit = {
            "schemaVersion": SCHEMA,
            "generatedAt": now(),
            "sourcePhase1SnapshotId": sid,
            "sourceOmegaFoundationSchema": fa.get("schemaVersion"),
            "developmentSeasons": list(range(2016, 2025)),
            "omegaHoldoutSeason": HOLDOUT,
            "omegaHoldoutRowsRead": 0,
            "postseasonPolicy": "EXCLUDED_SEPARATE_REGIME",
            "marketFieldsRead": 0,
            "oddsPapiRequests": 0,
            "modelFitPerformed": False,
            "snapSource": {**snap_audit, "manifest": str(snap_manifest_path.relative_to(root))},
            "exposure": xa,
            "resolvedSnapRows": len(resolved_snap_rows),
            "zeroCreditResolvedSnapRows": len(zero_rows),
            "zeroCreditResolvedSnapRatePct": round(100.0 * len(zero_rows) / len(resolved_snap_rows), 4) if resolved_snap_rows else None,
            "standardCreditReconciliation": {
                "eventLedger": expected_standard,
                "expandedUniverse": observed_standard,
                "pass": expected_standard == observed_standard,
            },
            "integrity": {
                "zeroOutcomeRowsIncluded": len(zero_rows) > 0,
                "eventLedgerUnmodified": True,
                "holdoutUnopened": True,
                "marketIsolation": True,
                "postseasonSeparated": True,
            },
        }
        (staging / "OMEGA_TACKLE_EXPOSURE_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        md = [
            "# OMEGA Tackle Model 0.1.1 — Exposure Universe Audit", "",
            f"Generated: {audit['generatedAt']}", "",
            "**FOUNDATION HARDENING ONLY. NO TACKLE MODEL IS FIT IN THIS PHASE.**", "",
            "## Why this patch exists", "",
            "OMEGA 0.1 correctly reconstructed tackle-credit events, but its player-game aggregation was event-seeded: a defender with defensive snaps and zero tackle credits had no row. Any player-level tackle model fit directly on that table would therefore condition on receiving a tackle and bias expected counts upward. 0.1.1 builds the full defensive exposure universe from snap counts and left-joins observed credits, creating explicit zero outcomes.", "",
            "## Integrity", "",
            f"- Source OMEGA foundation: `{sid}`",
            "- Development universe: **2016–2024 REG only**",
            "- OMEGA 2025 rows read: **0**",
            "- Postseason: **EXCLUDED**",
            "- Market fields read: **0**",
            "- OddsPapi requests: **0**",
            "- Model fitting: **NO**", "",
            "## Exposure universe", "",
            f"- Defensive-snap rows encountered: **{xa['snapDefensiveExposureRows']}**",
            f"- Defensive-snap rows with resolved GSIS identity: **{xa['resolvedSnapDefensiveExposureRows']}**",
            f"- Unresolved defensive-snap identities: **{xa['unresolvedSnapDefensiveExposureRows']}**",
            f"- Event-positive rows with no defensive snap join: **{xa['eventOnlyPositiveRows']}**",
            f"- Expanded player-game rows: **{xa['expandedRows']}**",
            f"- Fit-eligible resolved defensive-snap rows: **{xa['fitEligibleRows']}**",
            f"- Explicit zero-standard-credit player-games: **{len(zero_rows)}**",
            f"- Zero-standard-credit rate among resolved snap rows: **{audit['zeroCreditResolvedSnapRatePct']}%**", "",
            "## Reconciliation", "",
            f"- Standard defensive scrimmage credits in immutable event ledger: **{expected_standard}**",
            f"- Standard defensive scrimmage credits after expanded-universe join: **{observed_standard}**",
            f"- Reconciliation: **{'PASS' if expected_standard == observed_standard else 'FAIL'}**", "",
            "## Next gate", "",
            "Only after this audit passes should OMEGA 0.2 fit an xTO/xTC baseline. Player-level training must use `eligible_standard_rate_fit == 1`, which includes explicit zero-credit games and excludes event-only rows without snap exposure.", "",
        ]
        (staging / "OMEGA_TACKLE_EXPOSURE_AUDIT.md").write_text("\n".join(md), encoding="utf-8")
        files = []
        for p in sorted(staging.iterdir()):
            if p.is_file():
                files.append({"filename": p.name, "sha256": sha256_file(p), "bytes": p.stat().st_size})
        (staging / "OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion": SCHEMA, "sourcePhase1SnapshotId": sid, "createdAt": now(), "files": files}, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, out)
        (root / "data/normalized/nfl/CURRENT_OMEGA_TACKLE_EXPOSURE").write_text(sid + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print("OMEGA TACKLE MODEL 0.1.1 — EXPOSURE UNIVERSE HARDENING")
    print(f"PASS source foundation: {sid}")
    print(f"PASS expanded rows: {len(expanded)}")
    print(f"PASS explicit zero-credit defensive player-games: {len(zero_rows)}")
    print(f"PASS standard-credit reconciliation: {observed_standard}/{expected_standard}")
    print("PASS OMEGA 2025 holdout untouched · market fields 0 · OddsPapi 0 · model fit NO")
    print(f"REPORT: {out/'OMEGA_TACKLE_EXPOSURE_AUDIT.md'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import argparse
import csv
import hashlib
import json
import os
import uuid

VERSION = "0.34.2"
SCHEMA = "OMEGA_WEEK2_GAMEDAY_INACTIVE_STARTER_OVERLAY_0.34.2"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_aware(v: str) -> datetime:
    s = str(v or "").strip()
    if not s:
        raise ValueError("captured-at is required")
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("captured-at must include timezone")
    return d


def parse_pair(v: str, label: str) -> tuple[str, str]:
    parts = str(v).split("|", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise ValueError(f"{label} must be TEAM|VALUE")
    return parts[0].strip().upper(), parts[1].strip()


def parse_game_teams(game_id: str) -> tuple[str, str]:
    parts = str(game_id).strip().split("_")
    if len(parts) != 4:
        raise ValueError("game-id must look like 2026_02_DET_BUF")
    return parts[2].upper(), parts[3].upper()


def validate_url(url: str) -> str:
    u = str(url or "").strip()
    p = urlparse(u)
    if p.scheme != "https" or not p.netloc:
        raise ValueError(f"authoritative source must be https URL: {u}")
    return u


def latest_comparison(root: Path) -> Path:
    base = root / "data/prospective/nfl/omega_week2_market_comparison_0341"
    paths = sorted(base.glob("*/OMEGA_0.34.1_WEEK2_MARKET_COMPARISON.csv"))
    if not paths:
        raise FileNotFoundError("no OMEGA 0.34.1 comparison found")
    return paths[-1]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
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


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def classify(row: dict[str, str], *, final_inactives: bool, inactive: bool, starter_confirmed: bool) -> tuple[str, str]:
    quote_class = str(row.get("market_quote_classification") or "")
    base_status = str(row.get("operational_status") or "")
    role_state = str(row.get("role_state") or "")

    overlay_role = role_state
    if role_state == "STARTER_CONFLICT_REVIEW" and starter_confirmed:
        overlay_role = "STARTER_CONFLICT_RESOLVED_TEAM_DEPTH_CHART"

    if inactive:
        return overlay_role, "NO_ACTION_CONFIRMED_INACTIVE"
    if quote_class == "REFERENCE_ONLY_NON_EXECUTABLE":
        return overlay_role, "REFERENCE_ONLY_NOT_EXECUTABLE"
    if base_status == "NO_ACTION_SETTLEMENT_UNRESOLVED":
        return overlay_role, "NO_ACTION_SETTLEMENT_UNRESOLVED"
    if role_state == "REVIEW_BACKUP_CONFLICT":
        return overlay_role, "QUARANTINED_BACKUP_CONFLICT"
    if role_state == "STARTER_CONFLICT_REVIEW" and not starter_confirmed:
        return overlay_role, "REVIEW_STARTER_CONFLICT"
    if not final_inactives:
        if starter_confirmed and role_state == "STARTER_CONFLICT_REVIEW":
            return overlay_role, "PRELIMINARY_NO_AUTHORITATIVE_INACTIVE_OVERLAY_STARTER_CONFIRMED"
        return overlay_role, "PRELIMINARY_NO_AUTHORITATIVE_INACTIVE_OVERLAY"
    return overlay_role, "MARKET_ELIGIBLE_CONTROL_TRACK"


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply immutable official starter/inactive overlay downstream of frozen OMEGA Week 2")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--game-id", required=True)
    ap.add_argument("--captured-at", required=True, help="timezone-aware time the authoritative sources were observed")
    ap.add_argument("--inactive-list-status", required=True, choices=["PENDING", "FINAL"])
    ap.add_argument("--comparison-path", default="")
    ap.add_argument("--starter", action="append", default=[], help="repeat TEAM|Player Name; exact match only")
    ap.add_argument("--starter-source", action="append", default=[], help="repeat TEAM|https://official-team-depth-chart")
    ap.add_argument("--inactive", action="append", default=[], help="repeat TEAM|Player Name; exact match only; FINAL only")
    ap.add_argument("--inactive-source", action="append", default=[], help="repeat TEAM|https://official-inactive-list; FINAL requires both teams")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    away, home = parse_game_teams(args.game_id)
    teams = {away, home}
    captured = parse_aware(args.captured_at)
    now = datetime.now(timezone.utc)
    if captured.astimezone(timezone.utc) > now.replace(microsecond=999999):
        raise ValueError("captured-at cannot be in the future")

    starter_names: set[tuple[str, str]] = set()
    for raw in args.starter:
        team, name = parse_pair(raw, "starter")
        if team not in teams:
            raise ValueError(f"starter team {team} not in {args.game_id}")
        starter_names.add((team, name.casefold()))

    starter_sources: dict[str, list[str]] = {t: [] for t in teams}
    for raw in args.starter_source:
        team, url = parse_pair(raw, "starter-source")
        if team not in teams:
            raise ValueError(f"starter-source team {team} not in {args.game_id}")
        starter_sources[team].append(validate_url(url))
    for team, _name in starter_names:
        if not starter_sources.get(team):
            raise ValueError(f"starter confirmation for {team} requires starter-source")

    inactive_names: set[tuple[str, str]] = set()
    for raw in args.inactive:
        team, name = parse_pair(raw, "inactive")
        if team not in teams:
            raise ValueError(f"inactive team {team} not in {args.game_id}")
        inactive_names.add((team, name.casefold()))

    inactive_sources: dict[str, list[str]] = {t: [] for t in teams}
    for raw in args.inactive_source:
        team, url = parse_pair(raw, "inactive-source")
        if team not in teams:
            raise ValueError(f"inactive-source team {team} not in {args.game_id}")
        inactive_sources[team].append(validate_url(url))

    final_inactives = args.inactive_list_status == "FINAL"
    if not final_inactives and (inactive_names or any(inactive_sources.values())):
        raise ValueError("PENDING inactive-list-status cannot claim inactive names/sources")
    if final_inactives:
        missing = sorted(t for t in teams if not inactive_sources.get(t))
        if missing:
            raise ValueError("FINAL inactive list requires authoritative source for both teams: " + ", ".join(missing))

    comparison = Path(args.comparison_path).expanduser().resolve() if args.comparison_path else latest_comparison(root)
    if not comparison.exists():
        raise FileNotFoundError(comparison)
    source_rows = read_csv(comparison)
    rows = [r for r in source_rows if str(r.get("game_id") or "") == args.game_id]
    if not rows:
        raise ValueError(f"comparison contains no rows for {args.game_id}")

    out: list[dict] = []
    for row in rows:
        team = str(row.get("team") or "").upper()
        name = str(row.get("player_name") or "")
        key = (team, name.casefold())
        starter_confirmed = key in starter_names
        inactive = final_inactives and key in inactive_names
        overlay_role, status = classify(row, final_inactives=final_inactives, inactive=inactive, starter_confirmed=starter_confirmed)
        rec = dict(row)
        rec.update({
            "gameday_overlay_version": VERSION,
            "gameday_overlay_captured_at": captured.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "inactive_list_status": args.inactive_list_status,
            "inactive_verified": "TRUE" if final_inactives else "FALSE",
            "confirmed_inactive": "TRUE" if inactive else "FALSE",
            "starter_confirmed_exact": "TRUE" if starter_confirmed else "FALSE",
            "overlay_role_state": overlay_role,
            "overlay_operational_status": status,
            "market_execution_eligible": "FALSE",
            "frozen_omega_mutation": "FALSE",
        })
        out.append(rec)

    run_id = now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/prospective/nfl/omega_week2_gameday_overlay_0342" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    source_payload = {
        "schema": SCHEMA,
        "version": VERSION,
        "createdAt": now.isoformat(),
        "gameId": args.game_id,
        "capturedAt": captured.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "inactiveListStatus": args.inactive_list_status,
        "starterConfirmations": sorted([{"team": t, "playerNameCasefold": n} for t, n in starter_names], key=lambda x: (x["team"], x["playerNameCasefold"])),
        "starterSources": starter_sources,
        "inactivePlayers": sorted([{"team": t, "playerNameCasefold": n} for t, n in inactive_names], key=lambda x: (x["team"], x["playerNameCasefold"])),
        "inactiveSources": inactive_sources,
        "sourceComparison": str(comparison.relative_to(root) if comparison.is_relative_to(root) else comparison),
        "sourceComparisonSha256": sha256_file(comparison),
        "exactIdentityOnly": True,
        "fuzzyMatching": False,
        "frozenOmegaMutation": False,
    }
    source_path = out_dir / "OMEGA_0.34.2_GAMEDAY_SOURCE_OVERLAY.json"
    source_path.write_text(json.dumps(source_payload, indent=2) + "\n", encoding="utf-8")

    csv_path = out_dir / "OMEGA_0.34.2_GAMEDAY_MARKET_COMPARISON.csv"
    write_csv(csv_path, out)
    counts: dict[str, int] = {}
    for r in out:
        s = str(r["overlay_operational_status"])
        counts[s] = counts.get(s, 0) + 1
    audit = {
        "schema": SCHEMA,
        "version": VERSION,
        "createdAt": now.isoformat(),
        "gameId": args.game_id,
        "rows": len(out),
        "inactiveListStatus": args.inactive_list_status,
        "confirmedInactiveRows": sum(r["confirmed_inactive"] == "TRUE" for r in out),
        "starterConfirmedRows": sum(r["starter_confirmed_exact"] == "TRUE" for r in out),
        "operationalStatusCounts": counts,
        "marketEligibleRows": sum(r["overlay_operational_status"] == "MARKET_ELIGIBLE_CONTROL_TRACK" for r in out),
        "marketExecutionEligible": False,
        "marketExecutionReason": "DIRECT_BOOK_CONFIRMATION_AND_SETTLEMENT_POLICY_STILL_REQUIRED",
        "sourceOverlaySha256": sha256_file(source_path),
        "comparisonSha256": sha256_file(csv_path),
        "frozenOmegaMutation": False,
        "nextGate": "FINAL_OFFICIAL_INACTIVES_THEN_DIRECT_BOOK_CONFIRMATION" if not final_inactives else "DIRECT_BOOK_CONFIRMATION_AND_PREGAME_MARKET_SNAPSHOT",
    }
    audit_path = out_dir / "OMEGA_0.34.2_GAMEDAY_OVERLAY_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    rel = str(out_dir.relative_to(root))
    atomic_pointer(root / "data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_GAMEDAY_OVERLAY_0342", rel)
    atomic_pointer(root / f"data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_GAMEDAY_OVERLAY_0342_{args.game_id}", rel)

    print("\nOMEGA 0.34.2 — GAME-DAY INACTIVE / STARTER OVERLAY")
    print(f"Game: {args.game_id} · rows {len(out)} · inactive list {args.inactive_list_status}")
    print(f"Starter confirmations: {sum(r['starter_confirmed_exact']=='TRUE' for r in out)} · confirmed inactive rows: {sum(r['confirmed_inactive']=='TRUE' for r in out)}")
    print("Operational status:", json.dumps(counts, sort_keys=True))
    print("Frozen OMEGA mutation: NO · exact identity only · fuzzy matching NO")
    print("Market execution eligible: NO")
    print(f"Overlay: {csv_path}")
    print(f"Audit: {audit_path}")
    print(f"NEXT GATE: {audit['nextGate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

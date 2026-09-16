#!/usr/bin/env python3
"""OMEGA 0.34 — Week 2 downstream market comparison for frozen control + role-point shadow.

Read-only downstream comparison. This script never mutates frozen OMEGA and never
promotes the ROLE_POINT probability shadow. It compares a pregame raw tackle market
snapshot against:
  * FROZEN_OMEGA_CONTROL probabilities (decision/control probability track), and
  * CURRENT_ROLE_POINT_SHADOW probabilities (research-only cross-check).

Operational policy:
  * raw market snapshots must contain no model-derived fields;
  * only T+A half-lines 0.5..14.5 are supported;
  * deterministic identity bridge only (reuses OMEGA 0.18 helpers; no fuzzy matching);
  * post-kickoff market rows are excluded from comparison;
  * STARTER_CONFLICT rows require review;
  * REVIEW_BACKUP_CONFLICT rows remain quarantined;
  * without authoritative game-day inactive verification, all rows remain preliminary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import shutil

SCHEMA = "OMEGA_WEEK2_DUAL_TRACK_MARKET_COMPARISON_0.34.0"
VERSION = "0.34.0"
SEASON = 2026
WEEK = 2


def nowdt() -> datetime:
    return datetime.now(timezone.utc)


def now() -> str:
    return nowdt().isoformat(timespec="seconds").replace("+00:00", "Z")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def rcsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def wcsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    if not fields:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def num(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def truthy(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "y", "t", "ready", "pass"}


def parse_ts(v: Any) -> datetime | None:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_legacy_helpers(root: Path):
    p = root / "scripts/nfl/compare_omega_tackle_market_0180.py"
    spec = importlib.util.spec_from_file_location("omega018_market_helpers", p)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FAIL cannot load OMEGA 0.18 identity/market helpers: {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def freeze_bundle(root: Path) -> tuple[str, Path, dict[str, Any], Path, str]:
    ptr = root / "data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_DUAL_TRACK_FREEZE"
    if not ptr.exists():
        raise SystemExit("FAIL current Week 2 dual-track freeze pointer missing")
    fid = ptr.read_text(encoding="utf-8").strip()
    d = root / "data/prospective/nfl/omega_week2_dual_track_0330" / fid
    dual = d / "OMEGA_0.33_WEEK2_DUAL_TRACK.csv"
    manifest = d / "OMEGA_0.33_WEEK2_MANIFEST.json"
    hashes = d / "OMEGA_OUTPUT_HASHES.json"
    for p in (dual, manifest, hashes):
        if not p.exists():
            raise SystemExit(f"FAIL Week 2 freeze bundle incomplete: {p}")
    hm = json.loads(hashes.read_text(encoding="utf-8"))
    for p in (dual, manifest):
        expected = str(hm.get(p.name) or "")
        if not expected or sha(p) != expected:
            raise SystemExit(f"FAIL Week 2 freeze hash mismatch: {p.name}")
    mm = json.loads(manifest.read_text(encoding="utf-8"))
    return fid, d, mm, dual, sha(dual)


def market_bundle(root: Path) -> tuple[str, Path, dict[str, Any], Path, str]:
    ptr = root / "data/raw/nfl/omega/CURRENT_MARKET_SNAPSHOT"
    if not ptr.exists():
        raise SystemExit("FAIL no current raw market snapshot pointer; capture Week 2 market first")
    mid = ptr.read_text(encoding="utf-8").strip()
    d = root / "data/raw/nfl/omega/market_snapshots" / mid
    market = d / "normalized_market_rows.csv"
    manifest = d / "MARKET_SNAPSHOT_MANIFEST.json"
    for p in (market, manifest):
        if not p.exists():
            raise SystemExit(f"FAIL market snapshot incomplete: {p}")
    mm = json.loads(manifest.read_text(encoding="utf-8"))
    if mm.get("modelFieldsPresent") is not False or int(mm.get("oddsPapiRequests") or 0) != 0:
        raise SystemExit("FAIL raw-market integrity contract")
    return mid, d, mm, market, sha(market)


def model_probability(row: dict[str, Any], prefix: str, side: str, line: float) -> float:
    tag = str(float(line)).replace(".", "_")
    key = f"{prefix}p_{side.lower()}_{tag}"
    x = num(row.get(key))
    if x is None or x < 0 or x > 1:
        raise SystemExit(f"FAIL missing/invalid model probability {key} for {row.get('player_name')}")
    return x


def best_side(over_ev: float | None, under_ev: float | None) -> tuple[str, float | None]:
    vals = [("OVER", over_ev), ("UNDER", under_ev)]
    vals = [(s, v) for s, v in vals if v is not None]
    if not vals:
        return "", None
    return max(vals, key=lambda z: z[1])


def status_for(row: dict[str, Any], settlement_resolved: bool) -> str:
    trust = str(row.get("role_state") or "")
    if not settlement_resolved:
        return "NO_ACTION_SETTLEMENT_UNRESOLVED"
    if trust == "REVIEW_BACKUP_CONFLICT":
        return "QUARANTINED_BACKUP_CONFLICT"
    if trust == "STARTER_CONFLICT_REVIEW":
        return "REVIEW_STARTER_CONFLICT"
    if not truthy(row.get("verified_ready")):
        return "PRELIMINARY_NO_AUTHORITATIVE_INACTIVE_OVERLAY"
    return "MARKET_ELIGIBLE_CONTROL_TRACK"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    h = load_legacy_helpers(root)

    fid, fdir, fmeta, dual_path, dual_sha = freeze_bundle(root)
    mid, mdir, mmeta, market_path, market_sha = market_bundle(root)
    forecasts = rcsv(dual_path)
    if len(forecasts) != 800:
        raise SystemExit(f"FAIL unexpected Week 2 forecast count {len(forecasts)}; expected 800")
    if any(int(float(r.get("season") or 0)) != SEASON or int(float(r.get("week") or 0)) != WEEK for r in forecasts):
        raise SystemExit("FAIL non-2026-Week-2 row in dual-track freeze")

    indexes = h.build_indexes(forecasts)
    market_rows = [r for r in rcsv(market_path) if str(r.get("market_kind") or "").strip().lower() == "tackles_assists"]
    if not market_rows:
        raise SystemExit("FAIL current market snapshot has no tackles_assists rows")

    out: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    postkick: list[dict[str, Any]] = []
    methods: dict[str, int] = {}

    for m in market_rows:
        cand, method = h.resolve_market_identity(m, indexes)
        methods[method] = methods.get(method, 0) + 1
        if len(cand) == 0:
            unmatched.append({
                "player_name": m.get("player_name"), "player_team": m.get("player_team"),
                "opponent": m.get("opponent"), "book": m.get("book"), "line": m.get("line"),
                "join_method": method,
            })
            continue
        if len(cand) != 1:
            ambiguous.append({
                "player_name": m.get("player_name"), "player_team": m.get("player_team"),
                "book": m.get("book"), "line": m.get("line"), "candidate_count": len(cand),
                "candidate_names": "|".join(str(x.get("player_name") or "") for x in cand),
                "candidate_teams": "|".join(str(x.get("team") or "") for x in cand),
                "join_method": method,
            })
            continue

        p = cand[0]
        line = num(m.get("line"))
        if line is None or not h.is_half(line) or line < 0.5 or line > 14.5:
            unsupported.append({"player_name": m.get("player_name"), "book": m.get("book"), "line": m.get("line"), "reason": "UNSUPPORTED_LINE"})
            continue

        mt = parse_ts(m.get("captured_at")) or parse_ts(mmeta.get("createdAt"))
        ko = parse_ts(p.get("kickoff_utc"))
        if mt is None or ko is None:
            postkick.append({"player_name": m.get("player_name"), "book": m.get("book"), "line": line, "reason": "MISSING_TIME", "captured_at": m.get("captured_at"), "kickoff_utc": p.get("kickoff_utc")})
            continue
        if mt >= ko:
            postkick.append({"player_name": m.get("player_name"), "book": m.get("book"), "line": line, "reason": "AT_OR_AFTER_KICKOFF", "captured_at": mt.isoformat(), "kickoff_utc": ko.isoformat()})
            continue

        cpo = model_probability(p, "control_", "over", line)
        cpu = model_probability(p, "control_", "under", line)
        rpo = model_probability(p, "role_shadow_", "over", line)
        rpu = model_probability(p, "role_shadow_", "under", line)

        over_odds = num(m.get("over_odds_american"))
        under_odds = num(m.get("under_odds_american"))
        one_side = str(m.get("one_sided_side") or "").strip().upper()
        one_odds = num(m.get("one_sided_odds_american"))
        two_sided = over_odds is not None and under_odds is not None

        market_no_vig_over = market_no_vig_under = None
        control_over_ev = control_under_ev = role_over_ev = role_under_ev = None
        if two_sided:
            market_no_vig_over, market_no_vig_under = h.devig(over_odds, under_odds)
            control_over_ev = h.roi(cpo, over_odds)
            control_under_ev = h.roi(cpu, under_odds)
            role_over_ev = h.roi(rpo, over_odds)
            role_under_ev = h.roi(rpu, under_odds)
        elif one_side in {"OVER", "UNDER"} and one_odds is not None:
            if one_side == "OVER":
                control_over_ev = h.roi(cpo, one_odds); role_over_ev = h.roi(rpo, one_odds)
            else:
                control_under_ev = h.roi(cpu, one_odds); role_under_ev = h.roi(rpu, one_odds)
        else:
            unsupported.append({"player_name": m.get("player_name"), "book": m.get("book"), "line": line, "reason": "NO_EXECUTABLE_PRICE"})
            continue

        cb_side, cb_ev = best_side(control_over_ev, control_under_ev)
        rb_side, rb_ev = best_side(role_over_ev, role_under_ev)
        policy = h.settlement_policy_for_book(m.get("book"))
        resolved = policy.get("status") == "RESOLVED"
        op_status = status_for(p, resolved)

        rec = {
            "comparison_version": VERSION,
            "freeze_id": fid, "freeze_sha256": dual_sha,
            "market_snapshot_id": mid, "market_snapshot_sha256": market_sha,
            "market_captured_at": mt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "game_id": p.get("game_id"), "kickoff_utc": p.get("kickoff_utc"),
            "player_id": p.get("player_id"), "player_name": p.get("player_name"),
            "team": p.get("team"), "opponent": p.get("opponent"), "position_group": p.get("position_group"),
            "book": m.get("book"), "market_kind": "tackles_assists", "line": line,
            "over_odds_american": m.get("over_odds_american"), "under_odds_american": m.get("under_odds_american"),
            "one_sided_side": one_side, "one_sided_odds_american": m.get("one_sided_odds_american"),
            "two_sided": "TRUE" if two_sided else "FALSE",
            "market_no_vig_over": market_no_vig_over, "market_no_vig_under": market_no_vig_under,
            "control_xtc": p.get("control_xtc"), "role_point_xtc": p.get("role_point_xtc"),
            "control_h012_snap_share": p.get("control_h012_snap_share"), "role_point_snap_share": p.get("role_point_snap_share"),
            "control_p_over": cpo, "control_p_under": cpu,
            "role_shadow_p_over": rpo, "role_shadow_p_under": rpu,
            "control_over_ev": control_over_ev, "control_under_ev": control_under_ev,
            "role_shadow_over_ev": role_over_ev, "role_shadow_under_ev": role_under_ev,
            "control_best_side": cb_side, "control_best_ev": cb_ev,
            "role_shadow_best_side": rb_side, "role_shadow_best_ev": rb_ev,
            "tracks_agree_side": "TRUE" if cb_side and cb_side == rb_side else "FALSE",
            "role_state": p.get("role_state"),
            "week2_preferred_exposure_challenger": p.get("week2_preferred_exposure_challenger"),
            "starter_conflict_warning": p.get("starter_conflict_warning"),
            "backup_conflict_quarantine": p.get("backup_conflict_quarantine"),
            "verified_ready": p.get("verified_ready"), "verified_block_reason": p.get("verified_block_reason"),
            "settlement_status": policy.get("status"), "settlement_scope": policy.get("settlement_scope"),
            "includes_special_teams": policy.get("includes_special_teams"),
            "identity_join_method": method,
            "decision_probability_track": "FROZEN_OMEGA_CONTROL",
            "role_probability_status": "SHADOW_ONLY_NOT_PROMOTED",
            "operational_status": op_status,
        }
        if two_sided:
            rec["control_edge_vs_novig_over"] = cpo - float(market_no_vig_over)
            rec["control_edge_vs_novig_under"] = cpu - float(market_no_vig_under)
            rec["role_shadow_edge_vs_novig_over"] = rpo - float(market_no_vig_over)
            rec["role_shadow_edge_vs_novig_under"] = rpu - float(market_no_vig_under)
        out.append(rec)

    if not out:
        raise SystemExit(
            "FAIL no valid Week 2 T+A comparisons produced. The current market snapshot may be stale/Week 1, "
            "or no rows matched the frozen Week 2 universe. Capture a fresh Week 2 tackle market snapshot first."
        )

    stamp = nowdt().strftime("%Y%m%dT%H%M%SZ")
    digest_seed = hashlib.sha256((dual_sha + market_sha).encode()).hexdigest()[:8]
    cid = f"{stamp}_{digest_seed}"
    base = root / "data/prospective/nfl/omega_week2_market_comparison_0340"
    staging = base / ("." + cid + ".staging")
    final = base / cid
    if final.exists():
        raise SystemExit(f"FAIL immutable comparison already exists: {final}")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        comparison_path = staging / "OMEGA_0.34_WEEK2_MARKET_COMPARISON.csv"
        wcsv(comparison_path, out)
        wcsv(staging / "OMEGA_0.34_UNMATCHED.csv", unmatched)
        wcsv(staging / "OMEGA_0.34_AMBIGUOUS.csv", ambiguous)
        wcsv(staging / "OMEGA_0.34_UNSUPPORTED.csv", unsupported)
        wcsv(staging / "OMEGA_0.34_POSTKICK_EXCLUDED.csv", postkick)

        trust_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        agree = 0
        for r in out:
            t = str(r.get("role_state") or "")
            s = str(r.get("operational_status") or "")
            trust_counts[t] = trust_counts.get(t, 0) + 1
            status_counts[s] = status_counts.get(s, 0) + 1
            agree += int(r.get("tracks_agree_side") == "TRUE")

        audit = {
            "schemaVersion": SCHEMA,
            "comparisonId": cid,
            "createdAt": now(),
            "season": SEASON, "week": WEEK,
            "freezeId": fid, "freezeSha256": dual_sha,
            "marketSnapshotId": mid, "marketSnapshotSha256": market_sha,
            "comparisonRows": len(out),
            "twoSidedRows": sum(r.get("two_sided") == "TRUE" for r in out),
            "oneSidedRows": sum(r.get("two_sided") != "TRUE" for r in out),
            "unmatchedRows": len(unmatched), "ambiguousRows": len(ambiguous),
            "unsupportedRows": len(unsupported), "postKickExcludedRows": len(postkick),
            "identityJoinMethods": methods,
            "trustStateCounts": trust_counts,
            "operationalStatusCounts": status_counts,
            "trackSideAgreementRows": agree,
            "decisionProbabilityTrack": "FROZEN_OMEGA_CONTROL",
            "roleProbabilityStatus": "SHADOW_ONLY_NOT_PROMOTED",
            "authoritativeInactiveOverlayRequiredForMarketEligible": True,
            "marketFieldsReadDownstreamOnly": True,
            "modelRefits": 0, "modelWrites": 0, "oddsPapiRequests": 0,
        }
        audit_path = staging / "OMEGA_0.34_WEEK2_MARKET_COMPARISON_AUDIT.json"
        audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        hashes = {p.name: sha(p) for p in staging.iterdir() if p.is_file()}
        (staging / "OMEGA_OUTPUT_HASHES.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, final)
        atomic_text(root / "data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_MARKET_COMPARISON", cid + "\n")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    ranked = sorted(out, key=lambda r: float(r.get("control_best_ev") if r.get("control_best_ev") is not None else -999), reverse=True)
    print("OMEGA 0.34 — WEEK 2 DUAL-TRACK DOWNSTREAM MARKET COMPARISON")
    print(f"PASS freeze {fid} · market {mid} · comparison rows {len(out)}")
    print(f"PASS two-sided {sum(r.get('two_sided')=='TRUE' for r in out)} · one-sided {sum(r.get('two_sided')!='TRUE' for r in out)}")
    print(f"PASS unmatched {len(unmatched)} · ambiguous {len(ambiguous)} · unsupported {len(unsupported)} · postkick excluded {len(postkick)}")
    print("PASS control = decision probability track · role point probability = SHADOW ONLY")
    print("PASS no fuzzy identity · market read downstream only · model refits/writes 0")
    print("OPERATIONAL STATUS:", json.dumps(status_counts, sort_keys=True))
    print("TOP CONTROL EV ROWS (PRELIMINARY UNTIL STATUS ALLOWS):")
    for r in ranked[:15]:
        ev = r.get("control_best_ev")
        evs = "NA" if ev is None else f"{100*float(ev):+.1f}%"
        rev = r.get("role_shadow_best_ev")
        revs = "NA" if rev is None else f"{100*float(rev):+.1f}%"
        print(
            f"  {r['game_id']} · {r['player_name']} {r['control_best_side']} {r['line']} · "
            f"CONTROL EV {evs} · ROLE-shadow {r['role_shadow_best_side']} {revs} · "
            f"{r['role_state']} · {r['operational_status']}"
        )
    print(f"REPORT: {final/'OMEGA_0.34_WEEK2_MARKET_COMPARISON_AUDIT.json'}")
    print(f"COMPARISON: {final/'OMEGA_0.34_WEEK2_MARKET_COMPARISON.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

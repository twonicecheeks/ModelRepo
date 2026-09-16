#!/usr/bin/env python3
"""OMEGA 0.35 — Week 2 executable-price verification queue.

Read-only downstream triage over the immutable OMEGA 0.34.1 comparison.
No model fitting, probability changes, market mutation, or bet selection occurs here.

Purpose:
  * keep PropsMadness referenceBet/noOffer quotes research-only;
  * prioritize which rows should be checked at the actual sportsbook;
  * keep STARTER_CONFLICT and BACKUP_CONFLICT rows visibly separated;
  * preserve frozen control as the decision probability track and role-point as shadow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import csv
import hashlib
import json
import math
import os
import shutil

SCHEMA = "OMEGA_WEEK2_EXECUTABLE_VERIFICATION_QUEUE_0.35.0"
VERSION = "0.35.0"


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


def wcsv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    if fields is None:
        fields = []
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


def fair_american(p: float | None) -> float | None:
    if p is None or not (0.0 < p < 1.0):
        return None
    if p >= 0.5:
        return -100.0 * p / (1.0 - p)
    return 100.0 * (1.0 - p) / p


def comparison_bundle(root: Path) -> tuple[str, Path, Path, dict[str, Any]]:
    ptr = root / "data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_MARKET_COMPARISON"
    if not ptr.exists():
        raise SystemExit("FAIL current Week 2 market comparison pointer missing")
    cid = ptr.read_text(encoding="utf-8").strip()
    candidates = [
        root / "data/prospective/nfl/omega_week2_market_comparison_0341" / cid,
        root / "data/prospective/nfl/omega_week2_market_comparison_0340" / cid,
    ]
    d = next((x for x in candidates if x.exists()), None)
    if d is None:
        raise SystemExit(f"FAIL comparison bundle {cid} not found in 0.34.1/0.34.0 directories")
    csv_candidates = [d / "OMEGA_0.34.1_WEEK2_MARKET_COMPARISON.csv", d / "OMEGA_0.34_WEEK2_MARKET_COMPARISON.csv"]
    audit_candidates = [d / "OMEGA_0.34.1_WEEK2_MARKET_COMPARISON_AUDIT.json", d / "OMEGA_0.34_WEEK2_MARKET_COMPARISON_AUDIT.json"]
    cp = next((x for x in csv_candidates if x.exists()), None)
    ap = next((x for x in audit_candidates if x.exists()), None)
    hp = d / "OMEGA_OUTPUT_HASHES.json"
    if cp is None or ap is None or not hp.exists():
        raise SystemExit(f"FAIL incomplete comparison bundle: {d}")
    hashes = json.loads(hp.read_text(encoding="utf-8"))
    expected = str(hashes.get(cp.name) or "")
    if not expected or sha(cp) != expected:
        raise SystemExit(f"FAIL comparison CSV hash mismatch: {cp}")
    audit = json.loads(ap.read_text(encoding="utf-8"))
    if audit.get("decisionProbabilityTrack") != "FROZEN_OMEGA_CONTROL":
        raise SystemExit("FAIL unexpected decision probability track")
    if audit.get("roleProbabilityStatus") != "SHADOW_ONLY_NOT_PROMOTED":
        raise SystemExit("FAIL role probability is not shadow-only")
    return cid, d, cp, audit


def price_for_side(r: dict[str, str], side: str) -> float | None:
    if side == "OVER":
        x = num(r.get("over_odds_american"))
        if x is not None:
            return x
    if side == "UNDER":
        x = num(r.get("under_odds_american"))
        if x is not None:
            return x
    if str(r.get("one_sided_side") or "").strip().upper() == side:
        return num(r.get("one_sided_odds_american"))
    return None


def prob_for_side(r: dict[str, str], prefix: str, side: str) -> float | None:
    key = f"{prefix}p_{side.lower()}"
    return num(r.get(key))


def ev_for_side(r: dict[str, str], prefix: str, side: str) -> float | None:
    key = f"{prefix}{side.lower()}_ev"
    return num(r.get(key))


def queue_class(r: dict[str, str]) -> str:
    role = str(r.get("role_state") or "")
    agree = str(r.get("tracks_agree_side") or "").upper() == "TRUE"
    ev = num(r.get("control_best_ev"))
    if ev is None or ev <= 0:
        return "NONPOSITIVE_CONTROL_EV"
    if role == "REVIEW_BACKUP_CONFLICT":
        return "BACKUP_CONFLICT_QUARANTINE"
    if role == "STARTER_CONFLICT_REVIEW":
        return "STARTER_CONFLICT_REVIEW"
    if role == "NO_DEPTH_FALLBACK_H012":
        return "NO_DEPTH_REVIEW"
    if role == "ROLE_ALIGNED" and agree:
        return "PRIMARY_EXECUTABLE_PRICE_VERIFY"
    if role == "ROLE_ALIGNED" and not agree:
        return "TRACK_DISAGREEMENT_REVIEW"
    return "OTHER_REVIEW"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()

    cid, cdir, cp, caudit = comparison_bundle(root)
    rows = rcsv(cp)
    if not rows:
        raise SystemExit("FAIL comparison CSV is empty")
    if any(str(r.get("market_quote_classification") or "") != "REFERENCE_ONLY_NON_EXECUTABLE" for r in rows):
        raise SystemExit("FAIL 0.35 is intended for the current all-reference-only PropsMadness snapshot; mixed/executable rows require a new version")

    enriched: list[dict[str, Any]] = []
    for r in rows:
        side = str(r.get("control_best_side") or "").strip().upper()
        if side not in {"OVER", "UNDER"}:
            continue
        control_p = prob_for_side(r, "control_", side)
        role_p = prob_for_side(r, "role_shadow_", side)
        control_ev = ev_for_side(r, "control_", side)
        role_ev = ev_for_side(r, "role_shadow_", side)
        ref_price = price_for_side(r, side)
        qclass = queue_class(r)
        enriched.append({
            "queue_class": qclass,
            "game_id": r.get("game_id"),
            "kickoff_utc": r.get("kickoff_utc"),
            "player_name": r.get("player_name"),
            "team": r.get("team"),
            "opponent": r.get("opponent"),
            "position_group": r.get("position_group"),
            "role_state": r.get("role_state"),
            "tracks_agree_side": r.get("tracks_agree_side"),
            "side": side,
            "line": r.get("line"),
            "reference_book": r.get("book"),
            "reference_price": ref_price,
            "reference_captured_at": r.get("market_captured_at"),
            "control_probability": control_p,
            "role_shadow_probability_same_side": role_p,
            "control_ev_at_reference": control_ev,
            "role_shadow_ev_at_reference_same_side": role_ev,
            "control_fair_american": fair_american(control_p),
            "role_shadow_fair_american_same_side": fair_american(role_p),
            "control_xtc": r.get("control_xtc"),
            "role_point_xtc": r.get("role_point_xtc"),
            "control_h012_snap_share": r.get("control_h012_snap_share"),
            "role_point_snap_share": r.get("role_point_snap_share"),
            "market_quote_classification": r.get("market_quote_classification"),
            "operational_status": r.get("operational_status"),
            "actual_book": "",
            "actual_line": "",
            "actual_price": "",
            "actual_observed_at": "",
            "actual_available": "",
            "availability_verified": "",
            "verification_notes": "",
        })

    # Queue ranking is operational triage only: primary rows first, then review/quarantine classes;
    # within each class rank by frozen-control EV. It is not a model score or promotion rule.
    class_order = {
        "PRIMARY_EXECUTABLE_PRICE_VERIFY": 0,
        "STARTER_CONFLICT_REVIEW": 1,
        "TRACK_DISAGREEMENT_REVIEW": 2,
        "NO_DEPTH_REVIEW": 3,
        "BACKUP_CONFLICT_QUARANTINE": 4,
        "OTHER_REVIEW": 5,
        "NONPOSITIVE_CONTROL_EV": 6,
    }
    enriched.sort(key=lambda r: (class_order.get(str(r["queue_class"]), 99), -(float(r["control_ev_at_reference"]) if r["control_ev_at_reference"] is not None else -999)))
    for i, r in enumerate(enriched, 1):
        r["queue_rank"] = i

    stamp = nowdt().strftime("%Y%m%dT%H%M%SZ")
    seed = hashlib.sha256((cid + sha(cp)).encode()).hexdigest()[:8]
    qid = f"{stamp}_{seed}"
    base = root / "data/prospective/nfl/omega_week2_verification_queue_0350"
    staging = base / ("." + qid + ".staging")
    final = base / qid
    if final.exists():
        raise SystemExit(f"FAIL immutable queue already exists: {final}")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        fields = ["queue_rank"] + [k for k in enriched[0].keys() if k != "queue_rank"]
        wcsv(staging / "OMEGA_0.35_WEEK2_EXECUTABLE_PRICE_VERIFICATION_QUEUE.csv", enriched, fields)
        primary = [r for r in enriched if r["queue_class"] == "PRIMARY_EXECUTABLE_PRICE_VERIFY"]
        wcsv(staging / "OMEGA_0.35_PRIMARY_VERIFY.csv", primary, fields)
        review = [r for r in enriched if r["queue_class"] != "PRIMARY_EXECUTABLE_PRICE_VERIFY" and r["queue_class"] != "NONPOSITIVE_CONTROL_EV"]
        wcsv(staging / "OMEGA_0.35_REVIEW_AND_QUARANTINE.csv", review, fields)

        unmatched_file = cdir / "OMEGA_0.34.1_UNMATCHED.csv"
        if not unmatched_file.exists():
            unmatched_file = cdir / "OMEGA_0.34_UNMATCHED.csv"
        unmatched = rcsv(unmatched_file) if unmatched_file.exists() else []
        wcsv(staging / "OMEGA_0.35_UPSTREAM_UNMATCHED.csv", unmatched)

        counts: dict[str, int] = {}
        for r in enriched:
            k = str(r["queue_class"])
            counts[k] = counts.get(k, 0) + 1
        audit = {
            "schemaVersion": SCHEMA,
            "queueId": qid,
            "createdAt": now(),
            "comparisonId": cid,
            "comparisonSha256": sha(cp),
            "comparisonRows": len(rows),
            "queueRows": len(enriched),
            "classCounts": counts,
            "unmatchedRowsCarriedForward": len(unmatched),
            "referenceOnlyInputRequired": True,
            "decisionProbabilityTrack": "FROZEN_OMEGA_CONTROL",
            "roleProbabilityStatus": "SHADOW_ONLY_NOT_PROMOTED",
            "queueRankingPolicy": "OPERATIONAL_TRIAGE_ONLY_PRIMARY_FIRST_THEN_CONTROL_EV",
            "executablePriceVerifiedRows": 0,
            "authoritativeInactiveOverlayApplied": False,
            "modelRefits": 0,
            "modelWrites": 0,
            "oddsPapiRequests": 0,
            "note": "This queue does not recommend bets. Every reference quote must be re-checked at the actual sportsbook before any decision ledger entry."
        }
        (staging / "OMEGA_0.35_WEEK2_VERIFICATION_QUEUE_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        hashes = {p.name: sha(p) for p in staging.iterdir() if p.is_file()}
        (staging / "OMEGA_OUTPUT_HASHES.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, final)
        atomic_text(root / "data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_VERIFICATION_QUEUE", qid + "\n")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    primary = [r for r in enriched if r["queue_class"] == "PRIMARY_EXECUTABLE_PRICE_VERIFY"]
    starter = [r for r in enriched if r["queue_class"] == "STARTER_CONFLICT_REVIEW"]
    backup = [r for r in enriched if r["queue_class"] == "BACKUP_CONFLICT_QUARANTINE"]
    disagreement = [r for r in enriched if r["queue_class"] == "TRACK_DISAGREEMENT_REVIEW"]

    print("OMEGA 0.35 — WEEK 2 EXECUTABLE-PRICE VERIFICATION QUEUE")
    print(f"PASS comparison {cid} · rows {len(rows)} · all reference-only/non-executable")
    print(f"PRIMARY VERIFY {len(primary)} · STARTER REVIEW {len(starter)} · BACKUP QUARANTINE {len(backup)} · TRACK DISAGREE {len(disagreement)}")
    print(f"PASS upstream unmatched carried forward {len(unmatched)} · model refits/writes 0 · OddsPapi 0")
    print("TOP PRIMARY ROWS — VERIFY AT ACTUAL SPORTSBOOK BEFORE ANY DECISION:")
    for r in primary[:15]:
        cev = 100 * float(r["control_ev_at_reference"])
        rev = r["role_shadow_ev_at_reference_same_side"]
        revs = "NA" if rev is None else f"{100*float(rev):+.1f}%"
        cpct = 100 * float(r["control_probability"])
        rp = r["role_shadow_probability_same_side"]
        rpct = "NA" if rp is None else f"{100*float(rp):.1f}%"
        price = r["reference_price"]
        print(
            f"  {r['game_id']} · {r['player_name']} {r['side']} {r['line']} {price:+.0f} {r['reference_book']} · "
            f"CONTROL p {cpct:.1f}% EV {cev:+.1f}% · ROLE p {rpct} EV {revs} · {r['role_state']}"
        )
    if starter:
        print("STARTER-CONFLICT REVIEW — NOT PRIMARY VERIFY:")
        for r in starter[:8]:
            cev = 100 * float(r["control_ev_at_reference"])
            print(f"  {r['game_id']} · {r['player_name']} {r['side']} {r['line']} · CONTROL EV {cev:+.1f}%")
    if unmatched:
        print("UPSTREAM UNMATCHED:")
        for r in unmatched[:10]:
            print(f"  {r.get('player_name')} · team {r.get('player_team')} · book {r.get('book')} · line {r.get('line')} · {r.get('join_method')}")
    print(f"QUEUE: {final/'OMEGA_0.35_WEEK2_EXECUTABLE_PRICE_VERIFICATION_QUEUE.csv'}")
    print(f"PRIMARY: {final/'OMEGA_0.35_PRIMARY_VERIFY.csv'}")
    print(f"REPORT: {final/'OMEGA_0.35_WEEK2_VERIFICATION_QUEUE_AUDIT.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

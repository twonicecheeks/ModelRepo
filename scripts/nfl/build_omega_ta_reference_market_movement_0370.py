#!/usr/bin/env python3
"""OMEGA 0.37 — immutable NFL T+A reference-market movement ledger.

Read-only downstream research over immutable raw OMEGA market snapshots plus the
frozen Week 2 dual-track forecast. No model fitting, probability mutation, market
mutation, bet selection, or executable-price promotion occurs here.

Purpose:
  * track PropsMadness referenceBet/noOffer T+A quotes through time;
  * preserve exact snapshot chronology, line/price/book changes, adds/removals;
  * recompute frozen CONTROL and ROLE-shadow probability/EV at each observed line;
  * quantify how model-v-reference divergence changes without changing the model;
  * explicitly keep all reference quotes NON-EXECUTABLE.
"""
from __future__ import annotations

from collections import Counter, defaultdict
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

SCHEMA = "OMEGA_TA_REFERENCE_MARKET_MOVEMENT_0.37.0"
VERSION = "0.37.0"
SEASON = 2026
WEEK = 2
REFERENCE_MARKER = "REFERENCE_ONLY_NON_EXECUTABLE"


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


def parse_ts(v: Any) -> datetime | None:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def iso(d: datetime | None) -> str:
    return "" if d is None else d.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_helpers(root: Path):
    p = root / "scripts/nfl/compare_omega_tackle_market_0180.py"
    spec = importlib.util.spec_from_file_location("omega018_movement_helpers", p)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FAIL cannot load deterministic identity/market helpers: {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def freeze_bundle(root: Path) -> tuple[str, Path, str, list[dict[str, str]]]:
    ptr = root / "data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_DUAL_TRACK_FREEZE"
    if not ptr.exists():
        raise SystemExit("FAIL current Week 2 dual-track freeze pointer missing")
    fid = ptr.read_text(encoding="utf-8").strip()
    d = root / "data/prospective/nfl/omega_week2_dual_track_0330" / fid
    dual = d / "OMEGA_0.33_WEEK2_DUAL_TRACK.csv"
    hashes = d / "OMEGA_OUTPUT_HASHES.json"
    manifest = d / "OMEGA_0.33_WEEK2_MANIFEST.json"
    for p in (dual, hashes, manifest):
        if not p.exists():
            raise SystemExit(f"FAIL incomplete Week 2 freeze bundle: {p}")
    hm = json.loads(hashes.read_text(encoding="utf-8"))
    expected = str(hm.get(dual.name) or "")
    if not expected or sha(dual) != expected:
        raise SystemExit("FAIL frozen Week 2 dual-track CSV hash mismatch")
    rows = rcsv(dual)
    if len(rows) != 800:
        raise SystemExit(f"FAIL unexpected Week 2 forecast row count {len(rows)}; expected 800")
    if any(int(float(r.get("season") or 0)) != SEASON or int(float(r.get("week") or 0)) != WEEK for r in rows):
        raise SystemExit("FAIL non-2026 Week 2 row in frozen dual-track ledger")
    return fid, dual, sha(dual), rows


def model_probability(row: dict[str, Any], prefix: str, side: str, line: float) -> float | None:
    tag = str(float(line)).replace(".", "_")
    x = num(row.get(f"{prefix}p_{side.lower()}_{tag}"))
    return x if x is not None and 0.0 <= x <= 1.0 else None


def priced_side_probability(row: dict[str, Any], prefix: str, side: str) -> float | None:
    line = num(row.get("line"))
    return None if line is None else model_probability(row, prefix, side, line)


def ev(h, p: float | None, odds: float | None) -> float | None:
    if p is None or odds is None:
        return None
    return h.roi(p, odds)


def best_side(over_ev: float | None, under_ev: float | None) -> tuple[str, float | None]:
    vals = [("OVER", over_ev), ("UNDER", under_ev)]
    vals = [(s, v) for s, v in vals if v is not None]
    return max(vals, key=lambda z: z[1]) if vals else ("", None)


def side_price(r: dict[str, Any], side: str) -> float | None:
    side = side.upper()
    direct = num(r.get("over_odds_american" if side == "OVER" else "under_odds_american"))
    if direct is not None:
        return direct
    if str(r.get("one_sided_side") or "").strip().upper() == side:
        return num(r.get("one_sided_odds_american"))
    return None


def side_prob(r: dict[str, Any], prefix: str, side: str) -> float | None:
    return num(r.get(f"{prefix}{side.lower()}_probability"))


def quote_is_reference(r: dict[str, str]) -> bool:
    source = str(r.get("source") or "").strip().lower()
    notes = str(r.get("notes") or "")
    return source == "propsmadness-reference-api" or REFERENCE_MARKER in notes


def movement_type(prev: dict[str, Any], cur: dict[str, Any]) -> str:
    pl, cl = num(prev.get("line")), num(cur.get("line"))
    line_changed = pl is not None and cl is not None and abs(cl - pl) > 1e-12
    book_changed = str(prev.get("book") or "") != str(cur.get("book") or "")
    over_changed = side_price(prev, "OVER") != side_price(cur, "OVER")
    under_changed = side_price(prev, "UNDER") != side_price(cur, "UNDER")
    price_changed = over_changed or under_changed
    if line_changed and book_changed and price_changed:
        return "LINE_BOOK_PRICE_CHANGE"
    if line_changed and book_changed:
        return "LINE_AND_BOOK_CHANGE"
    if line_changed and price_changed:
        return "LINE_AND_PRICE_CHANGE"
    if line_changed:
        return "LINE_UP" if cl > pl else "LINE_DOWN"
    if book_changed and price_changed:
        return "BOOK_AND_PRICE_CHANGE"
    if book_changed:
        return "BOOK_CHANGE"
    if price_changed:
        return "PRICE_ONLY"
    return "UNCHANGED"


def snapshot_bundles(root: Path) -> list[dict[str, Any]]:
    base = root / "data/raw/nfl/omega/market_snapshots"
    if not base.exists():
        raise SystemExit("FAIL no immutable market_snapshots directory")
    bundles: list[dict[str, Any]] = []
    for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
        mp = d / "MARKET_SNAPSHOT_MANIFEST.json"
        cp = d / "normalized_market_rows.csv"
        if not mp.exists() or not cp.exists():
            continue
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("modelFieldsPresent") is not False or int(meta.get("oddsPapiRequests") or 0) != 0:
            continue
        rows = rcsv(cp)
        refs = [r for r in rows if str(r.get("market_kind") or "").strip().lower() == "tackles_assists" and quote_is_reference(r)]
        if not refs:
            continue
        created = parse_ts(meta.get("createdAt"))
        row_times = [parse_ts(r.get("captured_at")) for r in refs]
        row_times = [x for x in row_times if x is not None]
        observed = min(row_times) if row_times else created
        if observed is None:
            continue
        bundles.append({
            "snapshot_id": d.name,
            "dir": d,
            "manifest": meta,
            "csv": cp,
            "csv_sha256": sha(cp),
            "observed_at": observed,
            "rows": refs,
        })
    bundles.sort(key=lambda x: (x["observed_at"], x["snapshot_id"]))
    return bundles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    h = load_helpers(root)

    fid, dual_path, dual_sha, forecasts = freeze_bundle(root)
    indexes = h.build_indexes(forecasts)
    bundles = snapshot_bundles(root)
    if not bundles:
        raise SystemExit("FAIL no reference-only T+A snapshots available")

    observations: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    postkick: list[dict[str, Any]] = []
    join_methods = Counter()
    snapshot_counts = Counter()
    duplicate_keys: list[dict[str, Any]] = []

    for b in bundles:
        seen: dict[str, int] = Counter()
        for m in b["rows"]:
            cand, method = h.resolve_market_identity(m, indexes)
            join_methods[method] += 1
            base_diag = {
                "snapshot_id": b["snapshot_id"], "snapshot_observed_at": iso(b["observed_at"]),
                "player_name": m.get("player_name"), "player_team": m.get("player_team"),
                "opponent": m.get("opponent"), "book": m.get("book"), "line": m.get("line"),
                "join_method": method,
            }
            if len(cand) == 0:
                unmatched.append(base_diag)
                continue
            if len(cand) != 1:
                ambiguous.append({**base_diag, "candidate_count": len(cand), "candidate_names": "|".join(str(x.get("player_name") or "") for x in cand)})
                continue
            p = cand[0]
            line = num(m.get("line"))
            if line is None or not h.is_half(line) or line < 0.5 or line > 14.5:
                unsupported.append({**base_diag, "reason": "UNSUPPORTED_LINE"})
                continue
            mt = parse_ts(m.get("captured_at")) or b["observed_at"]
            ko = parse_ts(p.get("kickoff_utc"))
            if mt is None or ko is None or mt >= ko:
                postkick.append({**base_diag, "reason": "MISSING_TIME_OR_AT_AFTER_KICKOFF", "kickoff_utc": p.get("kickoff_utc")})
                continue

            cpo = model_probability(p, "control_", "over", line)
            cpu = model_probability(p, "control_", "under", line)
            rpo = model_probability(p, "role_shadow_", "over", line)
            rpu = model_probability(p, "role_shadow_", "under", line)
            if None in (cpo, cpu, rpo, rpu):
                unsupported.append({**base_diag, "reason": "MISSING_FROZEN_PROBABILITY_AT_LINE"})
                continue

            oo = num(m.get("over_odds_american")); uo = num(m.get("under_odds_american"))
            one_side = str(m.get("one_sided_side") or "").strip().upper(); one_odds = num(m.get("one_sided_odds_american"))
            if oo is None and uo is None and one_side not in {"OVER", "UNDER"}:
                unsupported.append({**base_diag, "reason": "NO_PRICE"})
                continue
            cev_o = ev(h, cpo, oo); cev_u = ev(h, cpu, uo)
            rev_o = ev(h, rpo, oo); rev_u = ev(h, rpu, uo)
            if one_side == "OVER" and one_odds is not None:
                cev_o = ev(h, cpo, one_odds); rev_o = ev(h, rpo, one_odds)
            elif one_side == "UNDER" and one_odds is not None:
                cev_u = ev(h, cpu, one_odds); rev_u = ev(h, rpu, one_odds)
            cb_side, cb_ev = best_side(cev_o, cev_u)
            rb_side, rb_ev = best_side(rev_o, rev_u)
            two = oo is not None and uo is not None
            nv_o = nv_u = None
            if two:
                nv_o, nv_u = h.devig(oo, uo)

            canonical_key = f"{p.get('game_id')}|{p.get('player_id')}"
            seen[canonical_key] += 1
            if seen[canonical_key] > 1:
                duplicate_keys.append({**base_diag, "canonical_key": canonical_key, "count_in_snapshot": seen[canonical_key]})

            observations.append({
                "snapshot_id": b["snapshot_id"], "snapshot_sha256": b["csv_sha256"],
                "captured_at": iso(mt), "snapshot_observed_at": iso(b["observed_at"]),
                "freeze_id": fid, "freeze_sha256": dual_sha,
                "canonical_key": canonical_key,
                "game_id": p.get("game_id"), "kickoff_utc": p.get("kickoff_utc"),
                "player_id": p.get("player_id"), "player_name": p.get("player_name"),
                "team": p.get("team"), "opponent": p.get("opponent"), "position_group": p.get("position_group"),
                "book": m.get("book"), "line": line,
                "over_odds_american": m.get("over_odds_american"), "under_odds_american": m.get("under_odds_american"),
                "one_sided_side": one_side, "one_sided_odds_american": m.get("one_sided_odds_american"),
                "two_sided": "TRUE" if two else "FALSE",
                "market_no_vig_over": nv_o, "market_no_vig_under": nv_u,
                "control_over_probability": cpo, "control_under_probability": cpu,
                "role_shadow_over_probability": rpo, "role_shadow_under_probability": rpu,
                "control_over_ev": cev_o, "control_under_ev": cev_u,
                "role_shadow_over_ev": rev_o, "role_shadow_under_ev": rev_u,
                "control_best_side": cb_side, "control_best_ev": cb_ev,
                "role_shadow_best_side": rb_side, "role_shadow_best_ev": rb_ev,
                "tracks_agree_side": "TRUE" if cb_side and cb_side == rb_side else "FALSE",
                "role_state": p.get("role_state"),
                "identity_join_method": method,
                "quote_classification": REFERENCE_MARKER,
                "operational_status": "REFERENCE_ONLY_NOT_EXECUTABLE",
            })
            snapshot_counts[b["snapshot_id"]] += 1

    if not observations:
        raise SystemExit("FAIL no Week 2 reference-only T+A observations matched frozen forecasts")

    observations.sort(key=lambda r: (parse_ts(r["captured_at"]) or datetime.min.replace(tzinfo=timezone.utc), r["canonical_key"], r["snapshot_id"]))

    by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in observations:
        by_player[str(r["canonical_key"])].append(r)

    transitions: list[dict[str, Any]] = []
    for key, seq in by_player.items():
        seq.sort(key=lambda r: (parse_ts(r["captured_at"]) or datetime.min.replace(tzinfo=timezone.utc), r["snapshot_id"]))
        for i in range(1, len(seq)):
            prev, cur = seq[i-1], seq[i]
            ptime, ctime = parse_ts(prev["captured_at"]), parse_ts(cur["captured_at"])
            line_delta = (num(cur["line"]) - num(prev["line"])) if num(cur["line"]) is not None and num(prev["line"]) is not None else None
            prev_side = str(prev.get("control_best_side") or "")
            cur_side = str(cur.get("control_best_side") or "")
            prev_prob = side_prob(prev, "control_", prev_side) if prev_side else None
            cur_prob_same_prev_side = side_prob(cur, "control_", prev_side) if prev_side else None
            prev_price = side_price(prev, prev_side) if prev_side else None
            cur_price_same_prev_side = side_price(cur, prev_side) if prev_side else None
            prev_be = h.american_break_even(prev_price) if prev_price not in (None, 0) else None
            cur_be = h.american_break_even(cur_price_same_prev_side) if cur_price_same_prev_side not in (None, 0) else None
            transitions.append({
                "canonical_key": key,
                "game_id": cur["game_id"], "player_id": cur["player_id"], "player_name": cur["player_name"],
                "team": cur["team"], "opponent": cur["opponent"], "role_state": cur["role_state"],
                "previous_snapshot_id": prev["snapshot_id"], "current_snapshot_id": cur["snapshot_id"],
                "previous_captured_at": prev["captured_at"], "current_captured_at": cur["captured_at"],
                "elapsed_minutes": ((ctime - ptime).total_seconds() / 60.0) if ptime and ctime else None,
                "movement_type": movement_type(prev, cur),
                "previous_book": prev["book"], "current_book": cur["book"], "book_changed": "TRUE" if prev["book"] != cur["book"] else "FALSE",
                "previous_line": prev["line"], "current_line": cur["line"], "line_delta": line_delta,
                "previous_over_odds": prev["over_odds_american"], "current_over_odds": cur["over_odds_american"],
                "previous_under_odds": prev["under_odds_american"], "current_under_odds": cur["under_odds_american"],
                "previous_control_best_side": prev_side, "current_control_best_side": cur_side,
                "control_best_side_changed": "TRUE" if prev_side != cur_side else "FALSE",
                "previous_control_best_ev": prev["control_best_ev"], "current_control_best_ev": cur["control_best_ev"],
                "control_best_ev_delta": (num(cur["control_best_ev"]) - num(prev["control_best_ev"])) if num(cur["control_best_ev"]) is not None and num(prev["control_best_ev"]) is not None else None,
                "previous_role_shadow_best_ev": prev["role_shadow_best_ev"], "current_role_shadow_best_ev": cur["role_shadow_best_ev"],
                "role_shadow_best_ev_delta": (num(cur["role_shadow_best_ev"]) - num(prev["role_shadow_best_ev"])) if num(cur["role_shadow_best_ev"]) is not None and num(prev["role_shadow_best_ev"]) is not None else None,
                "previous_control_probability_on_previous_side": prev_prob,
                "current_control_probability_on_previous_side": cur_prob_same_prev_side,
                "control_probability_change_due_to_line_on_previous_side": (cur_prob_same_prev_side - prev_prob) if prev_prob is not None and cur_prob_same_prev_side is not None else None,
                "previous_price_on_previous_side": prev_price, "current_price_on_previous_side": cur_price_same_prev_side,
                "previous_break_even_on_previous_side": prev_be, "current_break_even_on_previous_side": cur_be,
                "break_even_change_on_previous_side": (cur_be - prev_be) if prev_be is not None and cur_be is not None else None,
                "quote_classification": REFERENCE_MARKER,
                "operational_status": "RESEARCH_MOVEMENT_ONLY_NOT_EXECUTABLE",
            })

    # Appearance/removal events compare adjacent global snapshots. These are provider-board events,
    # not evidence of sportsbook action.
    appearance_events: list[dict[str, Any]] = []
    snap_to_rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in observations:
        snap_to_rows[r["snapshot_id"]].setdefault(str(r["canonical_key"]), r)
    active_bundles = [b for b in bundles if snapshot_counts[b["snapshot_id"]] > 0]
    for i in range(1, len(active_bundles)):
        a, b = active_bundles[i-1], active_bundles[i]
        prev_map = snap_to_rows.get(a["snapshot_id"], {})
        cur_map = snap_to_rows.get(b["snapshot_id"], {})
        for key in sorted(set(cur_map) - set(prev_map)):
            r = cur_map[key]
            appearance_events.append({
                "event": "ADDED_TO_REFERENCE_BOARD", "canonical_key": key, "player_name": r["player_name"], "team": r["team"],
                "previous_snapshot_id": a["snapshot_id"], "current_snapshot_id": b["snapshot_id"], "observed_at": r["captured_at"],
                "line": r["line"], "book": r["book"], "operational_status": "RESEARCH_ONLY_NOT_EXECUTABLE",
            })
        for key in sorted(set(prev_map) - set(cur_map)):
            r = prev_map[key]
            appearance_events.append({
                "event": "REMOVED_FROM_REFERENCE_BOARD", "canonical_key": key, "player_name": r["player_name"], "team": r["team"],
                "previous_snapshot_id": a["snapshot_id"], "current_snapshot_id": b["snapshot_id"], "observed_at": iso(b["observed_at"]),
                "line": r["line"], "book": r["book"], "operational_status": "RESEARCH_ONLY_NOT_EXECUTABLE",
            })

    # Latest movement board: one current row per canonical player, carrying the most recent transition.
    latest_transition = {str(r["canonical_key"]): r for r in transitions}
    latest_rows: list[dict[str, Any]] = []
    for key, seq in by_player.items():
        cur = sorted(seq, key=lambda r: (parse_ts(r["captured_at"]) or datetime.min.replace(tzinfo=timezone.utc), r["snapshot_id"]))[-1]
        tr = latest_transition.get(key)
        latest_rows.append({
            "canonical_key": key, "game_id": cur["game_id"], "kickoff_utc": cur["kickoff_utc"],
            "player_id": cur["player_id"], "player_name": cur["player_name"], "team": cur["team"], "opponent": cur["opponent"],
            "role_state": cur["role_state"], "latest_snapshot_id": cur["snapshot_id"], "latest_captured_at": cur["captured_at"],
            "latest_book": cur["book"], "latest_line": cur["line"],
            "latest_over_odds": cur["over_odds_american"], "latest_under_odds": cur["under_odds_american"],
            "latest_control_best_side": cur["control_best_side"], "latest_control_best_ev": cur["control_best_ev"],
            "latest_role_shadow_best_side": cur["role_shadow_best_side"], "latest_role_shadow_best_ev": cur["role_shadow_best_ev"],
            "tracks_agree_side": cur["tracks_agree_side"],
            "observation_count": len(seq),
            "latest_movement_type": tr.get("movement_type") if tr else "FIRST_OBSERVATION",
            "latest_line_delta": tr.get("line_delta") if tr else None,
            "latest_control_best_ev_delta": tr.get("control_best_ev_delta") if tr else None,
            "latest_book_changed": tr.get("book_changed") if tr else "FALSE",
            "quote_classification": REFERENCE_MARKER,
            "operational_status": "REFERENCE_ONLY_NOT_EXECUTABLE",
        })

    latest_rows.sort(key=lambda r: (
        0 if r["latest_movement_type"] not in {"FIRST_OBSERVATION", "UNCHANGED"} else 1,
        -(abs(num(r.get("latest_line_delta")) or 0.0)),
        -(abs(num(r.get("latest_control_best_ev_delta")) or 0.0)),
        str(r["player_name"]),
    ))

    stamp = nowdt().strftime("%Y%m%dT%H%M%SZ")
    seed_material = fid + dual_sha + "|".join(f"{b['snapshot_id']}:{b['csv_sha256']}" for b in bundles)
    lid = f"{stamp}_{hashlib.sha256(seed_material.encode()).hexdigest()[:8]}"
    base = root / "data/prospective/nfl/omega_ta_reference_market_movement_0370"
    staging = base / ("." + lid + ".staging")
    final = base / lid
    if final.exists():
        raise SystemExit(f"FAIL immutable 0.37 ledger already exists: {final}")
    staging.mkdir(parents=True, exist_ok=False)
    try:
        wcsv(staging / "OMEGA_0.37_REFERENCE_MARKET_OBSERVATIONS.csv", observations)
        wcsv(staging / "OMEGA_0.37_REFERENCE_MARKET_TRANSITIONS.csv", transitions)
        wcsv(staging / "OMEGA_0.37_LATEST_MOVEMENT_BOARD.csv", latest_rows)
        wcsv(staging / "OMEGA_0.37_APPEARANCE_EVENTS.csv", appearance_events)
        wcsv(staging / "OMEGA_0.37_UNMATCHED.csv", unmatched)
        wcsv(staging / "OMEGA_0.37_AMBIGUOUS.csv", ambiguous)
        wcsv(staging / "OMEGA_0.37_UNSUPPORTED.csv", unsupported)
        wcsv(staging / "OMEGA_0.37_POSTKICK_EXCLUDED.csv", postkick)
        wcsv(staging / "OMEGA_0.37_DUPLICATE_KEYS.csv", duplicate_keys)
        audit = {
            "schemaVersion": SCHEMA,
            "ledgerId": lid,
            "createdAt": now(),
            "freezeId": fid,
            "freezeSha256": dual_sha,
            "snapshotCountConsidered": len(bundles),
            "snapshotIds": [b["snapshot_id"] for b in bundles],
            "snapshotCsvSha256": {b["snapshot_id"]: b["csv_sha256"] for b in bundles},
            "matchedObservationRows": len(observations),
            "canonicalPlayersObserved": len(by_player),
            "transitionRows": len(transitions),
            "appearanceEventRows": len(appearance_events),
            "unmatchedRows": len(unmatched),
            "ambiguousRows": len(ambiguous),
            "unsupportedRows": len(unsupported),
            "postKickExcludedRows": len(postkick),
            "duplicateCanonicalKeysWithinSnapshot": len(duplicate_keys),
            "joinMethods": dict(join_methods),
            "movementTypes": dict(Counter(r["movement_type"] for r in transitions)),
            "appearanceTypes": dict(Counter(r["event"] for r in appearance_events)),
            "decisionProbabilityTrack": "FROZEN_OMEGA_CONTROL",
            "roleProbabilityStatus": "SHADOW_ONLY_NOT_PROMOTED",
            "marketQuoteClassification": REFERENCE_MARKER,
            "executablePriceRows": 0,
            "authoritativeInactiveOverlayApplied": False,
            "modelRefits": 0,
            "modelWrites": 0,
            "oddsPapiRequests": 0,
            "interpretationGuardrail": "Movement is provider reference-board movement only; it is not proof of sharp action, bet size, or sportsbook execution.",
        }
        (staging / "OMEGA_0.37_REFERENCE_MARKET_MOVEMENT_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        hashes = {p.name: sha(p) for p in staging.iterdir() if p.is_file()}
        (staging / "OMEGA_OUTPUT_HASHES.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, final)
        atomic_text(root / "data/prospective/nfl/omega/CURRENT_OMEGA_TA_REFERENCE_MARKET_MOVEMENT", lid + "\n")
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    changed = [r for r in latest_rows if r["latest_movement_type"] not in {"FIRST_OBSERVATION", "UNCHANGED"}]
    print("OMEGA 0.37 — NFL T+A REFERENCE-MARKET MOVEMENT LEDGER")
    print(f"PASS snapshots {len(bundles)} · observations {len(observations)} · canonical players {len(by_player)} · transitions {len(transitions)}")
    print(f"PASS latest changed {len(changed)} · adds/removals {len(appearance_events)} · unmatched {len(unmatched)} · ambiguous {len(ambiguous)} · unsupported {len(unsupported)} · postkick {len(postkick)}")
    print("PASS reference-only/non-executable · frozen CONTROL unchanged · ROLE shadow-only · model refits/writes 0 · OddsPapi 0")
    if len(bundles) == 1:
        print("BASELINE ONLY: one reference snapshot exists; capture/import another 0.17.11 board to begin movement transitions.")
    else:
        print("LATEST REFERENCE-BOARD MOVES — RESEARCH ONLY, NOT PROOF OF SHARP ACTION:")
        for r in changed[:20]:
            lev = num(r.get("latest_control_best_ev")); dev = num(r.get("latest_control_best_ev_delta")); ld = num(r.get("latest_line_delta"))
            levs = "NA" if lev is None else f"{100*lev:+.1f}%"
            devs = "NA" if dev is None else f"{100*dev:+.1f}pp"
            lds = "NA" if ld is None else f"{ld:+.1f}"
            print(f"  {r['game_id']} · {r['player_name']} · {r['latest_movement_type']} · line {r['latest_line']} ({lds}) · {r['latest_book']} · CONTROL {r['latest_control_best_side']} EV {levs} (Δ {devs}) · {r['role_state']}")
    print(f"LEDGER: {final/'OMEGA_0.37_REFERENCE_MARKET_OBSERVATIONS.csv'}")
    print(f"MOVES: {final/'OMEGA_0.37_REFERENCE_MARKET_TRANSITIONS.csv'}")
    print(f"LATEST: {final/'OMEGA_0.37_LATEST_MOVEMENT_BOARD.csv'}")
    print(f"AUDIT: {final/'OMEGA_0.37_REFERENCE_MARKET_MOVEMENT_AUDIT.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

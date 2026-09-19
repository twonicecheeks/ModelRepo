#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import uuid


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise ValueError(f"{path}:{n}: invalid JSON: {exc}") from exc
    if not rows:
        raise ValueError(f"no rows in {path}")
    return rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_pointer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, path)


def pct(v):
    return "n/a" if v is None else f"{100.0 * float(v):.2f}%"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audit leakage-safe MLB ML/K historical prediction ledger"
    )
    ap.add_argument("ledger")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    ledger = Path(args.ledger).expanduser().resolve()
    if not ledger.exists():
        raise FileNotFoundError(ledger)

    model_dir = root / "packages/models/mlb/evaluation"
    sys.path.insert(0, str(model_dir))
    import historical_validation_010 as hv

    rows = load_jsonl(ledger)
    report = hv.full_audit(rows)
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "_"
        + uuid.uuid4().hex[:8]
    )
    out_dir = root / "data/models/mlb/historical_validation_010" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    report.update(
        {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "label": args.label or None,
            "input_ledger": str(ledger),
            "input_sha256": sha256_file(ledger),
            "production_model_mutation": False,
            "market_requests": 0,
            "oddsPapi_requests": 0,
            "refit_performed": False,
        }
    )
    out = out_dir / "MLB_HISTORICAL_VALIDATION_AUDIT.json"
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    atomic_pointer(
        root / "data/models/mlb/CURRENT_HISTORICAL_VALIDATION_010",
        str(out_dir.relative_to(root)),
    )

    overall = report["overall"]
    print()
    print(f"MLB HISTORICAL VALIDATION {hv.VERSION}")
    print(f"Ledger: {ledger}")
    print(f"Rows: {report['rows']:,} · SHA256 {report['input_sha256']}")
    print("Production mutation: NO · refit: NO · market calls: 0 · OddsPapi: 0")
    if overall.get("brier") is not None:
        print(
            f"Brier {overall['brier']:.6f} · log loss {overall['log_loss']:.6f} "
            f"· probability bias {overall['probability_bias']:+.4f}"
        )
        print(f"Calibration ECE {overall['calibration']['ece']:.4f}")
    if overall.get("xk"):
        x = overall["xk"]
        print(
            f"xK MAE {x['mae']:.3f} · RMSE {x['rmse']:.3f} · bias {x['bias']:+.3f}"
        )
    if overall.get("betting"):
        b = overall["betting"]
        print(
            f"Bet rows {b['n']:,} · ROI {pct(b['roi'])} · P/L {b['profit_units']:+.3f}u "
            f"· max DD {b['max_drawdown_units']:.3f}u"
        )
    if overall.get("raw_implied_clv"):
        c = overall["raw_implied_clv"]
        print(
            f"Raw implied CLV {c['mean_probability_points']:+.3f}pp · "
            f"beat-close {pct(c['beat_close_rate'])}"
        )

    print()
    print("SEASON TYPE SPLITS")
    for season_type, s in report.get("season_type", {}).items():
        parts = [f"{season_type}: n {s.get('n', 0)}"]
        if s.get("brier") is not None:
            parts.append(f"Brier {s['brier']:.6f}")
            parts.append(f"bias {s['probability_bias']:+.4f}")
        if s.get("xk"):
            parts.append(f"xK MAE {s['xk']['mae']:.3f}")
            parts.append(f"xK RMSE {s['xk']['rmse']:.3f}")
            parts.append(f"xK bias {s['xk']['bias']:+.3f}")
        print(" · ".join(parts))

    print()
    print("DIAGNOSTIC SPLITS")
    for season, s in report.get("season", {}).items():
        parts = [f"season {season}: n {s.get('n', 0)}"]
        if s.get("brier") is not None:
            parts.append(f"Brier {s['brier']:.6f}")
            parts.append(f"bias {s['probability_bias']:+.4f}")
        if s.get("xk"):
            parts.append(f"xK MAE {s['xk']['mae']:.3f}")
            parts.append(f"xK bias {s['xk']['bias']:+.3f}")
        print(" · ".join(parts))
    for mode, s in report.get("workload_proxy_source", {}).items():
        if mode == "UNKNOWN":
            continue
        parts = [f"workload {mode}: n {s.get('n', 0)}"]
        if s.get("xk"):
            parts.append(f"xK MAE {s['xk']['mae']:.3f}")
            parts.append(f"xK bias {s['xk']['bias']:+.3f}")
        print(" · ".join(parts))
    for ruleset, s in report.get("ruleset", {}).items():
        if ruleset == "UNKNOWN":
            continue
        parts = [f"ruleset {ruleset}: n {s.get('n', 0)}"]
        if s.get("brier") is not None:
            parts.append(f"Brier {s['brier']:.6f}")
            parts.append(f"bias {s['probability_bias']:+.4f}")
        if s.get("xk"):
            parts.append(f"xK MAE {s['xk']['mae']:.3f}")
            parts.append(f"xK bias {s['xk']['bias']:+.3f}")
        print(" · ".join(parts))

    print()
    print("POSTSEASON REGIME AUDIT")
    for name, item in report["postseason_shift"].items():
        status = item.get("status")
        if "post_minus_reg" in item:
            print(
                f"{name}: {status} · POST−REG {item['post_minus_reg']:+.6f} · "
                f"95% CI [{item['ci95'][0]:+.6f}, {item['ci95'][1]:+.6f}]"
            )
        else:
            print(f"{name}: {status}")
    print()
    print(f"Audit: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

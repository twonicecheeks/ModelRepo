#!/usr/bin/env python3
"""POST_USAGE mechanism bakeoff 0.9.0.

Historical DEVELOPMENT bakeoff only. Compares:
- POST_USAGE_BF: prior-season matched pitcher BF ratio applied to expected BF
- POST_USAGE_OUTS: prior-season matched pitcher outs ratio applied to expected outs,
  then expected BF is recomputed with the baseline expected hits/walks.

Both factors are learned from workload outcomes only, never K outcomes.
Both are chronological: season S uses only usage observations from seasons < S.

Because 2016-2025 K outcomes have now been inspected, this script is model
development/selection, NOT a fresh validation. The selected mechanism must be
frozen before prospective 2026 postseason evaluation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import uuid


VERSION = "0.9.0"
LINEAGE = "mlb-post-usage-mechanism-bakeoff-v0.9.0-2026-09-19"


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("postusage080", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def rebuild_xk_from_exposure(row: dict, adjusted_bf: float) -> tuple[float, dict]:
    proj = row.get("k_projection") or {}
    c = proj.get("components") or {}
    matchup_k = float(c["matchupK"]) / 100.0
    weights = c.get("blendWeights") or {}
    sw = float(weights.get("structural") or 0.0)
    rw = float(weights.get("recent") or 0.0)
    yw = float(weights.get("season") or 0.0)
    if sw <= 0:
        raise ValueError("baseline projection missing structural blend weight")

    structural = adjusted_bf * matchup_k
    value = sw * structural
    if rw:
        if c.get("recentK") is None:
            raise ValueError("recent blend weight present but recentK missing")
        value += rw * float(c["recentK"])
    if yw:
        if c.get("seasonK") is None:
            raise ValueError("season blend weight present but seasonK missing")
        value += yw * float(c["seasonK"])

    ceiling = max(0.5, min(18.0, adjusted_bf * 0.75))
    xk = max(0.15, min(ceiling, value))
    return xk, {
        "adjusted_expected_bf": adjusted_bf,
        "adjusted_structural_k": structural,
        "matchup_k_rate": matchup_k,
        "blend_weights": {"structural": sw, "recent": rw, "season": yw},
        "physical_ceiling": ceiling,
    }


def outs_adjusted_xk(row: dict, outs_factor: float) -> tuple[float, dict]:
    proj = row.get("k_projection") or {}
    c = proj.get("components") or {}
    base_outs = float(c["expectedOuts"])
    hits = float(c["expectedHits"])
    walks = float(c["expectedWalks"])
    base_bf = float(c["expectedBF"])

    adjusted_outs = max(3.0, min(23.5, base_outs * float(outs_factor)))
    adjusted_bf = max(10.0, min(33.0, adjusted_outs + hits + walks + 0.30))
    xk, diag = rebuild_xk_from_exposure(row, adjusted_bf)
    return xk, {
        **diag,
        "baseline_expected_outs": base_outs,
        "usage_outs_factor": outs_factor,
        "adjusted_expected_outs": adjusted_outs,
        "baseline_expected_bf": base_bf,
        "baseline_expected_hits": hits,
        "baseline_expected_walks": walks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Bake off postseason usage mechanisms")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    v080 = load_module(root / "scripts/mlb/evaluate_mlb_post_usage_080.py")

    post_ledger = v080.resolve_pointer(
        root, "data/models/mlb/CURRENT_POSTSEASON_REPLAY_050",
        "MLB_POSTSEASON_HISTORY_PROXY_LEDGER.jsonl"
    )
    reg_ledger = v080.resolve_pointer(
        root, "data/models/mlb/CURRENT_REGULAR_CONTROL_K_071",
        "MLB_REGULAR_CONTROL_K_LEDGER.jsonl"
    )
    post_targets = v080.resolve_pointer(
        root, "data/normalized/mlb/CURRENT_HISTORICAL_OUTCOMES_030",
        "MLB_HISTORICAL_OUTCOMES.jsonl"
    )
    reg_targets = v080.resolve_pointer(
        root, "data/normalized/mlb/CURRENT_REGULAR_CONTROL_070",
        "MLB_REGULAR_CONTROL_TARGETS.jsonl"
    )

    post_rows = [
        r for r in v080.load_jsonl(post_ledger)
        if str(r.get("market_type", "")).upper() == "K"
    ]
    reg_rows = [
        r for r in v080.load_jsonl(reg_ledger)
        if str(r.get("market_type", "")).upper() == "K"
    ]
    p_targets = v080.target_workload_index(v080.load_jsonl(post_targets))
    r_targets = v080.target_workload_index(v080.load_jsonl(reg_targets))
    p_samples = v080.successful_workload_samples(post_rows, p_targets)
    r_samples = v080.successful_workload_samples(reg_rows, r_targets)
    ratios = v080.matched_pitcher_season_ratios(r_samples, p_samples)
    seasons = sorted({int(r["season"]) for r in post_rows})
    factors = v080.expanding_factors(ratios, seasons)

    baseline, bf_rows, outs_rows, blocked = [], [], [], []
    for r in post_rows:
        season = int(r["season"])
        f = factors[season]
        if f["status"] != "OOS_READY":
            continue
        if str(r.get("workload_proxy_source", "")) != "REGULAR_SEASON_STARTS":
            continue
        try:
            bf_xk, bf_diag = v080.usage_adjusted_xk(r, float(f["bf_factor"]))
            outs_xk, outs_diag = outs_adjusted_xk(r, float(f["outs_factor"]))
        except Exception as exc:
            blocked.append(
                {"game_id": str(r["game_id"]), "pitcher": r.get("pitcher"), "error": str(exc)}
            )
            continue

        b = dict(r)
        b["model_variant"] = "POST_HISTORY_PROXY"

        bf = dict(r)
        bf["model_variant"] = "POST_USAGE_BF"
        bf["xk"] = bf_xk
        bf["post_usage"] = {
            **bf_diag,
            "mechanism": "EXPECTED_BF_RATIO",
            "training_seasons": f["training_seasons"],
            "training_pitcher_seasons": f["training_pitcher_seasons"],
            "same_season_usage_outcomes_used": False,
            "k_outcomes_used_to_learn_factor": False,
        }

        oo = dict(r)
        oo["model_variant"] = "POST_USAGE_OUTS"
        oo["xk"] = outs_xk
        oo["post_usage"] = {
            **outs_diag,
            "mechanism": "EXPECTED_OUTS_RATIO_THEN_RECOMPUTE_BF",
            "training_seasons": f["training_seasons"],
            "training_pitcher_seasons": f["training_pitcher_seasons"],
            "same_season_usage_outcomes_used": False,
            "k_outcomes_used_to_learn_factor": False,
        }

        baseline.append(b)
        bf_rows.append(bf)
        outs_rows.append(oo)

    bf_cmp = v080.paired_bootstrap(baseline, bf_rows)
    outs_cmp = v080.paired_bootstrap(baseline, outs_rows)
    head_cmp = v080.paired_bootstrap(bf_rows, outs_rows)

    # This is historical DEVELOPMENT selection, not a validation verdict.
    # Mechanism preference is OUTS if it passes the baseline OOS improvement
    # criterion and is not clearly worse than BF on MAE/RMSE.
    selected = "NONE"
    reason = "neither usage mechanism met baseline improvement criteria"
    if outs_cmp.get("decision") == "POST_USAGE_IMPROVES_OOS":
        hci = head_cmp.get("ci95", {})
        mae_ci = hci.get("mae_delta")
        rmse_ci = hci.get("rmse_delta")
        clearly_worse = (
            mae_ci is not None and mae_ci[0] > 0
        ) or (
            rmse_ci is not None and rmse_ci[0] > 0
        )
        if not clearly_worse:
            selected = "POST_USAGE_OUTS"
            reason = (
                "OUTS improves baseline OOS and is not clearly worse than BF; "
                "preferred mechanistically because manager hook behavior acts on outs/leash first"
            )
    if selected == "NONE" and bf_cmp.get("decision") == "POST_USAGE_IMPROVES_OOS":
        selected = "POST_USAGE_BF"
        reason = "BF improves baseline OOS and OUTS did not satisfy selection rule"

    per_season = {}
    for season in sorted({int(r["season"]) for r in baseline}):
        b = [r for r in baseline if int(r["season"]) == season]
        x = [r for r in bf_rows if int(r["season"]) == season]
        o = [r for r in outs_rows if int(r["season"]) == season]
        per_season[str(season)] = {
            "factor": factors[season],
            "baseline": v080.xk_metrics(b),
            "post_usage_bf": v080.xk_metrics(x),
            "post_usage_outs": v080.xk_metrics(o),
        }

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/mlb/post_usage_bakeoff_090" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    ledger = out_dir / "MLB_POST_USAGE_MECHANISM_BAKEOFF.jsonl"
    all_rows = baseline + bf_rows + outs_rows
    with ledger.open("w", encoding="utf-8") as f:
        for r in sorted(
            all_rows,
            key=lambda x: (
                int(x["season"]), str(x.get("game_date", "")),
                str(x["game_id"]), str(x.get("pitcher", "")),
                str(x.get("model_variant", "")),
            ),
        ):
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")

    freeze_candidate = None
    if selected != "NONE":
        last = max(seasons)
        # 2026 prospective factor is learned from every matched historical
        # pitcher-season through 2025. No 2026 postseason usage enters it.
        prior_all = [r for r in ratios if int(r["season"]) <= last]
        if selected == "POST_USAGE_OUTS":
            value = __import__("statistics").median(float(r["outs_ratio"]) for r in prior_all)
            field = "outs_ratio"
        else:
            value = __import__("statistics").median(float(r["bf_ratio"]) for r in prior_all)
            field = "bf_ratio"
        freeze_candidate = {
            "model_variant": selected,
            "factor_field": field,
            "factor_value_for_2026_prospective": value,
            "training_seasons": sorted({int(r["season"]) for r in prior_all}),
            "training_pitcher_seasons": len(prior_all),
            "freeze_status": "CANDIDATE_REQUIRES_EXPLICIT_FREEZE",
            "prospective_test_season": 2026,
            "k_outcomes_used_to_learn_factor": False,
        }

    audit = {
        "version": VERSION,
        "lineage": LINEAGE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "HISTORICAL_DEVELOPMENT_BAKEOFF_NOT_FRESH_VALIDATION",
        "historical_scored_seasons": [s for s in seasons if factors[s]["status"] == "OOS_READY"],
        "warmup_season": min(seasons),
        "matched_pitcher_season_ratios_n": len(ratios),
        "bf_vs_baseline": bf_cmp,
        "outs_vs_baseline": outs_cmp,
        "outs_vs_bf": head_cmp,
        "historical_development_selection": {
            "selected": selected,
            "reason": reason,
        },
        "freeze_candidate": freeze_candidate,
        "per_season": per_season,
        "blocked": blocked,
        "blocked_n": len(blocked),
        "ledger": str(ledger),
        "ledger_sha256": sha256_file(ledger),
        "post_ledger": str(post_ledger),
        "post_ledger_sha256": sha256_file(post_ledger),
        "reg_ledger": str(reg_ledger),
        "reg_ledger_sha256": sha256_file(reg_ledger),
        "production_model_mutation": False,
        "model_refit_performed": False,
        "k_outcomes_used_to_learn_usage_factors": False,
        "historical_k_market": "NOT_ACQUIRED",
        "oddsPapi_requests": 0,
        "next_validation": "FREEZE_SELECTED_MECHANISM_THEN_2026_POSTSEASON_PROSPECTIVE",
    }
    audit_path = out_dir / "POST_USAGE_MECHANISM_BAKEOFF_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    atomic_write(
        root / "data/models/mlb/CURRENT_POST_USAGE_BAKEOFF_090",
        str(out_dir.relative_to(root)) + "\n",
    )

    print()
    print(f"MLB POST_USAGE MECHANISM BAKEOFF {VERSION}")
    print("Status: HISTORICAL DEVELOPMENT · NOT A FRESH HOLDOUT")
    print(f"Paired normal-starter rows: {len(baseline):,} · blocked: {len(blocked)}")
    print()
    for name, cmp in (("POST_USAGE_BF", bf_cmp), ("POST_USAGE_OUTS", outs_cmp)):
        b = cmp["baseline"]
        c = cmp["challenger"]
        d = cmp["challenger_minus_baseline"]
        ci = cmp["ci95"]
        print(
            f"{name}: MAE {c['mae']:.3f} ({d['mae']:+.3f}; "
            f"95% CI [{ci['mae_delta'][0]:+.3f}, {ci['mae_delta'][1]:+.3f}]) · "
            f"RMSE {c['rmse']:.3f} ({d['rmse']:+.3f}; "
            f"95% CI [{ci['rmse_delta'][0]:+.3f}, {ci['rmse_delta'][1]:+.3f}]) · "
            f"bias {c['bias']:+.3f}"
        )
    hc = head_cmp
    hd = hc["challenger_minus_baseline"]
    hci = hc["ci95"]
    print()
    print(
        "OUTS minus BF: "
        f"MAE {hd['mae']:+.3f} 95% CI [{hci['mae_delta'][0]:+.3f}, {hci['mae_delta'][1]:+.3f}] · "
        f"RMSE {hd['rmse']:+.3f} 95% CI [{hci['rmse_delta'][0]:+.3f}, {hci['rmse_delta'][1]:+.3f}] · "
        f"bias {hd['bias']:+.3f}"
    )
    print(f"Historical development selection: {selected}")
    print(f"Reason: {reason}")
    if freeze_candidate:
        print(
            f"2026 prospective freeze candidate: {freeze_candidate['model_variant']} · "
            f"{freeze_candidate['factor_field']}={freeze_candidate['factor_value_for_2026_prospective']:.4f} · "
            f"n pitcher-seasons {freeze_candidate['training_pitcher_seasons']}"
        )
        print("Freeze status: CANDIDATE_REQUIRES_EXPLICIT_FREEZE")
    print("Production mutation: NO · refit: NO · OddsPapi: 0")
    print(f"Ledger: {ledger}")
    print(f"Audit: {audit_path}")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())

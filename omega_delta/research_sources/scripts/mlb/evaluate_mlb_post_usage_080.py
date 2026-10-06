#!/usr/bin/env python3
"""Chronological postseason starter-usage challenger 0.8.0.

Research-only. Learns a POST workload factor from prior-season matched pitcher
exposure (actual BF / outs) between the late-regular control and postseason,
then applies ONLY that opportunity factor to the production K distribution's
structural exposure for later postseason seasons.

No K outcomes are used to learn the usage factor.
No betting markets are required or fabricated.
2015 is warm-up only because no prior postseason season exists in this study.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from random import Random
from statistics import fmean, median
from typing import Any
import argparse
import hashlib
import importlib.util
import json
import os
import uuid

VERSION = "0.8.0"
LINEAGE = "mlb-post-usage-oos-v0.8.0-prior-season-matched-bf-2026-09-19"
BASELINE_VARIANT = "POST_HISTORY_PROXY"
CHALLENGER_VARIANT = "POST_USAGE_OOS"
SEED = 190926
BOOTSTRAP_REPS = 4000


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise ValueError(f"{path}:{n}: invalid JSON: {exc}") from exc
    return rows


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


def resolve_pointer(root: Path, pointer_rel: str, leaf: str) -> Path:
    p = root / pointer_rel
    if not p.exists():
        raise FileNotFoundError(p)
    d = root / p.read_text(encoding="utf-8").strip()
    out = d / leaf
    if not out.exists():
        raise FileNotFoundError(out)
    return out


def ip_to_outs(v: Any) -> float | None:
    if v in (None, ""):
        return None
    s = str(v)
    if "." not in s:
        try:
            return float(int(s) * 3)
        except Exception:
            return None
    whole, rem = s.split(".", 1)
    try:
        w = int(whole)
        r = int(rem[:1])
    except Exception:
        return None
    if r not in (0, 1, 2):
        return None
    return float(w * 3 + r)


def player_id(row: dict[str, Any]) -> str:
    kp = row.get("k_projection") or {}
    x = kp.get("officialMlbId")
    return "" if x in (None, "") else str(x)


def target_workload_index(rows: list[dict[str, Any]]) -> dict[tuple[int, str, str], dict[str, float]]:
    out: dict[tuple[int, str, str], dict[str, float]] = {}
    for g in rows:
        season = int(g["season"])
        gid = str(g.get("game_id") or g.get("game_pk"))
        for side in ("away", "home"):
            st = (g.get(side) or {}).get("starter") or {}
            pid = str(st.get("mlb_id") or "")
            if not pid:
                continue
            bf = st.get("batters_faced")
            try:
                bf_n = float(bf)
            except Exception:
                bf_n = None
            outs = ip_to_outs(st.get("innings_pitched"))
            if bf_n is None or bf_n <= 0 or outs is None or outs <= 0:
                continue
            out[(season, gid, pid)] = {"bf": bf_n, "outs": outs}
    return out


def successful_workload_samples(
    ledger: list[dict[str, Any]],
    targets: dict[tuple[int, str, str], dict[str, float]],
) -> dict[tuple[int, str], list[dict[str, float]]]:
    grouped: dict[tuple[int, str], list[dict[str, float]]] = defaultdict(list)
    for r in ledger:
        if str(r.get("market_type", "")).upper() != "K":
            continue
        if str(r.get("workload_proxy_source", "")) != "REGULAR_SEASON_STARTS":
            continue
        pid = player_id(r)
        if not pid:
            continue
        key = (int(r["season"]), str(r["game_id"]), pid)
        actual = targets.get(key)
        if not actual:
            continue
        grouped[(int(r["season"]), pid)].append(actual)
    return grouped


def matched_pitcher_season_ratios(
    reg_samples: dict[tuple[int, str], list[dict[str, float]]],
    post_samples: dict[tuple[int, str], list[dict[str, float]]],
) -> list[dict[str, Any]]:
    rows = []
    for key in sorted(set(reg_samples) & set(post_samples)):
        season, pid = key
        reg = reg_samples[key]
        post = post_samples[key]
        reg_bf = fmean(x["bf"] for x in reg)
        post_bf = fmean(x["bf"] for x in post)
        reg_outs = fmean(x["outs"] for x in reg)
        post_outs = fmean(x["outs"] for x in post)
        if reg_bf <= 0 or reg_outs <= 0:
            continue
        rows.append(
            {
                "season": season,
                "pitcher_id": pid,
                "reg_games": len(reg),
                "post_games": len(post),
                "reg_mean_bf": reg_bf,
                "post_mean_bf": post_bf,
                "bf_ratio": post_bf / reg_bf,
                "reg_mean_outs": reg_outs,
                "post_mean_outs": post_outs,
                "outs_ratio": post_outs / reg_outs,
            }
        )
    return rows


def expanding_factors(ratios: list[dict[str, Any]], seasons: list[int]) -> dict[int, dict[str, Any]]:
    out = {}
    for season in seasons:
        prior = [r for r in ratios if int(r["season"]) < season]
        if not prior:
            out[season] = {
                "status": "WARMUP_NO_PRIOR_POSTSEASON",
                "training_pitcher_seasons": 0,
                "training_seasons": [],
                "bf_factor": None,
                "outs_factor": None,
            }
            continue
        out[season] = {
            "status": "OOS_READY",
            "training_pitcher_seasons": len(prior),
            "training_seasons": sorted({int(r["season"]) for r in prior}),
            # Median gives each pitcher-season equal influence and is robust
            # to injury/short-exit outliers. Direction is not constrained.
            "bf_factor": median(float(r["bf_ratio"]) for r in prior),
            "outs_factor": median(float(r["outs_ratio"]) for r in prior),
        }
    return out


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def usage_adjusted_xk(row: dict[str, Any], bf_factor: float) -> tuple[float, dict[str, Any]]:
    proj = row.get("k_projection") or {}
    c = proj.get("components") or {}
    base_bf = float(c["expectedBF"])
    matchup_k = float(c["matchupK"]) / 100.0
    weights = c.get("blendWeights") or {}
    structural_w = float(weights.get("structural") or 0.0)
    recent_w = float(weights.get("recent") or 0.0)
    season_w = float(weights.get("season") or 0.0)
    if structural_w <= 0:
        raise ValueError("baseline projection missing structural blend weight")

    # Same production normal-starter BF bounds. POST_USAGE changes only the
    # expected opportunity term; pitcher/opponent skill and K-history weights
    # remain exactly as in the baseline projection.
    adjusted_bf = clamp(base_bf * float(bf_factor), 10.0, 33.0)
    adjusted_structural = adjusted_bf * matchup_k
    value = structural_w * adjusted_structural

    recent_k = c.get("recentK")
    season_k = c.get("seasonK")
    if recent_w:
        if recent_k is None:
            raise ValueError("baseline recent weight present but recentK missing")
        value += recent_w * float(recent_k)
    if season_w:
        if season_k is None:
            raise ValueError("baseline season weight present but seasonK missing")
        value += season_w * float(season_k)

    physical_ceiling = max(0.5, min(18.0, adjusted_bf * 0.75))
    xk = clamp(value, 0.15, physical_ceiling)
    return xk, {
        "baseline_expected_bf": base_bf,
        "usage_bf_factor": bf_factor,
        "adjusted_expected_bf": adjusted_bf,
        "baseline_structural_k": float(c["structuralK"]),
        "adjusted_structural_k": adjusted_structural,
        "matchup_k_rate": matchup_k,
        "blend_weights": {
            "structural": structural_w,
            "recent": recent_w,
            "season": season_w,
        },
        "physical_ceiling": physical_ceiling,
    }


def xk_metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    errs = [float(r["xk"]) - float(r["actual_k"]) for r in rows]
    return {
        "n": len(errs),
        "bias": fmean(errs),
        "mae": fmean(abs(e) for e in errs),
        "rmse": sqrt(fmean(e * e for e in errs)),
    }


def paired_bootstrap(
    baseline: list[dict[str, Any]],
    challenger: list[dict[str, Any]],
    reps: int = BOOTSTRAP_REPS,
    seed: int = SEED,
) -> dict[str, Any]:
    def key(r: dict[str, Any]) -> tuple[str, str]:
        return str(r["game_id"]), player_id(r) or str(r.get("pitcher") or "")
    a = {key(r): r for r in baseline}
    b = {key(r): r for r in challenger}
    keys = sorted(set(a) & set(b))
    pairs = []
    for k in keys:
        ar, br = a[k], b[k]
        if int(ar["season"]) != int(br["season"]):
            raise ValueError("paired rows disagree on season")
        if float(ar["actual_k"]) != float(br["actual_k"]):
            raise ValueError("paired rows disagree on actual K")
        ae = float(ar["xk"]) - float(ar["actual_k"])
        be = float(br["xk"]) - float(br["actual_k"])
        pairs.append(
            {
                "season": int(ar["season"]),
                "baseline_error": ae,
                "challenger_error": be,
                "mae_delta": abs(be) - abs(ae),
                "sq_delta": be * be - ae * ae,
                "bias_delta": be - ae,
            }
        )
    if not pairs:
        return {"status": "NO_MATCHED_ROWS"}

    seasons = sorted({p["season"] for p in pairs})
    by_season = {s: [p for p in pairs if p["season"] == s] for s in seasons}
    rng = Random(seed)
    boot = {"mae_delta": [], "rmse_delta": [], "bias_delta": []}
    for _ in range(reps):
        sample = []
        for s in (rng.choice(seasons) for _ in seasons):
            sample.extend(by_season[s])
        boot["mae_delta"].append(fmean(p["mae_delta"] for p in sample))
        base_rmse = sqrt(fmean(p["baseline_error"] ** 2 for p in sample))
        chall_rmse = sqrt(fmean(p["challenger_error"] ** 2 for p in sample))
        boot["rmse_delta"].append(chall_rmse - base_rmse)
        boot["bias_delta"].append(fmean(p["bias_delta"] for p in sample))

    def ci(xs: list[float]) -> list[float]:
        ys = sorted(xs)
        def q(frac: float) -> float:
            pos = (len(ys) - 1) * frac
            lo = int(pos)
            hi = min(len(ys) - 1, lo + 1)
            w = pos - lo
            return ys[lo] * (1 - w) + ys[hi] * w
        return [q(0.025), q(0.975)]

    baseline_rows = [a[k] for k in keys]
    challenger_rows = [b[k] for k in keys]
    bm = xk_metrics(baseline_rows)
    cm = xk_metrics(challenger_rows)
    out = {
        "status": "OK",
        "matched_n": len(keys),
        "seasons": seasons,
        "baseline": bm,
        "challenger": cm,
        "challenger_minus_baseline": {
            "mae": cm["mae"] - bm["mae"],
            "rmse": cm["rmse"] - bm["rmse"],
            "bias": cm["bias"] - bm["bias"],
        },
        "cluster": "season",
        "bootstrap_reps": reps,
        "ci95": {
            "mae_delta": ci(boot["mae_delta"]),
            "rmse_delta": ci(boot["rmse_delta"]),
            "bias_delta": ci(boot["bias_delta"]),
        },
    }
    out["decision"] = (
        "POST_USAGE_IMPROVES_OOS"
        if out["ci95"]["mae_delta"][1] < 0
        and out["ci95"]["rmse_delta"][1] < 0
        and abs(cm["bias"]) < abs(bm["bias"])
        else "NO_CLEAR_POST_USAGE_IMPROVEMENT"
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate chronological POST_USAGE K challenger")
    ap.add_argument("--root", default="/Users/abbeyfelix/Developer/MODEL")
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()

    post_ledger = resolve_pointer(
        root, "data/models/mlb/CURRENT_POSTSEASON_REPLAY_050",
        "MLB_POSTSEASON_HISTORY_PROXY_LEDGER.jsonl"
    )
    reg_ledger = resolve_pointer(
        root, "data/models/mlb/CURRENT_REGULAR_CONTROL_K_071",
        "MLB_REGULAR_CONTROL_K_LEDGER.jsonl"
    )
    post_targets = resolve_pointer(
        root, "data/normalized/mlb/CURRENT_HISTORICAL_OUTCOMES_030",
        "MLB_HISTORICAL_OUTCOMES.jsonl"
    )
    reg_targets = resolve_pointer(
        root, "data/normalized/mlb/CURRENT_REGULAR_CONTROL_070",
        "MLB_REGULAR_CONTROL_TARGETS.jsonl"
    )

    post_rows = [
        r for r in load_jsonl(post_ledger)
        if str(r.get("market_type", "")).upper() == "K"
    ]
    reg_rows = [
        r for r in load_jsonl(reg_ledger)
        if str(r.get("market_type", "")).upper() == "K"
    ]
    p_targets = target_workload_index(load_jsonl(post_targets))
    r_targets = target_workload_index(load_jsonl(reg_targets))
    p_samples = successful_workload_samples(post_rows, p_targets)
    r_samples = successful_workload_samples(reg_rows, r_targets)
    ratios = matched_pitcher_season_ratios(r_samples, p_samples)

    seasons = sorted({int(r["season"]) for r in post_rows})
    factors = expanding_factors(ratios, seasons)

    challenger = []
    paired_baseline = []
    blocked = []
    for r in post_rows:
        season = int(r["season"])
        f = factors[season]
        if f["status"] != "OOS_READY":
            continue
        if str(r.get("workload_proxy_source", "")) != "REGULAR_SEASON_STARTS":
            # Keep opener behavior unchanged; the REG-vs-POST study did not
            # show the positive bias regime in opener-fallback rows.
            continue
        try:
            xk, diag = usage_adjusted_xk(r, float(f["bf_factor"]))
        except Exception as exc:
            blocked.append(
                {"game_id": str(r["game_id"]), "pitcher": r.get("pitcher"), "error": str(exc)}
            )
            continue
        b = dict(r)
        b["model_variant"] = BASELINE_VARIANT
        c = dict(r)
        c["model_variant"] = CHALLENGER_VARIANT
        c["xk"] = xk
        c["post_usage"] = {
            **diag,
            "factor_method": "EXPANDING_PRIOR_SEASONS_MATCHED_PITCHER_SEASON_MEDIAN_BF_RATIO",
            "training_pitcher_seasons": f["training_pitcher_seasons"],
            "training_seasons": f["training_seasons"],
            "outs_factor_diagnostic": f["outs_factor"],
            "k_outcomes_used_to_learn_factor": False,
            "same_season_usage_outcomes_used": False,
        }
        c["thesis"] = "POST_USAGE_PRIOR_SEASON_MATCHED_BF"
        paired_baseline.append(b)
        challenger.append(c)

    comparison = paired_bootstrap(paired_baseline, challenger)
    per_season = {}
    for season in sorted({int(r["season"]) for r in challenger}):
        a = [r for r in paired_baseline if int(r["season"]) == season]
        b = [r for r in challenger if int(r["season"]) == season]
        per_season[str(season)] = {
            "factor": factors[season],
            "baseline": xk_metrics(a),
            "challenger": xk_metrics(b),
            "mae_delta": xk_metrics(b)["mae"] - xk_metrics(a)["mae"],
            "bias_delta": xk_metrics(b)["bias"] - xk_metrics(a)["bias"],
        }

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out_dir = root / "data/models/mlb/post_usage_080" / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    ledger_path = out_dir / "MLB_POST_USAGE_PAIRED_LEDGER.jsonl"
    with ledger_path.open("w", encoding="utf-8") as f:
        for r in sorted(
            paired_baseline + challenger,
            key=lambda x: (
                int(x["season"]), str(x.get("game_date", "")),
                str(x["game_id"]), str(x.get("pitcher", "")),
                str(x.get("model_variant", "")),
            ),
        ):
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")

    audit = {
        "version": VERSION,
        "lineage": LINEAGE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "research_question": "Can prior-season postseason usage alone improve K xK out of sample?",
        "warmup_season": seasons[0] if seasons else None,
        "scored_seasons": [s for s in seasons if factors[s]["status"] == "OOS_READY"],
        "matched_pitcher_season_ratios": ratios,
        "expanding_usage_factors": {str(k): v for k, v in factors.items()},
        "comparison": comparison,
        "per_season": per_season,
        "blocked": blocked,
        "blocked_n": len(blocked),
        "production_model_mutation": False,
        "model_refit_performed": False,
        "k_outcomes_used_to_learn_usage_factor": False,
        "historical_k_market": "NOT_ACQUIRED",
        "oddsPapi_requests": 0,
        "post_ledger": str(post_ledger),
        "post_ledger_sha256": sha256_file(post_ledger),
        "reg_ledger": str(reg_ledger),
        "reg_ledger_sha256": sha256_file(reg_ledger),
        "post_targets": str(post_targets),
        "post_targets_sha256": sha256_file(post_targets),
        "reg_targets": str(reg_targets),
        "reg_targets_sha256": sha256_file(reg_targets),
        "paired_ledger": str(ledger_path),
        "paired_ledger_sha256": sha256_file(ledger_path),
    }
    audit_path = out_dir / "POST_USAGE_OOS_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    atomic_write(
        root / "data/models/mlb/CURRENT_POST_USAGE_080",
        str(out_dir.relative_to(root)) + "\n",
    )

    print()
    print(f"MLB POST_USAGE OOS CHALLENGER {VERSION}")
    print(f"Matched REG/POST pitcher-seasons for usage learning: {len(ratios)}")
    for season in seasons:
        f = factors[season]
        if f["status"] == "OOS_READY":
            print(
                f"{season}: BF factor {f['bf_factor']:.4f} · outs factor {f['outs_factor']:.4f} · "
                f"training pitcher-seasons {f['training_pitcher_seasons']} · "
                f"through {max(f['training_seasons'])}"
            )
        else:
            print(f"{season}: WARMUP · no prior postseason season")
    print()
    print(
        f"Paired OOS rows: {comparison.get('matched_n', 0)} · "
        f"blocked transformations: {len(blocked)}"
    )
    if comparison.get("status") == "OK":
        b = comparison["baseline"]
        c = comparison["challenger"]
        d = comparison["challenger_minus_baseline"]
        ci = comparison["ci95"]
        print(
            f"BASELINE: MAE {b['mae']:.3f} · RMSE {b['rmse']:.3f} · bias {b['bias']:+.3f}"
        )
        print(
            f"POST_USAGE: MAE {c['mae']:.3f} · RMSE {c['rmse']:.3f} · bias {c['bias']:+.3f}"
        )
        print(
            f"DELTA challenger-baseline: MAE {d['mae']:+.3f} "
            f"95% CI [{ci['mae_delta'][0]:+.3f}, {ci['mae_delta'][1]:+.3f}]"
        )
        print(
            f"DELTA challenger-baseline: RMSE {d['rmse']:+.3f} "
            f"95% CI [{ci['rmse_delta'][0]:+.3f}, {ci['rmse_delta'][1]:+.3f}]"
        )
        print(
            f"DELTA challenger-baseline: bias {d['bias']:+.3f} "
            f"95% CI [{ci['bias_delta'][0]:+.3f}, {ci['bias_delta'][1]:+.3f}]"
        )
        print(f"Decision: {comparison['decision']}")
    print("K outcomes used to learn usage factor: NO")
    print("Production mutation: NO · refit: NO · OddsPapi: 0")
    print(f"Paired ledger: {ledger_path}")
    print(f"Audit: {audit_path}")
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""OMEGA 0.24 — freeze a downstream role-adjusted tackle challenger.

This script NEVER modifies frozen OMEGA. It reads the immutable OMEGA prospective
ledger, accepts explicit pregame role-adjusted xTC means with uncertainty bounds,
and writes a separate immutable challenger ledger. The adjustment changes exposure
only: tackle-rate/opportunity structure remains inherited from the frozen OMEGA row.

For each player, implied corrected snap share is derived by proportional exposure
rescaling: corrected_share = original_share * corrected_mean / original_mean.
The frozen OMEGA NB_ROLE count-distribution parameters are then reused without refit.
No sportsbook or realized outcome data are read.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse, csv, hashlib, json, math, os, shutil, sys

SCHEMA = "OMEGA_ROLE_ADJUSTED_CHALLENGER_0.24.0"
LINEAGE = "omega-role-adjusted-challenger-v0.24.0"

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def sha(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def read_csv(path: Path):
    with path.open(newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, rows):
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields: fields.append(k)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        w.writeheader(); w.writerows(rows)

def parse_adjustment(raw: str):
    # player|mean|low|high|role_evidence
    parts=[x.strip() for x in raw.split("|",4)]
    if len(parts)!=5:
        raise argparse.ArgumentTypeError("adjustment must be player|mean|low|high|role_evidence")
    name,mean,low,high,evidence=parts
    try: mean=float(mean); low=float(low); high=float(high)
    except Exception: raise argparse.ArgumentTypeError("mean/low/high must be numeric")
    if not name or not evidence or not (0<=low<=mean<=high):
        raise argparse.ArgumentTypeError("adjustment requires name/evidence and 0 <= low <= mean <= high")
    return {"player_name":name,"corrected_mean":mean,"low_mean":low,"high_mean":high,"role_evidence":evidence}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    ap.add_argument("--game-id",required=True)
    ap.add_argument("--adjustment",action="append",type=parse_adjustment,required=True)
    ap.add_argument("--provenance-note",required=True)
    ap.add_argument("--pregame-proof-time",default="",help="Latest independently visible timestamp proving the values existed pre-kickoff; informational only")
    a=ap.parse_args(); root=Path(a.root).resolve()

    # Read immutable independent OMEGA probability ledger.
    lptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER"
    if not lptr.exists(): raise SystemExit("FAIL no current OMEGA probability ledger")
    lid=lptr.read_text(encoding="utf-8").strip()
    ldir=root/"data/prospective/nfl/omega/tackle_probability_016"/lid
    ledger=ldir/"OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv"
    sidecar=ldir/"OMEGA_2026_PROSPECTIVE_PROBABILITIES.sha256"
    audit=ldir/"OMEGA_0.16_PROSPECTIVE_AUDIT.json"
    for p in (ledger,sidecar,audit):
        if not p.exists(): raise SystemExit(f"FAIL missing OMEGA artifact: {p}")
    ledger_sha=sha(ledger)
    if sidecar.read_text(encoding="utf-8").strip()!=ledger_sha:
        raise SystemExit("FAIL OMEGA ledger hash mismatch")
    rows=read_csv(ledger)
    game_rows=[r for r in rows if str(r.get("game_id") or "")==a.game_id]
    if not game_rows: raise SystemExit(f"FAIL game not in current OMEGA ledger: {a.game_id}")

    # Load frozen count-distribution params only; no fitting/refitting.
    pptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    if not pptr.exists(): raise SystemExit("FAIL no frozen OMEGA probability pointer")
    psid=pptr.read_text(encoding="utf-8").strip()
    pspecp=root/"data/models/nfl/omega_tackle_016_probability_frozen"/psid/"OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json"
    if not pspecp.exists(): raise SystemExit("FAIL frozen probability spec missing")
    pspec=json.loads(pspecp.read_text(encoding="utf-8"))
    if pspec.get("distributionFamily")!="NB_ROLE": raise SystemExit("FAIL frozen distribution family drift")
    params=pspec["distributionParamsFitThrough2024"]
    sys.path.insert(0,str(root/"packages/models/nfl/omega"))
    import tackle_count_distribution as dist

    by_name={str(r.get("player_name") or "").strip().lower():r for r in game_rows}
    seen=set(); out=[]
    for adj in a.adjustment:
        key=adj["player_name"].lower()
        if key in seen: raise SystemExit(f"FAIL duplicate adjustment: {adj['player_name']}")
        seen.add(key)
        r=by_name.get(key)
        if r is None: raise SystemExit(f"FAIL player not uniquely found in game ledger: {adj['player_name']}")
        om=float(r["predicted_xtc"]); oss=float(r["predicted_snap_share"])
        if om<=0 or oss<=0: raise SystemExit(f"FAIL cannot exposure-rescale nonpositive original row: {adj['player_name']}")
        cm=adj["corrected_mean"]; lm=adj["low_mean"]; hm=adj["high_mean"]
        def implied(m): return min(1.0,max(0.0,oss*m/om))
        cs,ls,hs=implied(cm),implied(lm),implied(hm)
        ct,lt,ht=dist.role_tier(cs),dist.role_tier(ls),dist.role_tier(hs)
        z={
            "game_id":r["game_id"],"season":r["season"],"week":r["week"],"kickoff_utc":r.get("kickoff_utc",""),
            "team":r["team"],"opponent":r["opponent"],"player_id":r["player_id"],"player_name":r["player_name"],
            "position":r.get("position",""),"position_group":r.get("position_group",""),"prior_games":r.get("prior_games",""),
            "original_predicted_xtc":om,"original_predicted_snap_share":oss,"original_role_tier":r.get("distribution_role_tier",""),
            "corrected_predicted_xtc":cm,"corrected_xtc_low":lm,"corrected_xtc_high":hm,
            "corrected_snap_share":cs,"corrected_snap_share_low":ls,"corrected_snap_share_high":hs,
            "corrected_role_tier":ct,"corrected_role_tier_low":lt,"corrected_role_tier_high":ht,
            "exposure_multiplier":cm/om,"role_evidence":adj["role_evidence"],
            "method":"EXPOSURE_ONLY_PROPORTIONAL_RESCALE_OF_FROZEN_OMEGA_XTC",
            "distribution_family":"NB_ROLE_FROZEN_0.16_PARAMS_NO_REFIT",
        }
        for line in [x+0.5 for x in range(15)]:
            tag=str(line).replace(".","_")
            pc=dist.over_probability(line,cm,"NB_ROLE",params,ct)
            pl=dist.over_probability(line,lm,"NB_ROLE",params,lt)
            ph=dist.over_probability(line,hm,"NB_ROLE",params,ht)
            z[f"p_over_{tag}"]=pc; z[f"p_under_{tag}"]=1-pc
            z[f"p_over_lowmean_{tag}"]=pl; z[f"p_over_highmean_{tag}"]=ph
            z[f"fair_over_{tag}"]=dist.fair_american(pc); z[f"fair_under_{tag}"]=dist.fair_american(1-pc)
        out.append(z)

    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload_key="|".join(f"{x['player_id']}:{x['corrected_predicted_xtc']:.4f}" for x in sorted(out,key=lambda x:x['player_id']))
    digest=hashlib.sha256((ledger_sha+"|"+a.game_id+"|"+payload_key+"|"+a.provenance_note).encode()).hexdigest()
    sid=f"{stamp}_{digest[:8]}"
    base=root/"data/prospective/nfl/omega_role_adjusted_challenger_0240"
    final=base/sid; staging=base/("."+sid+".staging")
    base.mkdir(parents=True,exist_ok=True)
    if final.exists() or staging.exists(): raise SystemExit("FAIL challenger bundle already exists")
    staging.mkdir(parents=True,exist_ok=False)
    try:
        cp=staging/"OMEGA_0.24_ROLE_ADJUSTED_CHALLENGER.csv"; write_csv(cp,out); csha=sha(cp)
        manifest={
            "schemaVersion":SCHEMA,"lineage":LINEAGE,"challengerId":sid,"packagedAt":now(),"status":"POST_KICKOFF_PACKAGING_OF_PREKICKOFF_CHALLENGER_VALUES",
            "gameId":a.game_id,"rows":len(out),"sourceOmegaLedgerId":lid,"sourceOmegaLedgerSha256":ledger_sha,
            "sourceProspectiveAuditSha256":sha(audit),"frozenProbabilitySpecSha256":sha(pspecp),"challengerCsvSha256":csha,
            "provenance":{"note":a.provenance_note,"pregameProofTime":a.pregame_proof_time,"exactChatMessageTimestampPersistedInRepo":False},
            "method":{"changedComponent":"EXPOSURE_ONLY","tackleRateChanged":False,"teamOpportunityModelChanged":False,"distributionRefit":False,"marketDataEnteredProjection":False,"formula":"corrected_xTC = original_xTC * corrected_snap_share / original_snap_share","uncertainty":"low/high xTC bounds are explicit pregame role-uncertainty values; each is converted to implied snap share and frozen NB_ROLE tier independently"},
            "integrity":{"omegaModelModified":False,"omegaLedgerReadOnly":True,"outcomesRead":0,"marketFieldsRead":0,"oddsPapiPlayerPropRequests":0,"retroactiveOutcomeAdjustment":False}
        }
        mp=staging/"OMEGA_0.24_ROLE_ADJUSTED_MANIFEST.json"; mp.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        (staging/"OMEGA_0.24_ROLE_ADJUSTED_MANIFEST.sha256").write_text(sha(mp)+"\n",encoding="utf-8")
        os.replace(staging,final)
        ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_ROLE_ADJUSTED_CHALLENGER"; tmp=ptr.with_name("."+ptr.name+".tmp")
        tmp.write_text(sid+"\n",encoding="utf-8"); os.replace(tmp,ptr)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

    print("OMEGA 0.24 — ROLE-ADJUSTED CHALLENGER FREEZE")
    print(f"PASS challenger {sid} · game {a.game_id} · rows {len(out)}")
    print(f"PASS source OMEGA {ledger_sha} · read-only")
    print("PASS exposure-only adjustment · tackle rates unchanged · NB_ROLE params frozen/no refit")
    print("PASS market fields read 0 · outcomes read 0 · OMEGA writes 0")
    for r in sorted(out,key=lambda x:-float(x['corrected_predicted_xtc'])):
        print(f"  {r['player_name']}: {r['original_predicted_xtc']:.2f} -> {r['corrected_predicted_xtc']:.2f} T+A · snap {100*r['original_predicted_snap_share']:.1f}% -> {100*r['corrected_snap_share']:.1f}% · range {r['corrected_xtc_low']:.2f}-{r['corrected_xtc_high']:.2f}")
    print(f"MANIFEST: {final/'OMEGA_0.24_ROLE_ADJUSTED_MANIFEST.json'}")
    return 0

if __name__=="__main__": raise SystemExit(main())

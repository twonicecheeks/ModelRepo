#!/usr/bin/env python3
"""OMEGA 0.36.1 — prospective LB-only position challenger shadow.

Uses:
- immutable pre-Thursday Week-2 OMEGA 0.33 control rows,
- development-only OMEGA 0.36 serialized models fit through 2024,
- frozen OMEGA NB_ROLE distribution parameters.

No 2026 outcome, market, or sportsbook data is read. Rows whose kickoff has already
occurred at build time are excluded. LB receives the 0.36 residual mean adjustment;
DB and DL remain exact control. Distribution/dispersion tier is held fixed to the
control H012 tier so the prospective comparison isolates the LB mean correction.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import csv
import hashlib
import json
import os
import sys
import uuid

VERSION="0.36.1"
SCHEMA="OMEGA_WEEK2_POSITION_SHADOW_0.36.1"


def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()


def rcsv(path:Path)->list[dict[str,str]]:
    with path.open(newline="",encoding="utf-8-sig") as f:return list(csv.DictReader(f))


def wcsv(path:Path,rows:list[dict[str,Any]])->None:
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields or ["status"],extrasaction="ignore",lineterminator="\n")
        w.writeheader()
        for r in rows:w.writerow({k:"" if r.get(k) is None else r.get(k) for k in fields})


def parse_ts(v:Any)->datetime:
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def atomic(path:Path,text:str)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name("."+path.name+".tmp")
    tmp.write_text(text.rstrip()+"\n",encoding="utf-8")
    os.replace(tmp,path)


def resolve_position_artifact(root:Path):
    ptr=root/"data/models/nfl/CURRENT_OMEGA_POSITION_CHALLENGER_0360"
    if not ptr.exists():raise FileNotFoundError("OMEGA 0.36 artifact pointer missing")
    oid=ptr.read_text(encoding="utf-8").strip()
    d=root/"data/models/nfl/omega_position_challenger_0360"/oid
    rp=d/"OMEGA_0.36_POSITION_CHALLENGER_BAKEOFF.json"
    mp=d/"OMEGA_0.36_POSITION_CHALLENGER_MODELS.json"
    for p in (rp,mp):
        if not p.exists():raise FileNotFoundError(p)
    return oid,d,json.loads(rp.read_text(encoding="utf-8")),json.loads(mp.read_text(encoding="utf-8"))


def resolve_week2_freeze(root:Path):
    ptr=root/"data/prospective/nfl/omega/CURRENT_OMEGA_WEEK2_DUAL_TRACK_FREEZE"
    if not ptr.exists():raise FileNotFoundError("Week 2 dual-track pointer missing")
    fid=ptr.read_text(encoding="utf-8").strip()
    d=root/"data/prospective/nfl/omega_week2_dual_track_0330"/fid
    cp=d/"OMEGA_0.33_WEEK2_DUAL_TRACK.csv";mp=d/"OMEGA_0.33_WEEK2_MANIFEST.json";hp=d/"OMEGA_OUTPUT_HASHES.json"
    for p in (cp,mp,hp):
        if not p.exists():raise FileNotFoundError(p)
    hashes=json.loads(hp.read_text(encoding="utf-8"))
    if hashes.get(cp.name)!=sha(cp) or hashes.get(mp.name)!=sha(mp):
        raise ValueError("Week 2 freeze hash mismatch")
    return fid,d,json.loads(mp.read_text(encoding="utf-8")),cp


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL")
    args=ap.parse_args();root=Path(args.root).expanduser().resolve()
    sys.path[:0]=[str(root/"packages/models/nfl/omega")]
    import position_specific_challenger_0360 as pc
    import tackle_count_distribution as dist

    oid,odir,bake,models=resolve_position_artifact(root)
    if bake.get("positionTaxonomy")!="RAW_POSITION_PRECEDENCE_V1":
        raise SystemExit("FAIL OMEGA 0.36 artifact predates hardened edge-defender taxonomy; rerun analyze_omega_position_specific_challenger_0360.command")
    gates=bake.get("gateSummary",{})
    if gates.get("LB")!="NEXT_STAGE_SHADOW_SIGNAL":
        raise SystemExit(f"FAIL LB has not cleared historical shadow gate: {gates.get('LB')}")
    if gates.get("DB")=="NEXT_STAGE_SHADOW_SIGNAL":
        raise SystemExit("FAIL DB unexpectedly cleared gate; 0.36.1 is intentionally LB-only")
    if gates.get("DL")!="KEEP_CONTROL":
        raise SystemExit("FAIL DL control-preservation gate drift")
    if bake.get("holdoutOpened") is not False or int(bake.get("prospectiveRowsRead") or 0)!=0:
        raise SystemExit("FAIL OMEGA 0.36 development integrity drift")

    lb=pc.ResidualModel.from_dict(models["LB"])
    fid,fdir,fmeta,dual=resolve_week2_freeze(root)
    rows=rcsv(dual)
    if not rows:raise SystemExit("FAIL empty Week 2 control freeze")
    now=datetime.now(timezone.utc)
    future=[]
    excluded_games=set()
    for r in rows:
        ko=parse_ts(r.get("kickoff_utc"))
        if ko<=now:
            excluded_games.add(str(r.get("game_id") or ""))
            continue
        future.append(dict(r))
    if not future:
        raise SystemExit("FAIL no future Week 2 rows remain for prospective shadow")

    pptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN"
    sid=pptr.read_text(encoding="utf-8").strip()
    pspec=root/"data/models/nfl/omega_tackle_016_probability_frozen"/sid/"OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json"
    pmeta=json.loads(pspec.read_text(encoding="utf-8"))
    params=pmeta["distributionParamsFitThrough2024"]

    out=[];lb_n=0;shifted=0;reclassified=[]
    for r in future:
        z=dict(r)
        pos=pc.canonical_position_row(r)
        source_group=pc.canonical_position(r.get("position_group"))
        if pos!=source_group:
            reclassified.append({
                "game_id":r.get("game_id"),"player_id":r.get("player_id"),"player_name":r.get("player_name"),
                "raw_position":r.get("position"),"source_position_group":r.get("position_group"),"challenger_position_group":pos,
            })
        base=max(0.0,pc.num(r.get("control_xtc")))
        if pos=="LB":
            shadow=lb.predict(r);track="LB_RESIDUAL_SHADOW";lb_n+=1
            if abs(shadow-base)>1e-12:shifted+=1
        elif pos=="DL":
            shadow=base;track="DL_CONTROL_NO_CHANGE"
        elif pos=="DB":
            shadow=base;track="DB_CONTROL_NO_PROMOTION"
        else:
            shadow=base;track="CONTROL_FALLBACK"
        tier=str(r.get("control_distribution_role_tier") or "")
        if not tier:
            tier=dist.role_tier(pc.num(r.get("control_h012_snap_share")))
        z.update({
            "position_shadow_version":VERSION,
            "position_shadow_model_artifact":oid,
            "position_shadow_track":track,
            "position_shadow_xtc":shadow,
            "position_shadow_delta_xtc":shadow-base,
            "position_shadow_distribution_role_tier":tier,
            "position_shadow_dispersion_policy":"FIXED_CONTROL_H012_TIER",
            "position_shadow_status":"SHADOW_ONLY_NOT_PROMOTED",
            "position_shadow_market_dependency":"FALSE",
        })
        for whole in range(15):
            line=whole+.5;tag=str(line).replace(".","_")
            po=dist.over_probability(line,shadow,"NB_ROLE",params,tier)
            z[f"position_shadow_p_over_{tag}"]=po
            z[f"position_shadow_p_under_{tag}"]=1-po
            z[f"position_shadow_fair_over_{tag}"]=dist.fair_american(po)
            z[f"position_shadow_fair_under_{tag}"]=dist.fair_american(1-po)
        out.append(z)

    run_id=now.strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
    final=root/"data/prospective/nfl/omega_position_shadow_0361"/run_id
    final.mkdir(parents=True,exist_ok=False)
    csvp=final/"OMEGA_0.36.1_WEEK2_POSITION_SHADOW.csv";wcsv(csvp,out)
    audit={
        "schemaVersion":SCHEMA,"version":VERSION,"createdAt":now.isoformat(),"runId":run_id,
        "sourceWeek2FreezeId":fid,"sourceWeek2FreezeSha256":sha(dual),
        "sourcePositionArtifactId":oid,"sourcePositionBakeoffSha256":sha(odir/"OMEGA_0.36_POSITION_CHALLENGER_BAKEOFF.json"),
        "rows":len(out),"games":len({r["game_id"] for r in out}),"lbRows":lb_n,"lbShiftedRows":shifted,
        "positionTaxonomy":"RAW_POSITION_PRECEDENCE_V1","reclassifiedRows":reclassified,
        "excludedAlreadyStartedGames":sorted(excluded_games),
        "gateSummary":gates,
        "trackPolicy":{"LB":"0.36 residual shadow","DB":"frozen control","DL":"frozen control"},
        "dispersionPolicy":"FIXED_CONTROL_H012_TIER",
        "hypothesisTiming":"post-DET-BUF discovery; model parameters fit development-only 2017-2024",
        "sourceForecastTiming":"OMEGA 0.33 rows were frozen before Week 2 earliest kickoff",
        "integrity":{"2026OutcomeRowsRead":0,"marketFieldsRead":0,"oddsPapiRequests":0,
                     "frozenOmegaMutation":False,"productionPromotion":False,"modelRefits":0},
        "nextGate":"JOIN_ONLY_TO_FRESH_PREKICK_MARKET_ROWS_FOR_SHADOW_COMPARISON",
    }
    apath=final/"OMEGA_0.36.1_WEEK2_POSITION_SHADOW_AUDIT.json";apath.write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    (final/"OMEGA_OUTPUT_HASHES.json").write_text(json.dumps({csvp.name:sha(csvp),apath.name:sha(apath)},indent=2)+"\n",encoding="utf-8")
    atomic(root/"data/prospective/nfl/omega/CURRENT_OMEGA_POSITION_SHADOW_0361",str(final.relative_to(root)))
    print("OMEGA 0.36.1 — WEEK 2 POSITION-SPECIFIC PROSPECTIVE SHADOW")
    print(f"PASS future games {audit['games']} · rows {len(out)} · LB rows {lb_n} · shifted {shifted}")
    print(f"PASS LB shadow only · DB control · DL control · already-started games excluded {len(excluded_games)}")
    print(f"PASS hardened position taxonomy · reclassified rows {len(reclassified)}")
    for rr in reclassified[:20]:
        print(f"  RECLASS {rr['player_name']} · {rr['raw_position']}/{rr['source_position_group']} -> {rr['challenger_position_group']}")
    print("PASS frozen control dispersion · outcomes 0 · market fields 0 · frozen OMEGA mutation NO")
    print(f"SHADOW: {csvp}")
    print(f"AUDIT: {apath}")
    return 0

if __name__=="__main__":raise SystemExit(main())

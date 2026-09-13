#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib, json, re, sys, zipfile

EXPECTED_SCHEMA = "OMEGA_PM_NFL_TA_DIRECT_CAPTURE_0.17.6"
EXPECTED_SLUG = "player-tackles-assists"
TOKENS = ("book","sportsbook","operator","provider","price","odds","selection","market","line")

def now_stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def first(*vals):
    for v in vals:
        if v is not None and v != "":
            return v
    return None

def obj(*vals):
    for v in vals:
        if isinstance(v,dict):
            return v
    return {}

def candidate_direct_book(entry):
    if not isinstance(entry,dict):
        return None
    root=obj(entry.get("offer"),entry)
    bet=obj(root.get("bet"),entry.get("bet"))
    for container in (bet,root,entry):
        for key in ("sportsbook","sportsBook","book","operator","provider"):
            v=container.get(key)
            if isinstance(v,dict):
                x=first(v.get("name"),v.get("slug"),v.get("code"),v.get("id"))
                if x is not None:
                    return str(x)
            elif isinstance(v,(str,int,float)) and v != "":
                return str(v)
    return None

def collect_interesting_paths(x, path="$", depth=0, out=None):
    if out is None:
        out=[]
    if depth > 9:
        return out
    if isinstance(x,dict):
        for k,v in x.items():
            kp=f"{path}.{k}"
            lk=str(k).lower()
            if any(t in lk for t in TOKENS):
                preview=v
                if isinstance(v,(dict,list)):
                    try:
                        preview=json.dumps(v,ensure_ascii=False,separators=(",",":"))[:1500]
                    except Exception:
                        preview=str(type(v).__name__)
                else:
                    preview=str(v)[:500]
                out.append({"path":kp,"valueType":type(v).__name__,"preview":preview})
            if isinstance(v,(dict,list)):
                collect_interesting_paths(v,kp,depth+1,out)
    elif isinstance(x,list):
        for i,v in enumerate(x[:100]):
            collect_interesting_paths(v,f"{path}[{i}]",depth+1,out)
    return out

def shape(x, depth=0):
    if depth>5:
        return type(x).__name__
    if isinstance(x,dict):
        return {str(k):shape(v,depth+1) for k,v in x.items()}
    if isinstance(x,list):
        return [shape(x[0],depth+1)] if x else []
    return type(x).__name__

def main():
    downloads=Path.home()/"Downloads"
    caps=sorted(downloads.glob("OMEGA_0176_PROPSMADNESS_NFL_TA_DIRECT_CAPTURE_*.json"),
                key=lambda p:p.stat().st_mtime, reverse=True)
    if not caps:
        raise SystemExit("FAIL no OMEGA 0.17.6 direct capture found in ~/Downloads")
    src=caps[0]
    raw=src.read_bytes()
    try:
        data=json.loads(raw)
    except Exception as e:
        raise SystemExit(f"FAIL capture is not valid JSON: {e}")
    if data.get("schemaVersion") != EXPECTED_SCHEMA:
        raise SystemExit(f"FAIL wrong capture schema: {data.get('schemaVersion')}")
    if data.get("marketSlug") != EXPECTED_SLUG:
        raise SystemExit("FAIL wrong market slug")

    req=data.get("requests") or {}
    market=(req.get("market") or {}).get("data")
    if not isinstance(market,dict) or not isinstance(market.get("offers"),list):
        raise SystemExit("FAIL market offers[] missing")
    offers=market["offers"]

    missing=[]
    direct=0
    for i,e in enumerate(offers):
        book=candidate_direct_book(e)
        if book:
            direct+=1
            continue
        paths=collect_interesting_paths(e)
        missing.append({
            "rawIndex":i,
            "topLevelKeys":sorted(e.keys()) if isinstance(e,dict) else [],
            "shape":shape(e),
            "interestingPaths":paths,
            "rawOffer":e
        })

    if not missing:
        raise SystemExit("FAIL diagnostic found zero missing-direct-sportsbook rows; state differs from observed 0.17.7 failure")

    path_counts=Counter()
    value_examples={}
    for row in missing:
        for p in row["interestingPaths"]:
            path_counts[p["path"]]+=1
            value_examples.setdefault(p["path"],p["preview"])

    summary={
        "schemaVersion":"OMEGA_PM_NFL_TA_SPORTSBOOK_SCHEMA_DIAGNOSTIC_0.17.9",
        "generatedAt":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "sourceFile":str(src),
        "sourceSha256":hashlib.sha256(raw).hexdigest(),
        "marketSlug":EXPECTED_SLUG,
        "totalOffers":len(offers),
        "directSportsbookRows":direct,
        "missingDirectSportsbookRows":len(missing),
        "missingDirectRate":len(missing)/len(offers) if offers else None,
        "interestingPathCounts":[
            {"path":k,"count":v,"example":value_examples.get(k)}
            for k,v in path_counts.most_common()
        ],
        "marketTopLevelKeys":sorted(market.keys()),
        "credentialFieldsCaptured":0,
        "marketSnapshotAppended":False,
        "omegaIRead":False,
        "omegaIWritten":False,
        "oddsPapiRequests":0
    }

    stamp=now_stamp()
    sid=f"{stamp}_{summary['sourceSha256'][:8]}"
    root=Path("/Users/abbeyfelix/Developer/MODEL")
    outdir=root/"data/raw/nfl/omega/propsmadness_ta_schema_diagnostic_0179"/sid
    outdir.mkdir(parents=True,exist_ok=False)
    (outdir/"OMEGA_0.17.9_SPORTSBOOK_SCHEMA_SUMMARY.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
    (outdir/"OMEGA_0.17.9_MISSING_SPORTSBOOK_OFFERS.json").write_text(json.dumps({
        "schemaVersion":"OMEGA_PM_NFL_TA_MISSING_SPORTSBOOK_ROWS_0.17.9",
        "rows":missing
    },indent=2,ensure_ascii=False)+"\n")

    handoff=downloads/"OMEGA_0179_PROPSMADNESS_SPORTSBOOK_SCHEMA_HANDOFF.zip"
    if handoff.exists():
        handoff.unlink()
    with zipfile.ZipFile(handoff,"w",zipfile.ZIP_DEFLATED) as z:
        z.write(outdir/"OMEGA_0.17.9_SPORTSBOOK_SCHEMA_SUMMARY.json",
                "OMEGA_0179_HANDOFF/OMEGA_0.17.9_SPORTSBOOK_SCHEMA_SUMMARY.json")
        z.write(outdir/"OMEGA_0.17.9_MISSING_SPORTSBOOK_OFFERS.json",
                "OMEGA_0179_HANDOFF/OMEGA_0.17.9_MISSING_SPORTSBOOK_OFFERS.json")

    print()
    print("OMEGA 0.17.9 — PROPSMADNESS SPORTSBOOK SCHEMA DIAGNOSTIC")
    print()
    print(f"PASS endpoint offers {len(offers)}")
    print(f"PASS direct sportsbook rows {direct} · missing-direct sportsbook rows {len(missing)} ({len(missing)/len(offers):.1%})")
    print(f"PASS unique interesting paths {len(path_counts)}")
    print("PASS market snapshot appended: NO · OMEGA-I reads/writes 0 · OddsPapi 0 · network requests 0")
    print()
    print("TOP NESTED BOOK/PRICE/ODDS PATHS:")
    for item in summary["interestingPathCounts"][:20]:
        print(f"  {item['count']:>3} × {item['path']} :: {str(item['example'])[:180]}")
    print()
    print("UPLOAD:",handoff)

if __name__=="__main__":
    raise SystemExit(main())

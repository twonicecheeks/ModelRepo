#!/usr/bin/env python3
"""Build OMEGA 0.12 immutable blind 2025 tackle-count prediction ledger.

The exact OMEGA 0.11 frozen spec is verified before any 2025 tackle work. Global
models are fit on 2017-2024 REG only with frozen hyperparameters. 2025 is simulated
week-by-week: all predictions for a week are emitted before that week's realized
football/tackle history is admitted to rolling state for later weeks.

Historical count evaluation remains conditional on players who actually logged >0
defensive snaps in the target game. Target-game snap *magnitude* and tackle outcomes
are never model inputs and are never serialized into the blind ledger. This known
participant-universe limitation is part of the frozen 0.11 contract.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
import argparse, csv, hashlib, json, os, shutil, sys
from typing import Any

SCHEMA = "OMEGA_TACKLE_BLIND_2025_0.12"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})
    return fields


def parquet_rows(path: Path, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> tuple[list[dict[str, Any]], set[str]]:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    names = set(pf.schema_arrow.names)
    missing = [c for c in required if c not in names]
    if missing:
        raise ValueError(f"{path.name} missing required parquet column(s): {', '.join(missing)}")
    cols = list(required) + [c for c in optional if c in names and c not in required]
    return pf.read(columns=cols).to_pylist(), names


def load_player_meta(root: Path, asset: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    import pyarrow.parquet as pq
    path = root / asset["blobPath"]
    pf = pq.ParquetFile(path); names = set(pf.schema_arrow.names)
    required = {"gsis_id", "display_name", "position", "position_group"}
    if not required <= names:
        raise ValueError(f"players parquet missing: {sorted(required-names)}")
    cols = ["gsis_id", "display_name", "position", "position_group"]
    if "pfr_id" in names: cols.append("pfr_id")
    by_gsis: dict[str, dict[str, Any]] = {}; pfr_to_gsis: dict[str, str] = {}
    for r in pf.read(columns=cols).to_pylist():
        gsis = str(r.get("gsis_id") or "").strip()
        if not gsis: continue
        pfr = str(r.get("pfr_id") or "").strip()
        by_gsis[gsis] = {"display_name":str(r.get("display_name") or "").strip(), "position":str(r.get("position") or "").strip(), "position_group":str(r.get("position_group") or "").strip(), "pfr_id":pfr}
        if pfr: pfr_to_gsis[pfr] = gsis
    return by_gsis, pfr_to_gsis


def phase2f_2025_snap_asset(root: Path, sid: str) -> dict[str, Any]:
    base = root / "data/raw/nfl/nflverse/phase2f_holdout/snapshots"
    candidates: list[tuple[str, dict[str, Any]]] = []
    for mp in base.glob("*/SOURCE_MANIFEST.json"):
        try:
            d = json.loads(mp.read_text(encoding="utf-8")); a = d.get("asset", {})
            if d.get("sourcePhase1SnapshotId") != sid or int(d.get("season") or 0) != 2025: continue
            p = root / a.get("blobPath", "")
            if p.exists() and sha256_file(p) == a.get("sha256"):
                candidates.append((str(d.get("createdAt") or ""), a))
        except Exception:
            pass
    if not candidates:
        raise SystemExit("FAIL verified 2025 snap-count asset missing. Re-run the already-consumed NFL Phase2F holdout input acquisition; OMEGA 0.12 will not make a network request.")
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def normalize_team(contract: Any, v: Any) -> str:
    s = str(v or "").strip()
    return contract.normalize_team_abbr(s) if s else ""


def snap_share(r: dict[str, Any], team_snap_totals: dict[tuple[str,str], float], xb: Any) -> float | None:
    p = xb.normalize_pct(r.get("defense_pct"))
    if p is not None: return p
    s = xb.num(r.get("defense_snaps")); total = team_snap_totals.get((str(r.get("game_id") or ""), str(r.get("team") or "")))
    if s is None or total is None or total <= 0: return None
    return max(0.0, min(1.0, float(s)/float(total)))


def role_feature_row(pid: str, pg: str, h: list[float], pos_sum: dict[str,float], pos_n: dict[str,int], er: Any) -> dict[str, float]:
    prior = pos_sum[pg]/pos_n[pg] if pos_n[pg] else 0.35
    last1 = h[-1] if h else prior; l2=h[-2:]; l4=h[-4:]; l8=h[-8:]
    m2=er.mean_or(l2,prior); m4=er.mean_or(l4,prior); m8=er.mean_or(l8,prior)
    return {
        "position_prior_snap_share": prior, "prior_games_cap8": min(8,len(h))/8.0, "prior_games_log": __import__('math').log1p(len(h)),
        "last1_snap_share": last1, "last2_snap_share_mean":m2, "last4_snap_share_mean":m4, "last8_snap_share_mean":m8,
        "last4_snap_share_std":er.std_or_zero(l4), "last4_snap_share_min":min(l4) if l4 else prior, "last4_snap_share_max":max(l4) if l4 else prior,
        "last1_minus_last4":last1-m4, "last2_minus_last8":m2-m8,
        "position_DB":1.0 if pg=="DB" else 0.0, "position_LB":1.0 if pg=="LB" else 0.0, "position_DL":1.0 if pg=="DL" else 0.0,
        "position_OTHER":1.0 if pg not in {"DB","LB","DL"} else 0.0, "cold_start":1.0 if len(h)==0 else 0.0, "one_prior_game":1.0 if len(h)==1 else 0.0,
    }


def team_feature_row(game_id: str, week: int, offense: str, defense: str, off_hist: dict[str,list[dict[str,Any]]], def_hist: dict[str,list[dict[str,Any]]], xb: Any) -> dict[str, Any]:
    oh=xb._summary(off_hist[offense]); dh=xb._summary(def_hist[defense])
    if not oh or not dh: raise ValueError(f"missing team history for {game_id} {offense}@{defense}")
    return {
        "game_id":game_id,"season":2025,"week":week,"offense_team":offense,"defense_team":defense,
        "off_def_snaps_mean8":oh["def_snaps"],"def_def_snaps_mean8":dh["def_snaps"],"off_opportunity_plays_mean8":oh["opportunity_plays"],"def_opportunity_plays_mean8":dh["opportunity_plays"],
        "off_opportunity_rate8":oh["opportunity_rate"],"def_opportunity_rate8":dh["opportunity_rate"],"off_credits_per_opportunity8":oh["credits_per_opportunity"],"def_credits_per_opportunity8":dh["credits_per_opportunity"],
        "off_rush_share8":oh["rush_share"],"off_complete_pass_share8":oh["complete_pass_share"],"off_scramble_share8":oh["scramble_share"],"off_sack_share8":oh["sack_share"],
        "off_games_available8":oh["games"]/xb.TEAM_WINDOW,"def_games_available8":dh["games"]/xb.TEAM_WINDOW,
        "benchmark_defensive_snaps":0.5*(oh["def_snaps"]+dh["def_snaps"]),"benchmark_opportunity_plays":0.5*(oh["opportunity_plays"]+dh["opportunity_plays"]),
    }


def family_share(history: list[dict[str,Any]], families: tuple[str,...], window: int) -> dict[str,float] | None:
    h=history[-window:]; total=sum(float(r.get("total_opportunity_plays") or 0.0) for r in h)
    if total<=0:return None
    return {f:sum(float(r.get(f"opp_{f}") or 0.0) for r in h)/total for f in families}


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="/Users/abbeyfelix/Developer/MODEL"); args=ap.parse_args(); root=Path(args.root).expanduser().resolve()
    sys.path[:0]=[str(root/"packages/models/nfl/omega"), str(root/"packages/providers/nflverse/src")]
    import blind_holdout_2025 as bh, frozen_spec as fs, tackle_events as te, exposure_universe as eu, xto_xtc_baseline as xb, exposure_role_challenger as er, tackle_opportunity_footprint as tf
    import contract

    fptr=root/"data/models/nfl/CURRENT_OMEGA_TACKLE_FROZEN"
    if not fptr.exists(): raise SystemExit("FAIL frozen OMEGA pointer missing")
    sid=fptr.read_text(encoding="utf-8").strip(); frozen=root/"data/models/nfl/omega_tackle_frozen"/sid
    spec_path=frozen/"OMEGA_TACKLE_FROZEN_SPEC.json"; spec_sha=frozen/"OMEGA_TACKLE_FROZEN_SPEC.sha256"
    if not spec_path.exists() or not spec_sha.exists(): raise SystemExit("FAIL frozen OMEGA spec files missing")
    actual_sha=sha256_file(spec_path)
    if spec_sha.read_text(encoding="utf-8").strip()!=actual_sha: raise SystemExit("FAIL frozen spec sidecar hash mismatch")
    if actual_sha!=bh.FROZEN_SPEC_SHA256: raise SystemExit(f"FAIL this blind package is pinned to frozen spec {bh.FROZEN_SPEC_SHA256}, found {actual_sha}")
    spec=json.loads(spec_path.read_text(encoding="utf-8"))
    champ=spec.get("champion",{})
    checks=[(float(champ.get("xTOL2")),fs.XTO_L2,"xTO L2"),(float(champ.get("exposureL2")),fs.EXPOSURE_L2,"exposure L2"),(float(champ.get("familyAlpha")),fs.FAMILY_ALPHA,"family alpha")]
    for got,want,name in checks:
        if abs(got-want)>1e-12: raise SystemExit(f"FAIL frozen {name} drift")
    if tuple(champ.get("families") or ())!=tuple(fs.FAMILIES): raise SystemExit("FAIL frozen families drift")

    out=root/"data/models/nfl/omega_tackle_012_blind_2025"/sid
    pred=out/"OMEGA_2025_BLIND_PREDICTIONS.csv"; pred_sha=out/"OMEGA_2025_BLIND_PREDICTIONS.sha256"
    if out.exists():
        if pred.exists() and pred_sha.exists() and pred_sha.read_text(encoding="utf-8").strip()==sha256_file(pred):
            (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BLIND_2025").write_text(sid+"\n",encoding="utf-8"); print(f"PASS existing immutable OMEGA 2025 blind ledger verified: {out}"); return 0
        raise SystemExit(f"FAIL incomplete/corrupt existing blind output: {out}")

    foundation=root/"data/normalized/nfl/omega_tackle"/sid; exposure_dir=root/"data/normalized/nfl/omega_tackle_exposure"/sid; phase1=root/"data/normalized/nfl/phase1"/sid
    hist_plays=read_csv(foundation/"omega_tackle_play_opportunities.csv"); hist_events=read_csv(foundation/"omega_tackle_credit_events.csv"); hist_exp=read_csv(exposure_dir/"omega_tackle_exposure_player_games.csv")
    if any(int(float(r.get("season") or 0))>=2025 for r in hist_plays+hist_exp): raise SystemExit("FAIL development artifacts unexpectedly contain 2025")

    # Fit exact frozen global models on 2017-2024 only.
    hist_team_out=xb.aggregate_team_game_outcomes(hist_plays,hist_exp); hist_team_rows=xb.build_team_pregame_rows(hist_team_out)
    team_fit=[r for r in hist_team_rows if 2017<=int(r["season"])<=2024]
    if not team_fit: raise SystemExit("FAIL no 2017-2024 team fit rows")
    x_to_model=xb.fit_ridge(team_fit,target_key="actual_opportunity_plays",l2=fs.XTO_L2)
    x_snap_model=xb.fit_ridge(team_fit,target_key="actual_defensive_snaps",l2=fs.XDEFENSIVE_SNAPS_L2)
    hist_team_snaps=xb.estimate_team_defensive_snaps(hist_exp)
    role_rows=er.build_exposure_pregame_rows(hist_exp,hist_team_snaps); role_fit=[r for r in role_rows if 2017<=int(r["season"])<=2024]
    role_model=er.fit_ridge(role_fit,fs.EXPOSURE_L2)

    # Locate existing source assets. This command makes no network requests.
    source_manifest=root/"data/raw/nfl/nflverse/snapshots"/sid/"SOURCE_MANIFEST.json"; manifest=json.loads(source_manifest.read_text(encoding="utf-8")); assets={(x["source"],x.get("season")):x for x in manifest.get("assets",[])}
    player_meta,pfr_to_gsis=load_player_meta(root,assets[("players",None)])
    games=[r for r in read_csv(phase1/"game_identity.csv") if int(r.get("season") or 0)==2025 and str(r.get("game_type") or "")=="REG"]
    if not games: raise SystemExit("FAIL no 2025 REG games in Phase1 identity")
    game_meta={r["game_id"]:r for r in games}; allowed=set(game_meta)

    pbp_asset=assets.get(("play_by_play",2025))
    if not pbp_asset: raise SystemExit("FAIL 2025 PBP asset missing from frozen source snapshot")
    pbp_required=("game_id","play_id","season","week","posteam","defteam")
    pbp_optional=("play_type","no_play","play_deleted","special_teams_play","qtr","down","ydstogo","yardline_100","game_seconds_remaining","score_differential","score_differential_post","yards_gained","air_yards","yards_after_catch","run_location","run_gap","pass_location","pass_length","shotgun","no_huddle","qb_scramble","sack","complete_pass","interception","fumble","fumble_lost","rush_attempt","rush","pass_attempt","qb_dropback")+tuple(te.TACKLE_ID_COLUMNS)+tuple(te.TACKLE_NAME_COLUMNS)+tuple(te.TACKLE_TEAM_COLUMNS)
    raw_pbp,_=parquet_rows(root/pbp_asset["blobPath"],pbp_required,pbp_optional)
    play25=[]; events25=[]
    for r in raw_pbp:
        gid=str(r.get("game_id") or "")
        if gid not in allowed: continue
        if r.get("posteam"): r["posteam"]=normalize_team(contract,r["posteam"])
        if r.get("defteam"): r["defteam"]=normalize_team(contract,r["defteam"])
        ev=te.extract_credit_events(r); events25.extend(ev); play25.append(te.build_play_opportunity_row(r,ev))
    if not play25: raise SystemExit("FAIL no 2025 REG PBP rows reconstructed")

    snap_asset=phase2f_2025_snap_asset(root,sid)
    snap_required=("game_id","season","game_type","week","pfr_player_id","position","team","opponent","defense_snaps")
    snap_optional=("defense_pct","special_teams_snaps","special_teams_pct","player")
    snap25,_=parquet_rows(root/snap_asset["blobPath"],snap_required,snap_optional)
    for r in snap25:
        if r.get("team"): r["team"]=normalize_team(contract,r["team"])
        if r.get("opponent"): r["opponent"]=normalize_team(contract,r["opponent"])
    evgroups25=eu.aggregate_event_player_games(events25)
    exp25,exp25_audit=eu.build_expanded_rows(snap25,evgroups25,pfr_to_gsis=pfr_to_gsis,player_meta=player_meta,allowed_game_ids=allowed)
    exp25=[r for r in exp25 if int(r.get("season") or 0)==2025 and str(r.get("game_type") or "")=="REG"]
    if not exp25: raise SystemExit("FAIL no 2025 exposure universe")

    # Reconstruct realized 2025 weekly state; these rows are admitted only *after* each week is predicted.
    team25=xb.aggregate_team_game_outcomes(play25,exp25)
    old=tf.HOLDOUT_SEASON; tf.HOLDOUT_SEASON=2026
    try:
        fam25=tf.aggregate_team_family_opportunities(play25); pfc25=tf.aggregate_player_family_credits(events25)
    finally:
        tf.HOLDOUT_SEASON=old
    snap_tot25=xb.estimate_team_defensive_snaps(exp25)
    fammap25={(r["game_id"],r["defense_team"]):r for r in fam25}

    # Seed strictly-prior rolling state with 2016-2024 only.
    old=tf.HOLDOUT_SEASON; tf.HOLDOUT_SEASON=2026
    try:
        fam_hist_rows=tf.aggregate_team_family_opportunities(hist_plays); pfc_hist=tf.aggregate_player_family_credits(hist_events)
    finally:
        tf.HOLDOUT_SEASON=old
    fam_hist_map={(r["game_id"],r["defense_team"]):r for r in fam_hist_rows}

    off_hist:dict[str,list[dict[str,Any]]]=defaultdict(list); def_hist:dict[str,list[dict[str,Any]]]=defaultdict(list)
    off_fam:dict[str,list[dict[str,Any]]]=defaultdict(list); def_fam:dict[str,list[dict[str,Any]]]=defaultdict(list)
    league_fam={f:0.0 for f in fs.FAMILIES}; league_fam_total=0.0
    for g in sorted(hist_team_out,key=lambda r:(int(r["season"]),int(r["week"]),r["game_id"],r["defense_team"])):
        off_hist[g["offense_team"]].append(g); def_hist[g["defense_team"]].append(g)
    for g in sorted(fam_hist_rows,key=lambda r:(int(r["season"]),int(r["week"]),r["game_id"],r["defense_team"])):
        off_fam[g["offense_team"]].append(g); def_fam[g["defense_team"]].append(g); league_fam_total+=float(g.get("total_opportunity_plays") or 0.0)
        for f in fs.FAMILIES: league_fam[f]+=float(g.get(f"opp_{f}") or 0.0)

    player_snap_hist:dict[str,list[float]]=defaultdict(list); player_count_hist:dict[str,list[float]]=defaultdict(list)
    pos_snap_sum:dict[str,float]=defaultdict(float); pos_snap_n:dict[str,int]=defaultdict(int); pos_credits:dict[str,float]=defaultdict(float); pos_snaps:dict[str,float]=defaultdict(float)
    player_fam_hist:dict[str,dict[str,list[dict[str,float]]]]=defaultdict(lambda:defaultdict(list)); pos_fam_c:dict[tuple[str,str],float]=defaultdict(float); pos_fam_e:dict[tuple[str,str],float]=defaultdict(float)

    def update_player_state(rows:list[dict[str,Any]], fam_map:dict[tuple[str,str],dict[str,Any]], pfc:dict[tuple[str,str],dict[str,float]], team_tot:dict[tuple[str,str],float]) -> None:
        for r in sorted(rows,key=lambda x:(int(x.get("season") or 0),int(x.get("week") or 0),str(x.get("game_id") or ""),str(x.get("player_id") or ""))):
            if not bh.truthy(r.get("eligible_standard_rate_fit")): continue
            pid=str(r.get("player_id") or ""); team=str(r.get("team") or ""); gid=str(r.get("game_id") or "")
            if not pid or not team or not gid: continue
            ss=snap_share(r,team_tot,xb); snaps=xb.num(r.get("defense_snaps"))
            if ss is None or snaps is None or snaps<=0: continue
            pg=tf.canonical_position_group(r); credits=float(xb.as_int(r.get("combined_standard_def_scrimmage")))
            player_snap_hist[pid].append(float(ss)); player_count_hist[pid].append(credits); pos_snap_sum[pg]+=float(ss); pos_snap_n[pg]+=1; pos_credits[pg]+=credits; pos_snaps[pg]+=float(snaps)
            fg=fam_map.get((gid,team)); fc=pfc.get((gid,pid),{f:0.0 for f in fs.FAMILIES})
            if fg is None: continue
            for f in fs.FAMILIES:
                e=float(fg.get(f"opp_{f}") or 0.0)*float(ss); c=float(fc.get(f,0.0)); player_fam_hist[pid][f].append({"credits":c,"exposure":e}); pos_fam_c[(pg,f)]+=c; pos_fam_e[(pg,f)]+=e

    update_player_state(hist_exp,fam_hist_map,pfc_hist,hist_team_snaps)

    team25_by_week:dict[int,list[dict[str,Any]]]=defaultdict(list); fam25_by_week:dict[int,list[dict[str,Any]]]=defaultdict(list); exp25_by_week:dict[int,list[dict[str,Any]]]=defaultdict(list); games_by_week:dict[int,list[dict[str,Any]]]=defaultdict(list)
    for r in team25: team25_by_week[int(r["week"])].append(r)
    for r in fam25: fam25_by_week[int(r["week"])].append(r)
    for r in exp25: exp25_by_week[int(r.get("week") or 0)].append(r)
    for r in games: games_by_week[int(r.get("week") or 0)].append(r)

    blind:list[dict[str,Any]]=[]; week_audit=[]
    for week in sorted(games_by_week):
        target_games=games_by_week[week]
        # Emit every team prediction for the week before admitting week outcomes.
        team_features:dict[tuple[str,str],dict[str,Any]]={}; xto_pred:dict[tuple[str,str],float]={}; fam_pred:dict[tuple[str,str],dict[str,float]]={}
        league_share={f:(league_fam[f]/league_fam_total if league_fam_total>0 else 1.0/len(fs.FAMILIES)) for f in fs.FAMILIES}
        for gm in target_games:
            gid=str(gm["game_id"]); away=normalize_team(contract,gm.get("away_team")); home=normalize_team(contract,gm.get("home_team"))
            for offense,defense in ((away,home),(home,away)):
                tr=team_feature_row(gid,week,offense,defense,off_hist,def_hist,xb); team_features[(gid,defense)]=tr; xto_pred[(gid,defense)]=x_to_model.predict([float(tr[n]) for n in xb.TEAM_FEATURE_NAMES])
                off_share=family_share(off_fam[offense],tuple(fs.FAMILIES),fs.TEAM_WINDOW_GAMES); def_share=family_share(def_fam[defense],tuple(fs.FAMILIES),fs.TEAM_WINDOW_GAMES); raw={}
                for f in fs.FAMILIES: raw[f]=max(0.0,0.5*((off_share[f] if off_share else league_share[f])+(def_share[f] if def_share else league_share[f])))
                s=sum(raw.values()); fam_pred[(gid,defense)]={f:(raw[f]/s if s>0 else league_share[f]) for f in fs.FAMILIES}

        target_players=[r for r in exp25_by_week.get(week,[]) if bh.truthy(r.get("eligible_standard_rate_fit"))]
        emitted=0
        for r in target_players:
            gid=str(r.get("game_id") or ""); team=str(r.get("team") or ""); pid=str(r.get("player_id") or "")
            if (gid,team) not in team_features or not pid: continue
            pg=tf.canonical_position_group(r); h=player_snap_hist[pid]; rf=role_feature_row(pid,pg,h,pos_snap_sum,pos_snap_n,er); pred_ss=role_model.predict(rf)
            tfrow=team_features[(gid,team)]; last4=player_count_hist[pid][-4:]; pos_rate=pos_credits[pg]/pos_snaps[pg] if pos_snaps[pg]>0 else 0.08; pos_ss=pos_snap_sum[pg]/pos_snap_n[pg] if pos_snap_n[pg] else 0.35
            bench=fmean(last4) if last4 else pos_rate*float(tfrow["benchmark_defensive_snaps"])*pos_ss
            z={"game_id":gid,"season":2025,"week":week,"team":team,"opponent":str(r.get("opponent") or tfrow.get("offense_team") or ""),"player_id":pid,"display_name":str(r.get("display_name") or ""),"position":str(r.get("position") or ""),"position_group":pg,"participant_universe":"TARGET_GAME_DEFENSIVE_SNAP_GT0_CONDITIONAL_ONLY","prior_games":len(h),"predicted_xto":xto_pred[(gid,team)],"predicted_snap_share":pred_ss,"benchmark_last4_xtc":bench}
            total=0.0; shares=fam_pred[(gid,team)]
            for f in fs.FAMILIES:
                ph=player_fam_hist[pid][f][-fs.PLAYER_FAMILY_RATE_WINDOW_GAMES:]; pc=sum(x["credits"] for x in ph); pe=sum(x["exposure"] for x in ph); pr=pos_fam_c[(pg,f)]/pos_fam_e[(pg,f)] if pos_fam_e[(pg,f)]>0 else 0.15; rate=(pc+fs.FAMILY_ALPHA*pr)/(pe+fs.FAMILY_ALPHA) if pe+fs.FAMILY_ALPHA>0 else pr; po=xto_pred[(gid,team)]*shares[f]; contrib=po*pred_ss*rate
                z[f"pred_share_{f}"]=shares[f]; z[f"shrunk_rate_{f}"]=rate; z[f"pred_credit_{f}"]=contrib; total+=contrib
            z["predicted_xtc"]=max(0.0,total); blind.append(z); emitted+=1
        week_audit.append({"week":week,"games":len(target_games),"conditionalParticipantRows":len(target_players),"predictionsEmitted":emitted,"stateUpdatedAfterEmission":True})

        # Only now may this week's realized football/tackle state update later weeks.
        for g in team25_by_week.get(week,[]): off_hist[g["offense_team"]].append(g); def_hist[g["defense_team"]].append(g)
        for g in fam25_by_week.get(week,[]):
            off_fam[g["offense_team"]].append(g); def_fam[g["defense_team"]].append(g); league_fam_total+=float(g.get("total_opportunity_plays") or 0.0)
            for f in fs.FAMILIES: league_fam[f]+=float(g.get(f"opp_{f}") or 0.0)
        update_player_state(exp25_by_week.get(week,[]),fammap25,pfc25,snap_tot25)

    if not blind: raise SystemExit("FAIL blind ledger empty")
    if len({r["game_id"] for r in blind})<250: raise SystemExit(f"FAIL 2025 game coverage suspicious: {len({r['game_id'] for r in blind})}")
    bh.assert_blind_schema(blind[0].keys())

    outbase=out.parent; staging=outbase/("."+sid+".staging"); staging.mkdir(parents=True,exist_ok=False)
    try:
        fields=write_csv(staging/"OMEGA_2025_BLIND_PREDICTIONS.csv",blind); bh.assert_blind_schema(fields)
        psha=sha256_file(staging/"OMEGA_2025_BLIND_PREDICTIONS.csv"); (staging/"OMEGA_2025_BLIND_PREDICTIONS.sha256").write_text(psha+"\n",encoding="utf-8")
        models={"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"frozenSpecSha256":actual_sha,"fitSeasons":[2017,2018,2019,2020,2021,2022,2023,2024],"xDefensiveSnapsModel":x_snap_model.to_dict(),"xTOModel":x_to_model.to_dict(),"H012ExposureModel":role_model.to_dict(),"H008FamilyAlpha":fs.FAMILY_ALPHA}
        (staging/"OMEGA_2025_GLOBAL_MODELS.json").write_text(json.dumps(models,indent=2)+"\n",encoding="utf-8")
        audit={"schemaVersion":SCHEMA,"generatedAt":now(),"sourceSnapshotId":sid,"frozenSpecSha256":actual_sha,"predictionLedgerSha256":psha,"lineage":bh.LINEAGE,"integrity":{"globalFitSeasons":"2017-2024 REG only","sameWeekOutcomeAdmittedBeforePrediction":False,"futureWeekOutcomeAdmittedBeforePrediction":False,"targetTackleOutcomesSerialized":False,"targetSnapMagnitudeUsedAsFeature":False,"targetParticipantUniverseConditionalOnDefensiveSnapGT0":True,"marketFieldsRead":0,"oddsPapiRequests":0,"networkRequests":0,"scoreAttached":False,"sportsbookSettlementAssumed":False},"source":{"2025PbpAssetSha256":pbp_asset.get("sha256"),"2025SnapAssetSha256":snap_asset.get("sha256"),"2025PbpRowsReconstructed":len(play25),"2025TackleEventsReconstructedForWalkForwardUpdates":len(events25),"2025ExposureAudit":exp25_audit},"fit":{"teamRows2017To2024":len(team_fit),"exposureRows2017To2024":len(role_fit),"xDefensiveSnapsL2":fs.XDEFENSIVE_SNAPS_L2,"xTOL2":fs.XTO_L2,"exposureL2":fs.EXPOSURE_L2,"familyAlpha":fs.FAMILY_ALPHA},"blind":{"rows":len(blind),"games":len({r['game_id'] for r in blind}),"weeks":len({int(r['week']) for r in blind}),"weekAudit":week_audit,"columns":fields},"participantUniverseLimitation":spec.get("holdoutProtocol",{}).get("participantUniverseLimitation"),"nextGate":"Verify immutable blind ledger hash and coverage. Only then use a separate scoring command to attach 2025 actual counts exactly once. Do not alter the frozen spec or predictions."}
        (staging/"OMEGA_0.12_BLIND_AUDIT.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        md=f"""# OMEGA Tackle Model 0.12 — Blind 2025 Prediction Ledger Audit

Generated: {audit['generatedAt']}

**BLIND PREDICTIONS ONLY. 2025 SCORES ARE NOT ATTACHED. NO MARKET DATA.**

## Frozen contract

- Frozen spec SHA256: `{actual_sha}`
- Source snapshot: `{sid}`
- Global coefficient fit: **2017–2024 REG only**
- xDefensiveSnaps L2: **{fs.XDEFENSIVE_SNAPS_L2}**
- xTO L2: **{fs.XTO_L2}**
- H012 exposure L2: **{fs.EXPOSURE_L2}**
- H008 family alpha: **{fs.FAMILY_ALPHA}**

## Blind ledger

- Prediction rows: **{len(blind)}**
- Games represented: **{audit['blind']['games']}**
- Weeks represented: **{audit['blind']['weeks']}**
- Prediction ledger SHA256: `{psha}`
- Target T+A outcomes serialized: **NO**
- Target defensive-snap magnitude serialized: **NO**
- Score attached: **NO**

## Walk-forward integrity

- Entire target week predicted before that week's realized football/tackle state updates later weeks: **YES**
- Same-week outcomes admitted before prediction: **NO**
- Future-week outcomes admitted before prediction: **NO**
- Market fields read: **0**
- OddsPapi requests: **0**
- Network requests: **0**

## Participant-universe limitation

The holdout is conditional on player-games with resolved target-game defensive participation (`defense_snaps > 0`). That boolean is used only to define the historical evaluation universe. The target game's snap magnitude and tackle count do **not** enter the prediction. This remains insufficient for live VERIFIED prop Trust until a pregame active/inactive/depth-chart layer exists.

## Next gate

Verify this immutable ledger and its hash. Then score it exactly once in a separate phase. **Do not change the model, benchmark, rows, thresholds, or subgroup definitions after seeing 2025 outcomes.**
"""
        (staging/"OMEGA_0.12_BLIND_AUDIT.md").write_text(md,encoding="utf-8")
        files=[]
        for p in sorted(staging.iterdir()):
            if p.is_file(): files.append({"filename":p.name,"sha256":sha256_file(p),"bytes":p.stat().st_size})
        (staging/"OMEGA_OUTPUT_MANIFEST.json").write_text(json.dumps({"schemaVersion":SCHEMA,"sourceSnapshotId":sid,"createdAt":now(),"files":files},indent=2)+"\n",encoding="utf-8")
        os.replace(staging,out); (root/"data/models/nfl/CURRENT_OMEGA_TACKLE_BLIND_2025").write_text(sid+"\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(staging,ignore_errors=True); raise

    print("OMEGA 0.12 — BLIND 2025 LEDGER")
    print(f"PASS frozen spec SHA: {actual_sha}")
    print(f"PASS blind predictions: {len(blind)} rows · {len({r['game_id'] for r in blind})} games")
    print(f"PASS prediction ledger SHA256: {psha}")
    print("PASS score attached NO · market fields 0 · OddsPapi 0 · network 0")
    print(f"REPORT: {out/'OMEGA_0.12_BLIND_AUDIT.md'}")
    return 0

if __name__ == "__main__": raise SystemExit(main())

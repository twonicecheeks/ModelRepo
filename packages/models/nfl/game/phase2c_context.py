"""NFL Phase 2C pregame QB/roster context primitives.

Research-only. Every feature for game G is constructed from information with a
strictly earlier game key plus the target week's roster snapshot. Current-game PBP,
snap counts and outcomes are never admitted to that game's feature row.

Historical primary-QB identity is an OBSERVED postgame fact used only after lagging
into later games. It is not treated as a verified pregame starter source. When the
prior primary QB is not on the target week's active roster, Phase 2C resolves a
replacement only if exactly one active QB exists; otherwise QB skill is left missing
and an unresolved-change flag is surfaced.
"""
from __future__ import annotations

from collections import defaultdict
from math import log1p
from statistics import fmean
from typing import Any, Iterable

VERSION = "0.3.0"
LINEAGE = "nfl-game-v0.3.0-qb-roster-transition-research-2026-09-10"
HOLDOUT_SEASON = 2025

QB_METRICS = ("epa", "cpoe", "sack_rate", "explosive_pass_rate", "int_rate")
QB_HORIZONS = ("prior_season", "last4", "last8")
OL_POSITIONS = frozenset({"C", "G", "OG", "LG", "RG", "T", "OT", "LT", "RT", "OL"})
SKILL_POSITIONS = frozenset({"WR", "RB", "FB", "TE"})
ACTIVE_STATUS = "ACT"


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _flag(v: Any) -> bool:
    return _num(v) == 1.0


def _game_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return int(row["season"]), int(row["week"]), str(row["game_id"])


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    vals = [_num(r.get(field)) for r in rows]
    good = [x for x in vals if x is not None]
    return fmean(good) if good else None


def extract_observed_qb_game_metrics(pbp_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate QB dropbacks and identify the observed primary QB per team-game.

    The result is *postgame history*. Callers must lag it before constructing a
    pregame row. `passer_player_id` is required for an attributed dropback; rows
    without it are ignored rather than joined by display name.
    """
    by: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    meta: dict[tuple[str, str, str], tuple[int, int, str]] = {}
    for raw in pbp_rows:
        if not _flag(raw.get("qb_dropback")):
            continue
        if _flag(raw.get("no_play")) or _flag(raw.get("qb_kneel")):
            continue
        gid = _clean(raw.get("game_id"))
        team = _clean(raw.get("posteam")).upper()
        qid = _clean(raw.get("passer_player_id"))
        if not gid or not team or not qid:
            continue
        season = int(float(raw["season"]))
        week = int(float(raw["week"]))
        key = (gid, team, qid)
        by[key].append(dict(raw))
        meta[key] = (season, week, _clean(raw.get("passer_player_name")))

    per_qb: list[dict[str, Any]] = []
    for (gid, team, qid), plays in by.items():
        season, week, name = meta[(gid, team, qid)]
        cpoes = [_num(p.get("cpoe")) for p in plays]
        cpoes = [x for x in cpoes if x is not None]
        epa = [_num(p.get("qb_epa")) for p in plays]
        epa = [(_num(p.get("epa")) if q is None else q) for p, q in zip(plays, epa)]
        epa = [x for x in epa if x is not None]
        n = len(plays)
        row = {
            "game_id": gid, "season": season, "week": week, "team": team,
            "qb_gsis_id": qid, "qb_name": name, "dropbacks": n,
            "epa": fmean(epa) if epa else None,
            "cpoe": fmean(cpoes) if cpoes else None,
            "sack_rate": sum(_flag(p.get("sack")) for p in plays) / n if n else None,
            "explosive_pass_rate": sum((_num(p.get("yards_gained")) or 0.0) >= 20.0 for p in plays) / n if n else None,
            "int_rate": sum(_flag(p.get("interception")) for p in plays) / n if n else None,
        }
        per_qb.append(row)

    # Deterministic observed primary: most attributed dropbacks; ties break by ID.
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in per_qb:
        grouped[(r["game_id"], r["team"])].append(r)
    out: list[dict[str, Any]] = []
    for key, candidates in grouped.items():
        candidates.sort(key=lambda r: (-int(r["dropbacks"]), str(r["qb_gsis_id"])))
        primary = candidates[0]["qb_gsis_id"]
        total = sum(int(r["dropbacks"]) for r in candidates)
        for r in candidates:
            q = dict(r)
            q["observed_primary"] = 1 if q["qb_gsis_id"] == primary else 0
            q["team_attributed_dropbacks"] = total
            q["primary_dropback_share"] = (q["dropbacks"] / total) if total else None
            out.append(q)
    out.sort(key=lambda r: (r["season"], r["week"], r["game_id"], r["team"], -r["observed_primary"], r["qb_gsis_id"]))
    return out


def _active_roster_index(roster_rows: Iterable[dict[str, Any]]) -> tuple[dict[tuple[int,int,str], set[str]], dict[tuple[int,int,str], set[str]], dict[tuple[int,int,str], list[str]]]:
    gsis: dict[tuple[int,int,str], set[str]] = defaultdict(set)
    pfr: dict[tuple[int,int,str], set[str]] = defaultdict(set)
    active_qbs: dict[tuple[int,int,str], list[str]] = defaultdict(list)
    for r in roster_rows:
        try:
            key = (int(float(r["season"])), int(float(r["week"])), _clean(r.get("team")).upper())
        except Exception:
            continue
        if _clean(r.get("game_type")).upper() not in {"", "REG"}:
            continue
        if _clean(r.get("status")).upper() != ACTIVE_STATUS:
            continue
        # Preserve that the roster-week exists even when a particular identifier is missing.
        gsis.setdefault(key, set()); pfr.setdefault(key, set()); active_qbs.setdefault(key, [])
        gid = _clean(r.get("gsis_id")); pid = _clean(r.get("pfr_id"))
        if gid: gsis[key].add(gid)
        if pid: pfr[key].add(pid)
        pos = _clean(r.get("position")).upper()
        dcp = _clean(r.get("depth_chart_position")).upper()
        if gid and (pos == "QB" or dcp == "QB"):
            active_qbs[key].append(gid)
    for key in list(active_qbs):
        active_qbs[key] = sorted(set(active_qbs[key]))
    return gsis, pfr, active_qbs


def _qb_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"games": len(rows), "dropbacks": sum(int(r.get("dropbacks") or 0) for r in rows)}
    for metric in QB_METRICS:
        # Weight rate/mean metrics by attributed QB dropbacks so a 3-dropback relief
        # appearance cannot carry the same authority as a full start.
        pairs = [(_num(r.get(metric)), int(r.get("dropbacks") or 0)) for r in rows]
        pairs = [(x,n) for x,n in pairs if x is not None and n > 0]
        den = sum(n for _,n in pairs)
        out[metric] = (sum(x*n for x,n in pairs)/den) if den else None
    return out


def _strict_prior_qb_rows(qb_rows_by_id: dict[str, list[dict[str, Any]]], qid: str, target: tuple[int,int,str]) -> list[dict[str, Any]]:
    return [r for r in qb_rows_by_id.get(qid, []) if _game_key(r) < target]


def build_qb_pregame_context(
    games: Iterable[dict[str, Any]],
    qb_game_rows: Iterable[dict[str, Any]],
    roster_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build lagged QB continuity/state context for development games."""
    games_sorted = sorted((dict(g) for g in games), key=_game_key)
    primary_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    qb_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in qb_game_rows:
        rr = dict(r)
        rr["team"] = _clean(rr.get("team")).upper()
        if int(rr.get("observed_primary") or 0) == 1:
            primary_by_team[rr["team"]].append(rr)
        qb_by_id[_clean(rr.get("qb_gsis_id"))].append(rr)
    for d in (primary_by_team, qb_by_id):
        for rows in d.values(): rows.sort(key=_game_key)
    active_gsis, _, active_qbs = _active_roster_index(roster_rows)

    out=[]
    for g in games_sorted:
        season, week, gid = _game_key(g)
        if season >= HOLDOUT_SEASON:
            continue
        row={"game_id":gid,"season":season,"week":week,"home_team":_clean(g["home_team"]).upper(),"away_team":_clean(g["away_team"]).upper()}
        for side in ("home","away"):
            team=row[f"{side}_team"]; target=(season,week,gid)
            prior_primary=[r for r in primary_by_team.get(team,[]) if _game_key(r) < target]
            prev=prior_primary[-1] if prior_primary else None
            rkey=(season,week,team)
            aq=active_qbs.get(rkey,[]); aset=active_gsis.get(rkey,set())
            prev_id=_clean(prev.get("qb_gsis_id")) if prev else ""
            prev_active = (1.0 if prev_id in aset else 0.0) if prev_id and rkey in active_gsis else None
            projected=""; resolution="UNRESOLVED"
            if prev_id and prev_active == 1.0:
                projected=prev_id; resolution="INCUMBENT_ACTIVE_PROXY"
            elif len(aq)==1:
                projected=aq[0]; resolution="ROSTER_SINGLETON_CHANGE_PROXY"
            elif not prev_id:
                resolution="NO_PRIOR_PRIMARY"
            elif rkey not in active_gsis:
                resolution="ROSTER_WEEK_MISSING"
            else:
                resolution="MULTI_QB_CHANGE_UNRESOLVED"
            continuity = (1.0 if projected==prev_id else 0.0) if projected and prev_id else None
            change = (1.0-continuity) if continuity is not None else (1.0 if prev_id and prev_active==0.0 else None)
            unresolved = 1.0 if not projected else 0.0
            row[f"{side}_prev_primary_qb_gsis_id"] = prev_id
            row[f"{side}_projected_qb_gsis_id"] = projected
            row[f"{side}_qb_resolution"] = resolution
            row[f"{side}_qb_continuity"] = continuity
            row[f"{side}_qb_change_proxy"] = change
            row[f"{side}_qb_unresolved"] = unresolved
            row[f"{side}_active_qb_count"] = float(len(aq)) if rkey in active_qbs else None
            histories = _strict_prior_qb_rows(qb_by_id, projected, target) if projected else []
            for h in QB_HORIZONS:
                if h=="prior_season": use=[r for r in histories if int(r["season"])==season-1]
                elif h=="last4": use=histories[-4:]
                else: use=histories[-8:]
                s=_qb_summary(use)
                row[f"{side}_{h}_qb_games"] = float(s["games"])
                row[f"{side}_{h}_qb_dropbacks"] = float(s["dropbacks"])
                for metric in QB_METRICS:
                    row[f"{side}_{h}_qb_{metric}"] = s[metric]
            row[f"{side}_week1_qb_continuity"] = continuity if week==1 else 0.0
            row[f"{side}_week1_qb_change_proxy"] = change if week==1 else 0.0
        out.append(row)
    return out


def _weighted_return(rows: list[dict[str, Any]], active_pfr: set[str], snap_field: str, positions: set[str] | None = None) -> float | None:
    selected=[]
    for r in rows:
        n=_num(r.get(snap_field))
        if n is None or n <= 0: continue
        pos=_clean(r.get("position")).upper()
        if positions is not None and pos not in positions: continue
        pid=_clean(r.get("pfr_player_id"))
        selected.append((pid,n))
    den=sum(n for _,n in selected)
    if den<=0:return None
    return sum(n for pid,n in selected if pid and pid in active_pfr)/den


def build_roster_continuity_context(
    games: Iterable[dict[str, Any]],
    snap_rows: Iterable[dict[str, Any]],
    roster_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build prior-game snap-weighted continuity features.

    The target game's own snap counts are never read into its feature row. Week 1
    naturally uses the prior season's last observed game for that franchise.
    """
    games_sorted=sorted((dict(g) for g in games),key=_game_key)
    game_order={g["game_id"]:_game_key(g) for g in games_sorted}
    snaps_by_team_game: dict[tuple[str,str],list[dict[str,Any]]] = defaultdict(list)
    snap_game_meta: dict[tuple[str,str],tuple[int,int,str]]={}
    for raw in snap_rows:
        gid=_clean(raw.get("game_id")); team=_clean(raw.get("team")).upper()
        if not gid or not team or gid not in game_order: continue
        snaps_by_team_game[(team,gid)].append(dict(raw)); snap_game_meta[(team,gid)]=game_order[gid]
    snap_games_by_team: dict[str,list[tuple[tuple[int,int,str],str]]] = defaultdict(list)
    for team,gid in snaps_by_team_game:
        snap_games_by_team[team].append((snap_game_meta[(team,gid)],gid))
    for v in snap_games_by_team.values():v.sort()
    active_gsis,active_pfr,_=_active_roster_index(roster_rows)
    # active roster set history for an unweighted churn diagnostic
    roster_keys_by_team: dict[str,list[tuple[tuple[int,int,str],set[str]]]]=defaultdict(list)
    for (season,week,team),ids in active_gsis.items():
        roster_keys_by_team[team].append(((season,week,""),set(ids)))
    for v in roster_keys_by_team.values():v.sort(key=lambda x:x[0])

    out=[]
    for g in games_sorted:
        season,week,gid=_game_key(g)
        if season>=HOLDOUT_SEASON:continue
        row={"game_id":gid,"season":season,"week":week,"home_team":_clean(g["home_team"]).upper(),"away_team":_clean(g["away_team"]).upper()}
        for side in ("home","away"):
            team=row[f"{side}_team"]; target=(season,week,gid); rkey=(season,week,team)
            prior=[x for x in snap_games_by_team.get(team,[]) if x[0] < target]
            prior_gid=prior[-1][1] if prior else ""
            prev_rows=snaps_by_team_game.get((team,prior_gid),[])
            aset=active_pfr.get(rkey,set())
            roster_known=rkey in active_pfr
            row[f"{side}_prior_snap_game_id"] = prior_gid
            row[f"{side}_offense_snap_continuity"] = _weighted_return(prev_rows,aset,"offense_snaps") if roster_known else None
            row[f"{side}_ol_snap_continuity"] = _weighted_return(prev_rows,aset,"offense_snaps",set(OL_POSITIONS)) if roster_known else None
            row[f"{side}_skill_snap_continuity"] = _weighted_return(prev_rows,aset,"offense_snaps",set(SKILL_POSITIONS)) if roster_known else None
            row[f"{side}_defense_snap_continuity"] = _weighted_return(prev_rows,aset,"defense_snaps") if roster_known else None
            prior_rosters=[x for x in roster_keys_by_team.get(team,[]) if x[0] < (season,week,"")]
            prev_active=prior_rosters[-1][1] if prior_rosters else set()
            curr_active=active_gsis.get(rkey,set())
            row[f"{side}_active_roster_return_rate"] = (len(prev_active & curr_active)/len(prev_active)) if prev_active and rkey in active_gsis else None
            for stem in ("offense_snap_continuity","ol_snap_continuity","skill_snap_continuity","defense_snap_continuity","active_roster_return_rate"):
                row[f"{side}_week1_{stem}"] = row[f"{side}_{stem}"] if week==1 else 0.0
        out.append(row)
    return out


def merge_context_rows(base_rows: Iterable[dict[str, Any]], qb_rows: Iterable[dict[str, Any]], roster_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    qb={r["game_id"]:r for r in qb_rows}; rc={r["game_id"]:r for r in roster_rows}
    out=[]
    for b in base_rows:
        if int(b["season"])>=HOLDOUT_SEASON:continue
        gid=b["game_id"]; row=dict(b)
        for src in (qb.get(gid,{}),rc.get(gid,{})):
            for k,v in src.items():
                if k in {"game_id","season","week","home_team","away_team"}:continue
                row[k]=v
        out.append(row)
    out.sort(key=_game_key)
    return out


def log_dropbacks(v: Any) -> float | None:
    x=_num(v)
    return None if x is None else log1p(max(0.0,x))

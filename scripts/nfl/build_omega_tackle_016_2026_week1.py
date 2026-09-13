#!/usr/bin/env python3
"""Build immutable independent OMEGA-I 2026 Week-1 probability ledger.

Frozen coefficients/architecture are not retuned. 2025 realized football state is
used only as strictly-prior history for 2026. No 2026 outcomes and no market data
are read. The target-player universe comes from the captured pregame roster state,
not target-game realized defensive snaps.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
from statistics import fmean
from collections import defaultdict
import argparse,csv,hashlib,json,math,os,shutil,sys
from typing import Any

SEASON=2026
CORE={'DB','DL','LB'}

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def rcsv(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def wcsv(p,rows):
 rows=list(rows); fields=[]
 for r in rows:
  for k in r:
   if k not in fields:fields.append(k)
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows([{k:'' if r.get(k) is None else r.get(k) for k in fields} for r in rows])
 return fields
def pqrows(path,required,optional=()):
 import pyarrow.parquet as pq
 pf=pq.ParquetFile(path); names=set(pf.schema_arrow.names); miss=[x for x in required if x not in names]
 if miss:raise ValueError(f'{path.name} missing {miss}')
 cols=list(required)+[x for x in optional if x in names and x not in required]
 return pf.read(columns=cols).to_pylist(),names
def num(v,d=0.0):
 try:return d if v in (None,'') else float(v)
 except:return d
def truthy(v):return str(v).strip().lower() in {'1','true','yes','y','t'}
def normteam(contract,v):
 s=str(v or '').strip();return contract.normalize_team_abbr(s) if s else ''
def snap_share(r,tot,xb):
 p=xb.normalize_pct(r.get('defense_pct'))
 if p is not None:return p
 s=xb.num(r.get('defense_snaps')); t=tot.get((str(r.get('game_id') or ''),str(r.get('team') or '')))
 if s is None or t is None or t<=0:return None
 return max(0,min(1,float(s)/float(t)))
def role_feature(pg,h,pos_sum,pos_n,er):
 prior=pos_sum[pg]/pos_n[pg] if pos_n[pg] else .35; last1=h[-1] if h else prior; l2=h[-2:];l4=h[-4:];l8=h[-8:]
 m2=er.mean_or(l2,prior);m4=er.mean_or(l4,prior);m8=er.mean_or(l8,prior)
 return {'position_prior_snap_share':prior,'prior_games_cap8':min(8,len(h))/8,'prior_games_log':math.log1p(len(h)),'last1_snap_share':last1,'last2_snap_share_mean':m2,'last4_snap_share_mean':m4,'last8_snap_share_mean':m8,'last4_snap_share_std':er.std_or_zero(l4),'last4_snap_share_min':min(l4) if l4 else prior,'last4_snap_share_max':max(l4) if l4 else prior,'last1_minus_last4':last1-m4,'last2_minus_last8':m2-m8,'position_DB':1.0 if pg=='DB' else 0.0,'position_LB':1.0 if pg=='LB' else 0.0,'position_DL':1.0 if pg=='DL' else 0.0,'position_OTHER':1.0 if pg not in CORE else 0.0,'cold_start':1.0 if not h else 0.0,'one_prior_game':1.0 if len(h)==1 else 0.0}
def team_feature(game_id,week,offense,defense,off_hist,def_hist,xb):
 oh=xb._summary(off_hist[offense]);dh=xb._summary(def_hist[defense])
 if not oh or not dh:raise ValueError(f'missing team history {offense}@{defense}')
 return {'game_id':game_id,'season':SEASON,'week':week,'offense_team':offense,'defense_team':defense,'off_def_snaps_mean8':oh['def_snaps'],'def_def_snaps_mean8':dh['def_snaps'],'off_opportunity_plays_mean8':oh['opportunity_plays'],'def_opportunity_plays_mean8':dh['opportunity_plays'],'off_opportunity_rate8':oh['opportunity_rate'],'def_opportunity_rate8':dh['opportunity_rate'],'off_credits_per_opportunity8':oh['credits_per_opportunity'],'def_credits_per_opportunity8':dh['credits_per_opportunity'],'off_rush_share8':oh['rush_share'],'off_complete_pass_share8':oh['complete_pass_share'],'off_scramble_share8':oh['scramble_share'],'off_sack_share8':oh['sack_share'],'off_games_available8':oh['games']/xb.TEAM_WINDOW,'def_games_available8':dh['games']/xb.TEAM_WINDOW,'benchmark_defensive_snaps':.5*(oh['def_snaps']+dh['def_snaps']),'benchmark_opportunity_plays':.5*(oh['opportunity_plays']+dh['opportunity_plays'])}
def famshare(hist,fams,window):
 h=hist[-window:]; total=sum(float(r.get('total_opportunity_plays') or 0) for r in h)
 if total<=0:return None
 return {f:sum(float(r.get('opp_'+f) or 0) for r in h)/total for f in fams}
def player_meta(root,asset):
 rows,_=pqrows(root/asset['blobPath'],('gsis_id','display_name','position','position_group'),('pfr_id',));bg={};p2g={}
 for r in rows:
  g=str(r.get('gsis_id') or '').strip();p=str(r.get('pfr_id') or '').strip()
  if g:bg[g]=r
  if g and p:p2g[p]=g
 return bg,p2g
def snap_asset_2025(root,sid):
 base=root/'data/raw/nfl/nflverse/phase2f_holdout/snapshots'; cand=[]
 for mp in base.glob('*/SOURCE_MANIFEST.json'):
  try:
   d=json.loads(mp.read_text());a=d.get('asset',{});p=root/a.get('blobPath','')
   if d.get('sourcePhase1SnapshotId')==sid and int(d.get('season') or 0)==2025 and p.exists() and sha(p)==a.get('sha256'):cand.append((str(d.get('createdAt') or ''),a))
  except:pass
 if not cand:raise SystemExit('FAIL verified 2025 snap asset missing')
 return sorted(cand)[-1][1]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');a=ap.parse_args();root=Path(a.root).resolve()
 sys.path[:0]=[str(root/'packages/models/nfl/omega'),str(root/'packages/providers/nflverse/src')]
 import frozen_spec as fs,tackle_events as te,exposure_universe as eu,xto_xtc_baseline as xb,exposure_role_challenger as er,tackle_opportunity_footprint as tf,tackle_count_distribution as dist,contract
 # Frozen probability spec and exact 0.12 global-model lineage.
 pptr=root/'data/models/nfl/CURRENT_OMEGA_TACKLE_PROBABILITY_FROZEN'; bptr=root/'data/models/nfl/CURRENT_OMEGA_TACKLE_BLIND_2025'; sptr=root/'data/raw/nfl/omega/CURRENT_OMEGA_TACKLE_2026_PREGAME_SOURCE'
 for p in (pptr,bptr,sptr):
  if not p.exists():raise SystemExit(f'FAIL prerequisite missing: {p}')
 sid=pptr.read_text().strip(); probdir=root/'data/models/nfl/omega_tackle_016_probability_frozen'/sid; pspecp=probdir/'OMEGA_0.16_PROBABILITY_FROZEN_SPEC.json'; pspec=json.loads(pspecp.read_text())
 if pspec.get('distributionFamily')!='NB_ROLE':raise SystemExit('FAIL frozen probability family drift')
 params=pspec['distributionParamsFitThrough2024']
 bdir=root/'data/models/nfl/omega_tackle_012_blind_2025'/sid; gm=json.loads((bdir/'OMEGA_2025_GLOBAL_MODELS.json').read_text())
 source_id=sptr.read_text().strip(); src=root/'data/raw/nfl/omega/prospective_2026_pregame'/source_id; sm=json.loads((src/'PREGAME_SOURCE_MANIFEST.json').read_text())
 if int(sm.get('season',0))!=2026:raise SystemExit('FAIL pregame source not 2026')
 week=int(sm['targetWeek'])
 if week!=1:raise SystemExit('FAIL OMEGA 0.16 initial prospective builder is intentionally Week 1 only; later weeks require a separate prior-week 2026 state-admission gate')
 state=rcsv(src/'normalized_pregame_state.csv'); games=rcsv(src/'target_games.csv')
 # Historical 2016-2024 frozen artifacts; coefficients remain the exact 0.12 fit through 2024.
 foundation=root/'data/normalized/nfl/omega_tackle'/sid; exdir=root/'data/normalized/nfl/omega_tackle_exposure'/sid; phase1=root/'data/normalized/nfl/phase1'/sid
 histp=rcsv(foundation/'omega_tackle_play_opportunities.csv'); histe=rcsv(foundation/'omega_tackle_credit_events.csv'); histex=rcsv(exdir/'omega_tackle_exposure_player_games.csv')
 teamout=xb.aggregate_team_game_outcomes(histp,histex); teamrows=xb.build_team_pregame_rows(teamout); fit=[r for r in teamrows if 2017<=int(r['season'])<=2024]
 xto=xb.fit_ridge(fit,target_key='actual_opportunity_plays',l2=fs.XTO_L2); ts=xb.estimate_team_defensive_snaps(histex); rr=er.build_exposure_pregame_rows(histex,ts); role=er.fit_ridge([r for r in rr if 2017<=int(r['season'])<=2024],fs.EXPOSURE_L2)
 # Exact coefficient drift check against blind-holdout global models.
 canon=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'))
 if canon(xto.to_dict())!=canon(gm['xTOModel']):raise SystemExit('FAIL xTO coefficient drift vs 0.12 frozen blind model')
 if canon(role.to_dict())!=canon(gm['H012ExposureModel']):raise SystemExit('FAIL H012 coefficient drift vs 0.12 frozen blind model')
 # Reconstruct full 2025 realized state. This is history admission only, never fitting/tuning.
 manifest=json.loads((root/'data/raw/nfl/nflverse/snapshots'/sid/'SOURCE_MANIFEST.json').read_text());assets={(x['source'],x.get('season')):x for x in manifest['assets']};pm,p2g=player_meta(root,assets[('players',None)])
 games25=[r for r in rcsv(phase1/'game_identity.csv') if int(r.get('season') or 0)==2025 and str(r.get('game_type') or '')=='REG']; allowed={r['game_id'] for r in games25}
 pbpa=assets[('play_by_play',2025)]; req=('game_id','play_id','season','week','posteam','defteam');opt=('play_type','no_play','play_deleted','special_teams_play','qtr','down','ydstogo','yardline_100','game_seconds_remaining','score_differential','score_differential_post','yards_gained','air_yards','yards_after_catch','run_location','run_gap','pass_location','pass_length','shotgun','no_huddle','qb_scramble','sack','complete_pass','interception','fumble','fumble_lost','rush_attempt','rush','pass_attempt','qb_dropback')+tuple(te.TACKLE_ID_COLUMNS)+tuple(te.TACKLE_NAME_COLUMNS)+tuple(te.TACKLE_TEAM_COLUMNS)
 raw,_=pqrows(root/pbpa['blobPath'],req,opt);p25=[];e25=[]
 for r in raw:
  if str(r.get('game_id') or '') not in allowed:continue
  if r.get('posteam'):r['posteam']=normteam(contract,r['posteam'])
  if r.get('defteam'):r['defteam']=normteam(contract,r['defteam'])
  ev=te.extract_credit_events(r);e25.extend(ev);p25.append(te.build_play_opportunity_row(r,ev))
 sa=snap_asset_2025(root,sid);sr,_=pqrows(root/sa['blobPath'],('game_id','season','game_type','week','pfr_player_id','position','team','opponent','defense_snaps'),('defense_pct','special_teams_snaps','special_teams_pct','player'))
 for r in sr:
  if r.get('team'):r['team']=normteam(contract,r['team'])
  if r.get('opponent'):r['opponent']=normteam(contract,r['opponent'])
 ex25,_=eu.build_expanded_rows(sr,eu.aggregate_event_player_games(e25),pfr_to_gsis=p2g,player_meta=pm,allowed_game_ids=allowed);ex25=[r for r in ex25 if int(r.get('season') or 0)==2025 and str(r.get('game_type') or '')=='REG']
 to25=xb.aggregate_team_game_outcomes(p25,ex25); old=tf.HOLDOUT_SEASON;tf.HOLDOUT_SEASON=2026
 try:f25=tf.aggregate_team_family_opportunities(p25);pfc25=tf.aggregate_player_family_credits(e25);fh=tf.aggregate_team_family_opportunities(histp);pfch=tf.aggregate_player_family_credits(histe)
 finally:tf.HOLDOUT_SEASON=old
 st25=xb.estimate_team_defensive_snaps(ex25); fhm={(r['game_id'],r['defense_team']):r for r in fh};f25m={(r['game_id'],r['defense_team']):r for r in f25}
 # rolling state through end of 2025
 offh=defaultdict(list);defh=defaultdict(list);offf=defaultdict(list);deff=defaultdict(list);lf={f:0.0 for f in fs.FAMILIES};lft=0.0
 for g in sorted(teamout+to25,key=lambda r:(int(r['season']),int(r['week']),r['game_id'],r['defense_team'])):offh[g['offense_team']].append(g);defh[g['defense_team']].append(g)
 for g in sorted(fh+f25,key=lambda r:(int(r['season']),int(r['week']),r['game_id'],r['defense_team'])):
  offf[g['offense_team']].append(g);deff[g['defense_team']].append(g);lft+=float(g.get('total_opportunity_plays') or 0)
  for f in fs.FAMILIES:lf[f]+=float(g.get('opp_'+f) or 0)
 psh=defaultdict(list);psum=defaultdict(float);pn=defaultdict(int);pfh=defaultdict(lambda:defaultdict(list));pfc=defaultdict(float);pfe=defaultdict(float)
 def upd(rows,fmap,pc,tot):
  for r in sorted(rows,key=lambda x:(int(x.get('season') or 0),int(x.get('week') or 0),str(x.get('game_id') or ''),str(x.get('player_id') or ''))):
   if not truthy(r.get('eligible_standard_rate_fit')):continue
   pid=str(r.get('player_id') or '');team=str(r.get('team') or '');gid=str(r.get('game_id') or '');ss=snap_share(r,tot,xb);sn=xb.num(r.get('defense_snaps'))
   if not pid or ss is None or sn is None or sn<=0:continue
   pg=tf.canonical_position_group(r);psh[pid].append(float(ss));psum[pg]+=float(ss);pn[pg]+=1;fg=fmap.get((gid,team));fc=pc.get((gid,pid),{f:0.0 for f in fs.FAMILIES})
   if fg is None:continue
   for f in fs.FAMILIES:
    ex=float(fg.get('opp_'+f) or 0)*float(ss);cr=float(fc.get(f,0));pfh[pid][f].append({'credits':cr,'exposure':ex});pfc[(pg,f)]+=cr;pfe[(pg,f)]+=ex
 upd(histex,fhm,pfch,ts);upd(ex25,f25m,pfc25,st25)
 # Team predictions for captured future Week-1 games.
 tfeat={};xpred={};fpred={};league={f:(lf[f]/lft if lft>0 else 1/len(fs.FAMILIES)) for f in fs.FAMILIES}
 for g in games:
  gid=g['game_id'];away=normteam(contract,g['away_team']);home=normteam(contract,g['home_team'])
  for off,de in ((away,home),(home,away)):
   tr=team_feature(gid,week,off,de,offh,defh,xb);tfeat[(gid,de)]=tr;xpred[(gid,de)]=xto.predict([float(tr[n]) for n in xb.TEAM_FEATURE_NAMES]);off_mix=famshare(offf[off],tuple(fs.FAMILIES),fs.TEAM_WINDOW_GAMES);def_mix=famshare(deff[de],tuple(fs.FAMILIES),fs.TEAM_WINDOW_GAMES);raws={f:max(0,.5*((off_mix[f] if off_mix else league[f])+(def_mix[f] if def_mix else league[f]))) for f in fs.FAMILIES};s=sum(raws.values());fpred[(gid,de)]={f:(raws[f]/s if s else league[f]) for f in fs.FAMILIES}
 outrows=[]
 for r in state:
  if r.get('research_ready')!='TRUE' or r.get('roster_status')!='ACTIVE_ROSTER' or r.get('game_status')=='OUT':continue
  gid=r['game_id'];team=normteam(contract,r['team']);pid=r['player_id'];pg=r['position_group']
  if pg not in CORE or (gid,team) not in tfeat:continue
  rf=role_feature(pg,psh[pid],psum,pn,er);ss=max(0,min(1,role.predict(rf)));shares=fpred[(gid,team)];total=0.0;z={'captured_at':sm['capturedAt'],'pregame_source_snapshot':source_id,'game_id':gid,'season':2026,'week':week,'kickoff_utc':r.get('kickoff_utc'),'team':team,'opponent':r.get('opponent'),'player_id':pid,'player_name':r.get('player_name'),'position':r.get('position'),'position_group':pg,'prior_games':len(psh[pid]),'predicted_xto':xpred[(gid,team)],'predicted_snap_share':ss,'availability_authority':r.get('availability_authority'),'game_status':r.get('game_status'),'injury_designation':r.get('injury_designation'),'listed_starter':r.get('listed_starter'),'depth_role':r.get('depth_role'),'verified_ready':'FALSE','verified_block_reason':r.get('verified_block_reason') or 'NO_AUTHORITATIVE_GAME_DAY_INACTIVE_SOURCE'}
  for f in fs.FAMILIES:
   h=pfh[pid][f][-fs.PLAYER_FAMILY_RATE_WINDOW_GAMES:];pc=sum(x['credits'] for x in h);pe=sum(x['exposure'] for x in h);pr=pfc[(pg,f)]/pfe[(pg,f)] if pfe[(pg,f)]>0 else .15;rate=(pc+fs.FAMILY_ALPHA*pr)/(pe+fs.FAMILY_ALPHA) if pe+fs.FAMILY_ALPHA>0 else pr;con=xpred[(gid,team)]*shares[f]*ss*rate;z['pred_share_'+f]=shares[f];z['shrunk_rate_'+f]=rate;z['pred_credit_'+f]=con;total+=con
  z['predicted_xtc']=max(0,total);tier=dist.role_tier(ss);z['distribution_family']='NB_ROLE';z['distribution_role_tier']=tier;z['distribution_size']=params.get('size_'+tier,params['globalSize'])
  for line in [x+.5 for x in range(15)]:
   po=dist.over_probability(line,z['predicted_xtc'],'NB_ROLE',params,tier);pu=1-po;tag=str(line).replace('.','_');z['p_over_'+tag]=po;z['p_under_'+tag]=pu;z['fair_over_'+tag]=dist.fair_american(po);z['fair_under_'+tag]=dist.fair_american(pu)
  outrows.append(z)
 if not outrows:raise SystemExit('FAIL no prospective OMEGA predictions emitted')
 # No market/outcome columns allowed.
 bad=[c for c in outrows[0] if any(t in c.lower() for t in ('book','price','odds','edge','ev','actual_xtc','result','settlement'))]
 if bad:raise SystemExit('FAIL forbidden prospective ledger columns: '+','.join(bad))
 outbase=root/'data/prospective/nfl/omega/tackle_probability_016';out=outbase/source_id
 if out.exists():
  led=out/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv';hp=out/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.sha256'
  if led.exists() and hp.exists() and hp.read_text().strip()==sha(led):print(f'PASS existing immutable prospective ledger verified: {out}');return 0
  raise SystemExit('FAIL corrupt existing prospective output')
 stg=outbase/('.'+source_id+'.staging');stg.mkdir(parents=True,exist_ok=False)
 try:
  led=stg/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv';wcsv(led,outrows);hs=sha(led);(stg/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.sha256').write_text(hs+'\n')
  audit={'schemaVersion':'OMEGA_2026_PROSPECTIVE_PROBABILITY_0.16','generatedAt':now(),'sourceSnapshotId':sid,'pregameSourceSnapshotId':source_id,'season':2026,'week':week,'rows':len(outrows),'games':len({r['game_id'] for r in outrows}),'players':len({r['player_id'] for r in outrows}),'ledgerSha256':hs,'meanModelCoefficients':'exact OMEGA 0.12 global coefficients fit 2017-2024','historyStateAdmittedThrough':'2025 REG complete','omega2025Use':'strictly-prior 2026 state only; 0 tuning rows','distribution':'frozen OMEGA 0.16 NB_ROLE params fit through 2024','integrity':{'2026OutcomeRowsRead':0,'sameWeek2026OutcomesRead':0,'marketFieldsRead':0,'oddsPapiRequests':0,'targetPlayerUniverse':'captured pregame active-roster defenders; no target-game snap conditioning','verifiedReadyRows':0,'status':'PROSPECTIVE_RESEARCH_ONLY'}}
  (stg/'OMEGA_0.16_PROSPECTIVE_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n');os.replace(stg,out);(root/'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER').write_text(source_id+'\n')
 except Exception:
  shutil.rmtree(stg,ignore_errors=True);raise
 print('OMEGA 0.16 — 2026 WEEK 1 PROSPECTIVE PROBABILITY LEDGER')
 print(f"PASS predictions {len(outrows)} · games {len({r['game_id'] for r in outrows})} · players {len({r['player_id'] for r in outrows})}")
 print(f'PASS immutable ledger SHA256: {hs}')
 print('PASS frozen H008+H012 mean coefficients · frozen NB_ROLE distribution')
 print('PASS 2025 tuning rows 0 · 2026 outcomes 0 · market fields 0 · OddsPapi 0')
 print('STATUS: PROSPECTIVE_RESEARCH_ONLY — VERIFIED-ready rows 0 until authoritative game-day availability is integrated')
 print(f'REPORT: {out/"OMEGA_0.16_PROSPECTIVE_AUDIT.json"}')
 return 0
if __name__=='__main__':raise SystemExit(main())

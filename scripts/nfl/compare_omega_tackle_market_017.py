#!/usr/bin/env python3
"""Join immutable OMEGA-I probabilities to immutable raw T+A prices downstream.
Produces research comparison only. Never modifies OMEGA-I or raw market snapshots.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,math,os,re,shutil
EXPECTED_WEEK1_LEDGER='fe4991a743a1c02994b59d473a1bec9a1ccafa61a60548df43f2f5292e4ca08a'
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def rcsv(p):
 with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def norm_name(s):return re.sub(r'[^a-z0-9]','',str(s or '').lower())
def norm_team(s):return re.sub(r'[^A-Z0-9]','',str(s or '').upper())
def num(s):
 try:return float(s)
 except:return None
def american_break_even(a):
 a=float(a)
 if a==0:raise ValueError('zero American odds')
 return (-a)/((-a)+100) if a<0 else 100/(a+100)
def roi(p,a):
 a=float(a);profit=100/abs(a) if a<0 else a/100
 return p*profit-(1-p)
def devig(a,b):
 x=american_break_even(a);y=american_break_even(b);t=x+y
 return x/t,y/t
def is_half(line):return abs((float(line)*2)-round(float(line)*2))<1e-9 and int(round(float(line)*2))%2==1
def tag(line):return str(float(line)).replace('.','_')
def settlement_resolved(r):
 vals=[str(r.get('settlement_scope') or '').strip().upper(),str(r.get('includes_special_teams') or '').strip().upper(),str(r.get('stat_correction_policy') or '').strip().upper()]
 return all(v not in {'','UNKNOWN','UNRESOLVED','NA','N/A'} for v in vals)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='/Users/abbeyfelix/Developer/MODEL');ap.add_argument('--allow-ledger-hash',default=EXPECTED_WEEK1_LEDGER);a=ap.parse_args();root=Path(a.root).resolve()
 lp=root/'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_PROBABILITY_LEDGER';mp=root/'data/raw/nfl/omega/CURRENT_MARKET_SNAPSHOT'
 if not lp.exists():raise SystemExit('FAIL no current OMEGA probability ledger pointer')
 if not mp.exists():raise SystemExit('FAIL no current raw market snapshot pointer')
 lid=lp.read_text().strip();ld=root/'data/prospective/nfl/omega/tackle_probability_016'/lid;ledger=ld/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.csv';hp=ld/'OMEGA_2026_PROSPECTIVE_PROBABILITIES.sha256'
 if not ledger.exists() or not hp.exists():raise SystemExit('FAIL probability ledger/hash missing')
 actual=sha(ledger);recorded=hp.read_text().strip()
 if actual!=recorded:raise SystemExit('FAIL OMEGA-I ledger hash mismatch')
 if a.allow_ledger_hash and actual!=a.allow_ledger_hash:raise SystemExit(f'FAIL unexpected OMEGA-I ledger hash {actual}; expected {a.allow_ledger_hash}')
 mid=mp.read_text().strip();md=root/'data/raw/nfl/omega/market_snapshots'/mid;market=md/'normalized_market_rows.csv';mm=md/'MARKET_SNAPSHOT_MANIFEST.json'
 if not market.exists() or not mm.exists():raise SystemExit('FAIL market snapshot incomplete')
 mmeta=json.loads(mm.read_text());
 if mmeta.get('modelFieldsPresent') is not False or int(mmeta.get('oddsPapiRequests',0))!=0:raise SystemExit('FAIL raw-market integrity contract')
 lr=rcsv(ledger);mr=[r for r in rcsv(market) if str(r.get('market_kind') or '').lower()=='tackles_assists']
 byid={};byname={}
 for r in lr:
  pid=str(r.get('player_id') or '').strip(); key=(norm_name(r.get('player_name')),norm_team(r.get('team')))
  if pid:byid.setdefault(pid,[]).append(r)
  byname.setdefault(key,[]).append(r)
 out=[];unmatched=0;ambig=0;unsupported=0
 for m in mr:
  cand=[];pid=str(m.get('player_id') or '').strip()
  if pid:cand=byid.get(pid,[])
  if not cand:cand=byname.get((norm_name(m.get('player_name')),norm_team(m.get('player_team'))),[])
  opp=norm_team(m.get('opponent'))
  if opp and len(cand)>1:cand=[x for x in cand if norm_team(x.get('opponent'))==opp]
  if len(cand)==0:unmatched+=1;continue
  if len(cand)!=1:ambig+=1;continue
  l=num(m.get('line'))
  if l is None or not is_half(l) or l<0.5 or l>14.5:unsupported+=1;continue
  p=cand[0];t=tag(l);po=num(p.get('p_over_'+t));pu=num(p.get('p_under_'+t))
  if po is None or pu is None:unsupported+=1;continue
  over=num(m.get('over_odds_american'));under=num(m.get('under_odds_american'));side=str(m.get('one_sided_side') or '').upper();one=num(m.get('one_sided_odds_american'))
  row={'model_ledger_id':lid,'model_ledger_sha256':actual,'market_snapshot_id':mid,'market_captured_at':m.get('captured_at'),'book':m.get('book'),'game_id_model':p.get('game_id'),'player_id':p.get('player_id'),'player_name':p.get('player_name'),'team':p.get('team'),'opponent':p.get('opponent'),'line':f'{l:.1f}','predicted_xtc':p.get('predicted_xtc'),'predicted_snap_share':p.get('predicted_snap_share'),'distribution_role_tier':p.get('distribution_role_tier'),'model_p_over':po,'model_p_under':pu,'model_fair_over':p.get('fair_over_'+t),'model_fair_under':p.get('fair_under_'+t),'verified_ready':p.get('verified_ready'),'verified_block_reason':p.get('verified_block_reason'),'settlement_resolved':'TRUE' if settlement_resolved(m) else 'FALSE','market_reference_quality':'TWO_SIDED_NO_VIG' if over is not None and under is not None else 'ONE_SIDED_EV_ONLY'}
  if over is not None:
   row['over_price']=over;row['over_break_even']=american_break_even(over);row['over_roi']=roi(po,over);row['over_prob_edge']=po-row['over_break_even']
  if under is not None:
   row['under_price']=under;row['under_break_even']=american_break_even(under);row['under_roi']=roi(pu,under);row['under_prob_edge']=pu-row['under_break_even']
  if over is not None and under is not None:
   no,nu=devig(over,under);row['market_novig_over']=no;row['market_novig_under']=nu;row['model_vs_novig_over']=po-no;row['model_vs_novig_under']=pu-nu
  elif one is not None and side in {'OVER','UNDER'}:
   ps=po if side=='OVER' else pu;row['one_sided_side']=side;row['one_sided_price']=one;row['one_sided_break_even']=american_break_even(one);row['one_sided_roi']=roi(ps,one);row['one_sided_prob_edge']=ps-row['one_sided_break_even']
  blockers=[]
  if str(p.get('verified_ready')).upper()!='TRUE':blockers.append('AVAILABILITY_UNVERIFIED')
  if not settlement_resolved(m):blockers.append('SETTLEMENT_UNRESOLVED')
  row['actionability']='NON_ACTIONABLE' if blockers else 'RESEARCH_READY_ONLY';row['actionability_blockers']='|'.join(blockers)
  out.append(row)
 if not out:raise SystemExit(f'FAIL no comparable T+A rows · unmatched {unmatched} · ambiguous {ambig} · unsupported {unsupported}')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');sid=f'{stamp}_{actual[:8]}_{mid[-8:]}';base=root/'data/prospective/nfl/omega/market_comparison_017';final=base/sid;st=base/('.'+sid+'.staging');base.mkdir(parents=True,exist_ok=True);st.mkdir(parents=True,exist_ok=False)
 try:
  fields=[]
  for r in out:
   for k in r:
    if k not in fields:fields.append(k)
  op=st/'OMEGA_0.17_MARKET_COMPARISON.csv'
  with op.open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(out)
  oh=sha(op);audit={'schemaVersion':'OMEGA_MARKET_COMPARISON_0.17','generatedAt':now(),'omegaLedgerId':lid,'omegaLedgerSha256':actual,'marketSnapshotId':mid,'comparisonRows':len(out),'unmatchedRows':unmatched,'ambiguousRows':ambig,'unsupportedLineRows':unsupported,'twoSidedRows':sum(r['market_reference_quality']=='TWO_SIDED_NO_VIG' for r in out),'oneSidedRows':sum(r['market_reference_quality']=='ONE_SIDED_EV_ONLY' for r in out),'settlementResolvedRows':sum(r['settlement_resolved']=='TRUE' for r in out),'verifiedReadyRows':sum(str(r['verified_ready']).upper()=='TRUE' for r in out),'actionableRows':0,'modelReadOnly':True,'rawMarketReadOnly':True,'marketEnteredModel':False,'oddsPapiPlayerPropRequests':0,'comparisonSha256':oh,'status':'PROSPECTIVE_RESEARCH_ONLY'}
  (st/'OMEGA_0.17_MARKET_COMPARISON_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n');(st/'OMEGA_0.17_MARKET_COMPARISON.sha256').write_text(oh+'\n');os.replace(st,final);(root/'data/prospective/nfl/omega/CURRENT_OMEGA_TACKLE_MARKET_COMPARISON').write_text(sid+'\n')
 except Exception:
  shutil.rmtree(st,ignore_errors=True);raise
 print('OMEGA 0.17 — DOWNSTREAM MARKET COMPARISON ALPHA')
 print(f'PASS OMEGA-I ledger {actual} · read-only')
 print(f'PASS comparison rows {len(out)} · two-sided {audit["twoSidedRows"]} · one-sided {audit["oneSidedRows"]}')
 print(f'PASS unmatched {unmatched} · ambiguous {ambig} · unsupported lines {unsupported}')
 print(f'PASS settlement-resolved {audit["settlementResolvedRows"]} · VERIFIED-ready {audit["verifiedReadyRows"]} · actionable 0')
 print('PASS market entered OMEGA-I: NO · OddsPapi player-prop requests 0')
 print(f'PASS immutable comparison SHA256: {oh}')
 print('STATUS: PROSPECTIVE_RESEARCH_ONLY — positive EV is not a VERIFIED pick')
 print(f'REPORT: {final/"OMEGA_0.17_MARKET_COMPARISON_AUDIT.json"}')
 return 0
if __name__=='__main__':raise SystemExit(main())

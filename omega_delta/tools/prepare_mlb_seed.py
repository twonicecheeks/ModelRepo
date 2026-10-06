"""Build auditable, portable research inputs from the original public-data cache."""
import argparse
import hashlib
import json
import shutil
from collections import defaultdict, Counter
from datetime import date, timedelta
from pathlib import Path
from statistics import fmean


def readl(p): return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def dumps(p,a): p.write_text(json.dumps(a,indent=2)+'\n')
def outs(ip):
    pieces=str(ip).split('.')
    rem=int(pieces[1]) if len(pieces)>1 else 0
    if rem not in range(3): raise ValueError('Invalid baseball innings')
    return int(pieces[0])*3+rem


def prepare(root, target):
    target.mkdir(parents=True,exist_ok=True)
    replay=root/(root/'data/models/mlb/CURRENT_POSTSEASON_REPLAY_050').read_text().strip()
    outdir=root/(root/'data/normalized/mlb/CURRENT_HISTORICAL_OUTCOMES_030').read_text().strip()
    for src,dst in [('V2_REPRODUCTION_INPUTS.jsonl','REPRODUCTION_INPUTS.jsonl'),('MLB_POSTSEASON_HISTORY_PROXY_LEDGER.jsonl','BASELINE_LEDGER.jsonl'),('POSTSEASON_REPLAY_MANIFEST.json','REPLAY_MANIFEST.json')]:shutil.copyfile(replay/src,target/dst)
    shutil.copyfile(outdir/'MLB_HISTORICAL_OUTCOMES.jsonl',target/'OUTCOMES.jsonl')
    outcomes=readl(target/'OUTCOMES.jsonl');post=defaultdict(list)
    for g in outcomes:
        for side in ['away','home']:
            st=g[side]['starter'];key=(g['season'],str(st['mlb_id']))
            if st['games_started']!=1: continue
            post[key].append({'date':g['game_date'],'outs':outs(st['innings_pitched']),'game_id':g['game_id']})
    observations,pairs=[],[]
    for (year,pid),starts in sorted(post.items()):
        p=root/f'data/raw/mlb/historical_priors_040/mlb/starter_gamelog/{year}/{pid}.json'
        if not p.exists(): continue
        data=json.loads(p.read_text());reg=[]
        first_post=min(s['date'] for s in starts)
        for group in data.get('stats',[]):
            for s in group.get('splits',[]):
                st=s.get('stat',{})
                if s.get('gameType')!='R' or st.get('gamesStarted')!=1 or s.get('date','9999')>=first_post:continue
                reg.append({'date':s['date'],'outs':outs(st['inningsPitched']),'game_id':str(s.get('game',{}).get('gamePk',''))})
        if not reg: continue
        cutoff=(date.fromisoformat(max(s['date'] for s in reg))-timedelta(days=44)).isoformat()
        late=[s for s in reg if s['date']>=cutoff]
        observations.append({'season':year,'pitcher_id':pid,'regular_starts':late,'postseason_starts':starts})
        if len(late)<3 or fmean(s['outs'] for s in late)<=0: continue
        a,b=fmean(s['outs'] for s in late),fmean(s['outs'] for s in starts)
        pairs.append({'season':year,'pitcher_id':pid,'reg_games':len(late),'post_games':len(starts),
                      'reg_mean_outs':a,'post_mean_outs':b,'outs_ratio':b/a})
    dumps(target/'USAGE_PAIRS.json',pairs)
    (target/'USAGE_OBSERVATIONS.jsonl').write_text('\n'.join(json.dumps(x) for x in observations)+'\n')
    rawpath=root/'data/raw/mlb/market_archive/sbr_10Y.json';raw=json.loads(rawpath.read_text())
    ids={108:'Angels',109:'Diamondbacks',110:'Orioles',111:'Red Sox',112:'Cubs',113:'Reds',114:'Indians',115:'Rockies',116:'Tigers',117:'Astros',118:'Royals',119:'Dodgers',120:'Nationals',121:'Mets',133:'Athletics',134:'Pirates',135:'Padres',136:'Mariners',137:'Giants',138:'Cardinals',139:'Rays',140:'Rangers',141:'Blue Jays',142:'Twins',143:'Phillies',144:'Braves',145:'White Sox',146:'Marlins',147:'Yankees',158:'Brewers'}
    index=defaultdict(list)
    for q in raw:
        if q.get('date'):index[str(int(q['date']))].append(q)
    audit=[];counts=Counter()
    for g in outcomes:
        qs=index[g['game_date'].replace('-','')]
        reason='MISSING_DATE' if not qs else 'TEAM_IDENTITY_MISMATCH'
        matches=[q for q in qs if q['home_team']==ids[g['home']['team_id']] and q['away_team']==ids[g['away']['team_id']]]
        if matches:
            matches=[q for q in matches if q['home_final']==g['home']['score'] and q['away_final']==g['away']['score']]
            reason='SCORE_OR_AMBIGUOUS_MATCH' if len(matches)!=1 else 'MISSING_BOOK_AND_ENTRY_TIMESTAMP'
        counts[reason]+=1;audit.append({'game_id':g['game_id'],'date':g['game_date'],'status':reason})
    dumps(target/'MARKET_ARCHIVE_AUDIT.json',{'source_url':'https://raw.githubusercontent.com/flancast90/sportsbookreview-scraper/1a820e50c6fbd0276cde073c22bfffae78930868/data/mlb_archive_10Y.json',
          'sha256':hashlib.sha256(rawpath.read_bytes()).hexdigest(),'records':len(raw),'coverage_counts':dict(counts),
          'accepted':0,'status':'REJECTED','rows':audit,'identity_repaired_by_outcomes':False})
    prior=root/(root/'data/normalized/mlb/CURRENT_POSTSEASON_PRIORS_040').read_text().strip()
    shutil.copyfile(prior/'POSTSEASON_PRIORS_MANIFEST.json',target/'SOURCE_MANIFEST.json')
    print(f'Portable inputs ready. Matched workload pairs: {len(pairs)}. Archive: {dict(counts)}')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--target',type=Path,required=True);a=ap.parse_args();prepare(a.root,a.target)

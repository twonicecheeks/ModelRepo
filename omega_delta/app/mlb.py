"""Local MLB board, frozen model, quotes, and prospective evidence journal."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import threading
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .core import canonical, now, stamp
from .mlb_model import (exposure_ml, postseason_k, logistic, logit,
                        k_probabilities, quote_ev, fair_odds, decimal_odds, settle)
from .delta import Delta, model_files, project_delta
from .delta_model import at_line

ROOT=Path(__file__).resolve().parents[1]
TEAM_CODES={108:'LAA',109:'ARI',110:'BAL',111:'BOS',112:'CHC',113:'CIN',114:'CLE',115:'COL',116:'DET',117:'HOU',118:'KC',119:'LAD',120:'WSH',121:'NYM',133:'OAK',134:'PIT',135:'SD',136:'SEA',137:'SF',138:'STL',139:'TB',140:'TEX',141:'TOR',142:'MIN',143:'PHI',144:'ATL',145:'CWS',146:'MIA',147:'NYY',158:'MIL'}
BASE='https://statsapi.mlb.com/api/v1'


def json_file(p):return json.loads(p.read_text())


def project(inputs, workloads, frozen, delta_profiles=None):
    # User input cannot inject outcomes or odds into the inference process.
    from .mlb_model import strip_targets
    if not shutil.which('node'):raise ValueError('MLB projection needs Node 18 or newer. The historical report remains available.')
    proc=subprocess.run(['node',str(ROOT/'tools/mlb_project.cjs')],input=canonical([strip_targets(r) for r in inputs]),text=True,capture_output=True,timeout=45)
    if proc.returncode:raise ValueError('MLB input could not be projected: '+proc.stderr.splitlines()[0][:220])
    projections=json.loads(proc.stdout);factor=frozen['usage']['factor'];ml,krows=None,[]
    delta_model=model_files();drows=[];delta_profiles=delta_profiles or {}
    for row,result in zip(inputs,projections):
        base=result['base']
        if row['replay_type']=='ML':
            ml=exposure_ml(base,workloads,factor);c=frozen['calibration']
            ml.update(baseline_home_probability=base['homeWin'],calibrated_home_probability=logistic(c['intercept']+c['slope']*logit(ml['home_probability'])))
        else:
            k=postseason_k(base,factor,row.get('workload_mode','HISTORY_PROXY'),row.get('regular_starts',True))
            k.update(baseline_k=base['expectedK'],team=row['starter_input']['team'])
            krows.append(k)
            profile=delta_profiles.get(f"{row['game_id']}:{k['player_id']}")
            drows.append(project_delta(row,k,delta_model,profile))
    if ml is None or len(krows)!=2:raise ValueError('Each game needs one moneyline input and two starter inputs.')
    return {'moneyline':ml,'starters':krows,'delta':drows,'model_version':frozen['model_version'],'model_sha256':hashlib.sha256(canonical(frozen).encode()).hexdigest(),'edge_status':'NOT_VERIFIED'}


class MLB:
    def __init__(self,store):
        self.store=store
        self.frozen=json_file(ROOT/'audit/mlb/FROZEN_MODEL.json')
        self.report=json_file(ROOT/'audit/mlb/BACKTEST_REPORT.json')
        self.delta=Delta(store)
        self.operation_lock=threading.Lock()
        initial=ROOT/'seed/mlb/INITIAL_BOARD.json'
        if initial.exists() and not store.setting('mlb_board'):
            store.set_setting('mlb_board',json_file(initial))

    def operation(self,kind,*args):
        if not self.operation_lock.acquire(False):raise ValueError('An MLB collection or grading operation is already running.')
        try:
            result=getattr(self,kind)(*args)
            self.store.set_setting('mlb_last_failure',None)
            return result
        except Exception as e:
            self.store.set_setting('mlb_last_failure',{'at':now(),'error':str(e)[:300]})
            raise
        finally:self.operation_lock.release()

    def delta_grade(self):
        return self.delta.grade(self)

    def state(self):
        board=self.store.setting('mlb_board',{'games':[],'status':'NOT_REFRESHED'})
        board=dict(board)
        # A saved pregame snapshot never silently becomes an actionable live forecast.
        current=stamp(now())
        board['games']=[dict(g,display_status='STARTED' if stamp(g['start_at'])<=current else g['status']) for g in board.get('games',[])]
        return {'board':board,'frozen':self.frozen,'report':self.report,
                'quotes':self.store.setting('mlb_quotes',[]),'prospective':self.store.setting('mlb_prospective',{}),
                'node_available':bool(shutil.which('node')),'last_failure':self.store.setting('mlb_last_failure'),
                'delta':self.delta.state()}

    def fetch(self,url):
        req=urllib.request.Request(url,headers={'User-Agent':'OMEGA/2.0 public baseball research'})
        with urllib.request.urlopen(req,timeout=25) as r:
            raw=r.read(25_000_001)
        if len(raw)>25_000_000:raise ValueError('Public response too large')
        self.receipts.append({'url':url,'received_at':now(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
        # Retain actual source payloads in the append-only snapshot journal.
        self.store.snapshot('mlb_source',url,raw.decode('utf-8'))
        return raw.decode('utf-8')

    def get(self,path,**params):
        url=BASE+path+('?' + urllib.parse.urlencode(params) if params else '')
        return json.loads(self.fetch(url))

    def refresh(self,iso_date=None):
        from zoneinfo import ZoneInfo
        iso_date=iso_date or datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        d=date.fromisoformat(iso_date);year=d.year
        if year!=self.frozen['season']:raise ValueError('The frozen candidate is for 2026. Revalidate before a new season.')
        self.receipts=[]
        sched=self.get('/schedule',sportId=1,date=iso_date,gameTypes='F,D,L,W',hydrate='team,probablePitcher,venue')
        games=[]
        for dt in sched.get('dates',[]):
            for g in dt.get('games',[]):
                record={'game_id':str(g['gamePk']),'start_at':g['gameDate'],'game_date':iso_date,
                        'abstract_state':g['status'].get('abstractGameCode'),'official_status':g['status']['detailedState'],
                        'venue':g.get('venue',{}).get('name','')}
                for side in ['away','home']:
                    t=g['teams'][side];pid=t.get('probablePitcher',{}).get('id')
                    record[side]={'id':t['team']['id'],'code':TEAM_CODES.get(t['team']['id'],t['team']['name']),
                                  'pitcher_id':pid,'pitcher_name':t.get('probablePitcher',{}).get('fullName')}
                record['away_code']=record['away']['code'];record['home_code']=record['home']['code']
                games.append(record)
        ready=[];blocked=[]
        for g in games:
            view={'game_id':g['game_id'],'start_at':g['start_at'],'away':g['away_code'],'home':g['home_code']}
            if g['abstract_state'] not in {'P','S'} or stamp(g['start_at'])<=stamp(now()):
                blocked.append(dict(view,status='STARTED',reason=g['official_status']));continue
            g['box']=self.get('/game/'+g['game_id']+'/boxscore')
            # Avoid downloading features before both batting orders exist.
            valid=all(sum(bool(re.fullmatch(r'[1-9]00',str(p.get('battingOrder','')))) for p in g['box'].get('teams',{}).get(s,{}).get('players',{}).values())==9 for s in ['away','home'])
            if not valid or not all(g[s]['pitcher_id'] for s in ['away','home']):
                blocked.append(dict(view,status='BLOCKED',reason='Waiting for both official batting orders and probable starters'));continue
            ready.append(g)
        generated=[]
        if ready:
            assets={}
            selections='pa,k_percent,bb_percent,batting_avg,xba,xslg,xwoba,isolated_power,hard_hit_percent,barrel_batted_rate,whiff_percent,swing_percent'
            urls={}
            for y,prefix in [(year,'savant'),(year-1,'previous')]:
                for kind in ['pitcher','batter']:
                    urls[prefix+'_'+kind]='https://baseballsavant.mlb.com/leaderboard/custom?'+urllib.parse.urlencode({'year':y,'type':kind,'filter':'','min':1,'selections':selections,'chart':'false','x':'pa','y':'pa','r':'no','csv':'true'})
            for y,key in [(year,'wrc'),(year-1,'previous_wrc')]:
                urls[key]='https://www.fangraphs.com/api/leaders/major-league/data?'+urllib.parse.urlencode({'age':'','pos':'all','stats':'bat','lg':'all','qual':0,'season':y,'season1':y,'startdate':'','enddate':'','month':0,'hand':'','team':0,'pageitems':2000,'pagenum':1,'ind':0,'rost':0,'players':'','type':8,'postseason':'','sortdir':'default','sortstat':'WAR'})
            for rolling in [3,2,1]:urls['park_'+str(rolling)]='https://baseballsavant.mlb.com/leaderboard/statcast-park-factors?'+urllib.parse.urlencode({'condition':'All','parks':'mlb','rolling':rolling,'stat':'index_wOBA','type':'year','year':year})
            # Independent public reads; source snapshots remain serialized by Store.
            with ThreadPoolExecutor(max_workers=5) as pool:
                for key,raw in zip(urls,pool.map(self.fetch,urls.values())):assets[key]=json.loads(raw) if 'wrc' in key else raw
            previous=self.get('/schedule',sportId=1,date=(d-timedelta(days=1)).isoformat(),gameTypes='R,F,D,L,W',hydrate='team')
            boxes={str(g['gamePk']):self.get('/game/'+str(g['gamePk'])+'/boxscore') for dt in previous.get('dates',[]) for g in dt.get('games',[])}
            for g in ready:
                g.update(previous_schedule=previous,previous_boxes=boxes)
                for side in ['away','home']:
                    t=g[side];tid=t['id']
                    t['log']=self.get('/people/'+str(t['pitcher_id'])+'/stats',stats='gameLog',group='pitching',season=year,gameType='R')
                    t['stats']=self.get('/stats',stats='season',group='pitching',season=year,teamId=tid,playerPool='All',gameType='R',limit=100,hydrate='person')
                    t['roster']=self.get('/teams/'+str(tid)+'/roster',rosterType='active',season=year,date=iso_date,hydrate='person')
            payload={'season':year,'captured_at':now(),'assets':assets,'games':ready}
            proc=subprocess.run(['node',str(ROOT/'tools/build_mlb_live.cjs')],input=canonical(payload),text=True,capture_output=True,timeout=60)
            if proc.returncode:raise ValueError('Could not assemble MLB inputs: '+proc.stderr.splitlines()[0][:220])
            for g in json.loads(proc.stdout):
                inputs=g.pop('inputs',None);workloads=g.pop('workloads',None)
                if inputs:
                    profiles={key:p for key,p in self.store.setting('delta_profiles',{}).items() if key.startswith(g['game_id']+':')}
                    for p in profiles.values():
                        if stamp(p['start_at'])!=stamp(g['start_at']) or stamp(p['observed_at'])>=stamp(g['start_at']):
                            raise ValueError('DELTA profile time does not match the official game; import corrected inputs.')
                    forecast=project(inputs,workloads,self.frozen,profiles)
                    captured=now()
                    if stamp(captured)>=stamp(g['start_at']):g.update(status='STARTED',reason='First pitch passed during collection')
                    else:
                        g.update(forecast=forecast,captured_at=captured,inputs_sha256=hashlib.sha256(canonical(inputs).encode()).hexdigest())
                        g['snapshot_id']=self.store.snapshot('mlb_forecast',g['game_id'],canonical({'game':g,'inputs':inputs,'workloads':workloads,'receipts':self.receipts,'frozen_model':self.frozen,'delta_model':model_files(),'delta_profiles':profiles}))
                generated.append(g)
        board={'date':iso_date,'captured_at':now(),'games':blocked+generated,'status':'RECORDED','market_requests':0,
               'receipts':self.receipts,'edge_status':'NOT_VERIFIED'}
        self.store.snapshot('mlb_board',iso_date,canonical(board));self.store.set_setting('mlb_board',board)
        return {'games':len(board['games']),'ready':sum(g['status']=='READY_RESEARCH' for g in board['games']),'blocked':sum(g['status']=='BLOCKED' for g in board['games']),'market_requests':0}

    def import_quotes(self,raw,name='mlb-quotes.csv'):
        rows=list(csv.DictReader(io.StringIO(raw)))
        if not 1<=len(rows)<=5000:raise ValueError('Import 1–5,000 MLB quote rows.')
        board=self.store.setting('mlb_board',{});bygame={g['game_id']:g for g in board.get('games',[])}
        accepted=[]
        for i,row in enumerate(rows,2):
            try:
                g=bygame[row['game_id']];f=g.get('forecast')
                if not f:raise ValueError('Game has no saved pregame forecast.')
                t=stamp(row['captured_at'])
                if t>=stamp(g['start_at']) or t>stamp(now()):raise ValueError('Quote must precede first pitch and cannot be future-dated.')
                if stamp(g['captured_at'])>=stamp(g['start_at']):raise ValueError('Forecast was not frozen pregame.')
                if stamp(g['captured_at'])>t:raise ValueError('Quote predates the saved forecast; later inputs cannot price an earlier entry.')
                if row['settlement_definition']!='FULL_GAME':raise ValueError('Use FULL_GAME settlement; first-five/inning markets cannot be compared.')
                book=row['book'].strip()
                if not book or not row.get('source','').strip():raise ValueError('Book and source are required.')
                odds=float(row['odds']);decimal_odds(odds);kind=row['market_type'].upper();side=row['side'].upper()
                if kind=='ML':
                    if side not in {g['home'],g['away']}:raise ValueError('Selection is not a team in this game.')
                    # Moneyline challengers failed improvement: expose both; no production promotion.
                    ph=f['moneyline']['calibrated_home_probability'];p=ph if side==g['home'] else 1-ph
                    pb=f['moneyline']['baseline_home_probability'];baseline=pb if side==g['home'] else 1-pb
                    push=0.;line=None;pid=''
                elif kind=='K':
                    if side not in {'OVER','UNDER'}:raise ValueError('K side must be OVER or UNDER.')
                    pid=str(row['player_id']);s=next((s for s in f['starters'] if s['player_id']==pid),None)
                    if not s:raise ValueError('Pitcher identity does not match this forecast.')
                    line=float(row['line']);probs=k_probabilities(s['expected_k'],line,s['uncertainty_multiplier']);p=probs[side.lower()];push=probs['push']
                    baseline=k_probabilities(s['baseline_k'],line,s['uncertainty_multiplier'])[side.lower()]
                else:raise ValueError('Market must be ML or K.')
                delta_quote={}
                if kind=='K':
                    d=next((d for d in f.get('delta',[]) if d['player_id']==pid),None)
                    if d:
                        dp=at_line(d['pa']['pmf'],line)
                        delta_quote={'delta_probability':dp[side.lower()],'delta_push_probability':dp['push'],'delta_ev':quote_ev(dp[side.lower()],dp['push'],odds),'delta_fair_odds':fair_odds(dp[side.lower()],dp['push']),'delta_model_version':d['model_version']}
                accepted.append({'id':uuid.uuid4().hex,'game_id':g['game_id'],'market_type':kind,'side':side,'player_id':pid,'line':line,'book':book,'odds':odds,'captured_at':row['captured_at'],'received_at':now(),'source':row['source'],'forecast_snapshot_id':g['snapshot_id'],'probability':p,'baseline_probability':baseline,'push_probability':push,'ev':quote_ev(p,push,odds),'baseline_ev':quote_ev(baseline,push,odds),'fair_odds':fair_odds(p,push),'status':'RESEARCH_ONLY','entry_receipt_verified':False,'settlement_definition':'FULL_GAME',**delta_quote})
            except (KeyError,ValueError,StopIteration) as e:raise ValueError(f'Quote row {i}: {e}') from e
        sid=self.store.snapshot('mlb_quotes',name,raw)
        for q in accepted:q['quote_snapshot_id']=sid
        existing=self.store.setting('mlb_quotes',[])
        self.store.set_setting('mlb_quotes',existing+accepted)
        return {'rows':len(accepted),'snapshot_id':sid,'evidence_status':'USER_SUPPLIED_PRICES_UNVERIFIED'}

    def grade(self):
        self.receipts=[];quotes=self.store.setting('mlb_quotes',[]);targets={}
        for gid in sorted({q['game_id'] for q in quotes}):
            if not re.fullmatch(r'\d+',gid):continue
            live=self.get('/game/'+gid+'/linescore');box=self.get('/game/'+gid+'/boxscore')
            # Schedule status is the authoritative final flag.
            sched=self.get('/schedule',sportId=1,gamePk=gid)
            gs=[g for d in sched.get('dates',[]) for g in d.get('games',[])]
            if len(gs)!=1 or gs[0]['status'].get('abstractGameCode')!='F':continue
            home=live.get('teams',{}).get('home',{}).get('runs');away=live.get('teams',{}).get('away',{}).get('runs')
            if home is None or away is None or home==away:continue
            starters={}
            for side in ['away','home']:
                team=box.get('teams',{}).get(side,{})
                for p in team.get('players',{}).values():
                    st=p.get('stats',{}).get('pitching',{})
                    if st.get('gamesStarted')==1:starters[str(p['person']['id'])]=st.get('strikeOuts')
            targets[gid]={'home_win':int(home>away),'starters':starters,'home':TEAM_CODES.get(gs[0]['teams']['home']['team']['id'])}
        grades=[]
        for q in quotes:
            t=targets.get(q['game_id'])
            if not t:continue
            if q['market_type']=='ML':actual=t['home_win'] if q['side']==t['home'] else 1-t['home_win'];selection='ML'
            else:
                actual=t['starters'].get(q['player_id']);selection=q['side']
                if actual is None:continue  # scratched/relief pitchers never get substituted.
            grades.append({'quote_id':q['id'],'game_id':q['game_id'],'actual':actual,'flat_unit_profit':settle(selection,actual,q['line'],q['odds']),'candidate_qualifies':q['ev']>=.02,'status':'EXPLORATORY_USER_QUOTES'})
        result={'status':'EDGE_NOT_VERIFIED','graded_quotes':len(grades),'grades':grades,
                'note':'Imported prices are unverified, and repeated quotes are not independent wagers. No profit-based promotion.'}
        self.store.snapshot('mlb_grading','Prospective research grading',canonical(result));self.store.set_setting('mlb_prospective',result)
        return {'graded_quotes':len(grades),'status':result['status']}

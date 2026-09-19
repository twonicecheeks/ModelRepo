#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const TEAM_ID_CODE = Object.freeze({
  '108':'LAA','109':'ARI','110':'BAL','111':'BOS','112':'CHC','113':'CIN','114':'CLE',
  '115':'COL','116':'DET','117':'HOU','118':'KC','119':'LAD','120':'WSH','121':'NYM',
  '133':'OAK','134':'PIT','135':'SD','136':'SEA','137':'SF','138':'STL','139':'TB',
  '140':'TEX','141':'TOR','142':'MIN','143':'PHI','144':'ATL','145':'CWS','146':'MIA',
  '147':'NYY','158':'MIL'
});

const TEAM_CODE_NICKNAME = Object.freeze({
  ARI:'Diamondbacks',ATL:'Braves',BAL:'Orioles',BOS:'Red Sox',CHC:'Cubs',CWS:'White Sox',
  CIN:'Reds',CLE:'Guardians',COL:'Rockies',DET:'Tigers',HOU:'Astros',KC:'Royals',
  LAA:'Angels',LAD:'Dodgers',MIA:'Marlins',MIL:'Brewers',MIN:'Twins',NYM:'Mets',
  NYY:'Yankees',OAK:'Athletics',PHI:'Phillies',PIT:'Pirates',SD:'Padres',SF:'Giants',
  SEA:'Mariners',STL:'Cardinals',TB:'Rays',TEX:'Rangers',TOR:'Blue Jays',WSH:'Nationals'
});

const HISTORICAL_VENUE_ALIASES = Object.freeze({
  'dodger stadium':'UNIQLO Field at Dodger Stadium',
  'minute maid park':'Daikin Park',
  'at t park':'Oracle Park',
  'miller park':'American Family Field',
  'suntrust park':'Truist Park',
  'guaranteed rate field':'Rate Field',
  'safeco field':'T-Mobile Park',
  'marlins park':'loanDepot park'
});

const VERSION='0.5.4';
const LINEAGE='mlb-postseason-history-proxy-replay-v0.5.4-ruleset-diagnostics-2026-09-19';

function readJson(p){ return JSON.parse(fs.readFileSync(p,'utf8')); }
function readText(p){ return fs.readFileSync(p,'utf8'); }
function readJsonl(p){
  return fs.readFileSync(p,'utf8').split(/\r?\n/).filter(x=>x.trim()).map((x,i)=>{
    try{return JSON.parse(x);}catch(e){throw new Error(`${p}:${i+1}: ${e.message}`);}
  });
}
function writeJsonl(p,rows){
  fs.mkdirSync(path.dirname(p),{recursive:true});
  const tmp=path.join(path.dirname(p),'.'+path.basename(p)+'.tmp');
  fs.writeFileSync(tmp,rows.map(x=>JSON.stringify(x)).join('\n')+'\n','utf8');
  fs.renameSync(tmp,p);
}
function sha256File(p){
  const h=crypto.createHash('sha256');h.update(fs.readFileSync(p));return h.digest('hex');
}
function mean(xs){
  const v=(xs||[]).map(Number).filter(Number.isFinite);
  return v.length?v.reduce((a,b)=>a+b,0)/v.length:null;
}
function num(v,f=null){
  if(v===null||v===undefined||v==='')return f;
  const n=Number(v);return Number.isFinite(n)?n:f;
}
function ipToOuts(v){
  if(v===null||v===undefined||v==='')return null;
  const m=String(v).match(/^(\d+)(?:\.(\d))?$/);
  if(!m)return null;
  const whole=Number(m[1]), rem=m[2]==null?0:Number(m[2]);
  if(rem<0||rem>2)return null;
  return whole*3+rem;
}
function priorDate(iso){
  const d=new Date(iso+'T00:00:00Z'); d.setUTCDate(d.getUTCDate()-1);
  return d.toISOString().slice(0,10);
}
function teamCode(starterCore,team){
  const byName=starterCore.teamCode(team?.name);
  if(byName)return byName;
  return TEAM_ID_CODE[String(team?.team_id||'')]||null;
}


function rulesetForSeason(season){
  const y=Number(season);
  return y===2020 || y>=2022 ? 'UNIVERSAL_DH' : 'PRE_UNIVERSAL_DH';
}
function normalizeLabel(v){
  return String(v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .replace(/[^a-z0-9]+/g,' ').replace(/\s+/g,' ').trim();
}
function resolvePark(parkCore,bundle,venueName,homeCode){
  const direct=parkCore.getForVenue(bundle,venueName);
  if(direct)return {row:direct,method:'VENUE_NAME'};
  const alias=HISTORICAL_VENUE_ALIASES[normalizeLabel(venueName)];
  if(alias){
    const aliased=parkCore.getForVenue(bundle,alias);
    if(aliased)return {row:aliased,method:'HISTORICAL_VENUE_ALIAS',alias};
  }
  const nickname=normalizeLabel(TEAM_CODE_NICKNAME[homeCode]||'');
  if(!nickname)return {row:null,method:'UNRESOLVED'};
  const matches=(bundle?.rows||[]).filter(r=>{
    const t=normalizeLabel(r?.team);
    const v=normalizeLabel(r?.venue);
    return t===nickname || t.endsWith(' '+nickname) || nickname.endsWith(' '+t) ||
      (homeCode==='LAD'&&v.includes('dodger stadium')) ||
      (homeCode==='HOU'&&(v.includes('daikin park')||v.includes('minute maid park')));
  });
  return matches.length===1?{row:matches[0],method:'HOME_TEAM_IDENTITY'}:{row:null,method:'UNRESOLVED'};
}
function historicalStartingLineup(boxscore,side){
  const team=boxscore?.teams?.[side];
  if(!team)return {state:'ERROR',count:0,hitters:[],reason:`boxscore missing teams.${side}`};
  const rows=Object.values(team.players||{}).filter(p=>{
    const bo=String(p?.battingOrder||'');
    return /^\d00$/.test(bo) && p?.person?.id != null;
  }).sort((a,b)=>Number(a.battingOrder)-Number(b.battingOrder));
  const seen=new Set(),hitters=[];
  for(const p of rows){
    const id=String(p.person.id);
    if(seen.has(id))continue;
    seen.add(id);
    hitters.push({
      mlbId:id,name:p?.person?.fullName||null,order:Math.floor(Number(p.battingOrder)/100),
      battingOrder:String(p.battingOrder),position:p?.position?.abbreviation||null
    });
  }
  if(hitters.length===9&&hitters.every(x=>x.name&&x.order>=1&&x.order<=9)){
    return {state:'OFFICIAL',count:9,hitters,reason:null,source:'completed MLB boxscore starter battingOrder codes'};
  }
  return {state:'INCOMPLETE',count:hitters.length,hitters,reason:`starter-coded boxscore lineup contains ${hitters.length}/9 hitters`};
}
function defaultPointer(root,rel,leaf){
  const p=path.join(root,rel);
  if(!fs.existsSync(p))throw new Error(`missing pointer ${p}`);
  const dir=fs.readFileSync(p,'utf8').trim();
  const out=path.join(root,dir,leaf);
  if(!fs.existsSync(out))throw new Error(`missing pointed file ${out}`);
  return out;
}
function statSplits(payload){
  const out=[];
  for(const group of payload?.stats||[]) for(const split of group?.splits||[]) out.push(split);
  return out;
}
function parsePitchingGameLog(payload){
  const rows=[];
  for(const split of statSplits(payload)){
    const st=split?.stat||{};
    const outs=ipToOuts(st.inningsPitched);
    const date=String(split?.date||split?.game?.gameDate||split?.gameDate||'').slice(0,10);
    if(!date||outs===null||outs<=0)continue;
    rows.push({
      date,
      gamePk: split?.game?.gamePk??split?.game?.id??null,
      gamesStarted:num(st.gamesStarted,0),
      outs,
      er:num(st.earnedRuns),
      hits:num(st.hits),
      bb:num(st.baseOnBalls),
      k:num(st.strikeOuts),
      bf:num(st.battersFaced),
      pitches:num(st.numberOfPitches),
    });
  }
  rows.sort((a,b)=>a.date.localeCompare(b.date)||String(a.gamePk||'').localeCompare(String(b.gamePk||'')));
  return rows;
}
function selectWorkloadHistory(rows,snapshotAt){
  const prior=(rows||[]).filter(x=>x.date < snapshotAt.slice(0,10));
  const starts=prior.filter(x=>Number(x.gamesStarted)>=1);
  if(starts.length)return {rows:starts,mode:'REGULAR_SEASON_STARTS'};
  if(prior.length)return {rows:prior,mode:'REGULAR_SEASON_APPEARANCES_OPENER_FALLBACK'};
  return {rows:[],mode:'EMPTY'};
}
function historyMarket(values,snapshotAt){
  const xs=(values||[]).map(Number).filter(Number.isFinite);
  return {
    state:'HISTORICAL_HISTORY_ONLY',
    observedAt:snapshotAt,
    representative:null,
    offers:[],
    statistics:{
      overall:{
        l30:xs.slice(-30),
        season:{average:mean(xs),hit:null,total:xs.length},
        pitcherGrade:null
      },
      vsLeft:{l30:[],season:{average:null,hit:null,total:null},pitcherGrade:null},
      vsRight:{l30:[],season:{average:null,hit:null,total:null},pitcherGrade:null}
    }
  };
}
function workloadMarkets(gameLog,snapshotAt){
  const selected=selectWorkloadHistory(gameLog,snapshotAt);
  const logs=selected.rows;
  return {
    mode:selected.mode,
    logs,
    markets:{
      'player-strikeouts':historyMarket(logs.map(x=>x.k),snapshotAt),
      'player-pitcher-outs':historyMarket(logs.map(x=>x.outs),snapshotAt),
      'player-earned-runs':historyMarket(logs.map(x=>x.er),snapshotAt),
      'player-hits-allowed':historyMarket(logs.map(x=>x.hits),snapshotAt),
      'player-walks':historyMarket(logs.map(x=>x.bb),snapshotAt),
    }
  };
}
function kSkillRow(kCore,bundle,id){
  const r=kCore.savantRow(bundle,id,{minCurrent:30,minPrevious:60});
  if(!r)return null;
  return {
    mlbId:String(r.playerId),name:r.name||null,pa:num(r.pa,0),
    K:num(r.kPct),Whiff:num(r.whiffPct),SwStr:num(r.swStrPct),Contact:num(r.contactPct),BB:num(r.bbPct),
    sourceSeason:r.sourceSeason||null,sampleCurrent:num(r.sampleCurrent,0),samplePrevious:num(r.samplePrevious,0),
    previousK:num(r.previousK),previousWhiff:num(r.previousWhiff),previousSwStr:num(r.previousSwStr),previousContact:num(r.previousContact)
  };
}
function mlOpponentMetrics(mlCore,lineup){
  const la=mlCore.lineupAverages(lineup);
  const bas=lineup.map(x=>mlCore.validatedMetric({'BA':x?.metrics?.BA??x?.BA},'BA',null)).filter(Number.isFinite);
  return {
    'xwOBA':la.xwoba,'BA':mean(bas),'xSLG':la.xslg,'HardHit%':la.hardhit,'Barrel%':la.barrel,
    'K%':la.k,'BB%':la.bb,'Contact%':la.contact
  };
}
function loadPriorDayUsage(root,game,bullpenCore){
  const iso=priorDate(String(game.game_date).slice(0,10));
  const schedPath=path.join(root,`data/raw/mlb/historical_priors_040/mlb/prior_day_schedule/${iso}.json`);
  if(!fs.existsSync(schedPath)){
    return {usedByTeam:new Map(),knownTeams:new Set(),scheduledCount:new Map(),resolvedCount:new Map()};
  }
  const sched=readJson(schedPath), boxes=new Map();
  for(const d of sched?.dates||[]) for(const g of d?.games||[]){
    const pk=String(g?.gamePk||''); if(!pk)continue;
    const bp=path.join(root,`data/raw/mlb/historical_priors_040/mlb/prior_day_boxscore/${pk}.json`);
    if(fs.existsSync(bp))boxes.set(pk,readJson(bp));
  }
  return bullpenCore.parseYesterdayUsage(
    sched,boxes,[String(game.away.team_id),String(game.home.team_id)]
  );
}
function parseArgs(argv){
  const a={root:'/Users/abbeyfelix/Developer/MODEL',outcomes:null,priors:null,output:null,strictCoverage:false};
  for(let i=2;i<argv.length;i++){
    const x=argv[i];
    if(x==='--root')a.root=argv[++i];
    else if(x==='--outcomes')a.outcomes=argv[++i];
    else if(x==='--priors')a.priors=argv[++i];
    else if(x==='--output')a.output=argv[++i];
    else if(x==='--strict-coverage')a.strictCoverage=true;
    else throw new Error(`unknown argument ${x}`);
  }
  return a;
}

function main(){
  const args=parseArgs(process.argv), root=path.resolve(args.root);
  const starterCore=require(path.join(root,'packages/providers/mlb_official/src/starter_core.js'));
  const bullpenCore=require(path.join(root,'packages/providers/mlb_official/src/bullpen_core.js'));
  const savantCore=require(path.join(root,'packages/providers/baseball_savant/src/savant_core.js'));
  const parkCore=require(path.join(root,'packages/providers/baseball_savant/src/park_factor_core.js'));
  const wrcCore=require(path.join(root,'packages/providers/fangraphs/src/wrc_core.js'));
  const mlCore=require(path.join(root,'packages/models/mlb/moneyline/structured_ml_core.js'));
  const kCore=require(path.join(root,'packages/models/mlb/k/structured_k_core.js'));
  const replay=require(path.join(root,'packages/models/mlb/evaluation/production_replay_adapter_020.js'));

  const outcomes=path.resolve(args.outcomes||defaultPointer(
    root,'data/normalized/mlb/CURRENT_HISTORICAL_OUTCOMES_030','MLB_HISTORICAL_OUTCOMES.jsonl'
  ));
  const priors=path.resolve(args.priors||defaultPointer(
    root,'data/normalized/mlb/CURRENT_POSTSEASON_PRIORS_040','POSTSEASON_PRIORS_MANIFEST.json'
  ));
  const rows=readJsonl(outcomes).filter(x=>String(x.season_type).toUpperCase()==='POST');
  if(!rows.length)throw new Error('no postseason outcomes');
  const priorManifest=readJson(priors);
  if(priorManifest.error_count)throw new Error(`postseason prior manifest has ${priorManifest.error_count} acquisition errors`);

  const seasons=[...new Set(rows.map(x=>Number(x.season)))].sort((a,b)=>a-b);
  const savantBundles={pitcher:{},batter:{}},wrcBundles={},parkBundles={};
  const assetWarnings=[];

  for(const season of seasons){
    for(const type of ['pitcher','batter']){
      const curPath=path.join(root,`data/raw/mlb/historical_priors_040/savant/${season}/${type}.csv`);
      const prevPath=path.join(root,`data/raw/mlb/historical_priors_040/savant/${season-1}/${type}.csv`);
      const cur=savantCore.parseLeaderboard(readText(curPath),type,season);
      let prev=null;
      if(fs.existsSync(prevPath)){
        try{prev=savantCore.parseLeaderboard(readText(prevPath),type,season-1);}
        catch(e){assetWarnings.push(`Savant ${type} ${season-1} previous fallback unavailable: ${e.message}`);}
      }
      savantBundles[type][season]=savantCore.seasonBundle(cur,prev);
    }
    const wc=path.join(root,`data/raw/mlb/historical_priors_040/fangraphs/${season}/wrc.json`);
    const wp=path.join(root,`data/raw/mlb/historical_priors_040/fangraphs/${season-1}/wrc.json`);
    const curW=wrcCore.parseLeaderboard(readJson(wc),season);
    let prevW=null;
    if(fs.existsSync(wp)){
      try{prevW=wrcCore.parseLeaderboard(readJson(wp),season-1);}
      catch(e){assetWarnings.push(`FanGraphs wRC+ ${season-1} fallback unavailable: ${e.message}`);}
    }
    wrcBundles[season]=wrcCore.seasonBundle(curW,prevW);

    const parks=[];
    for(const rolling of [3,2,1]){
      const pp=path.join(root,`data/raw/mlb/historical_priors_040/park/${season}/rolling_${rolling}.html`);
      try{parks.push(parkCore.parseHtml(readText(pp),season,rolling));}
      catch(e){assetWarnings.push(`Park ${season} rolling ${rolling}: ${e.message}`);}
    }
    parkBundles[season]=parkCore.mergeBundles(parks);
  }

  const ledger=[],snapshotRows=[],blocked=[];
  for(const game of rows){
    const season=Number(game.season), snapshotAt=game.game_datetime;
    const awayCode=teamCode(starterCore,game.away),homeCode=teamCode(starterCore,game.home);
    const baseId=String(game.game_id||game.game_pk);
    try{
      if(!snapshotAt||!Number.isFinite(Date.parse(snapshotAt)))throw new Error('missing game_datetime');
      if(!game.venue_name)throw new Error('venue_name missing; reacquire outcomes with 0.3.2+');
      if(!awayCode||!homeCode)throw new Error(`team code unresolved: ${game.away?.name} / ${game.home?.name}`);
      const boxPath=path.join(root,String(game.boxscore_cache_path||''));
      if(!game.boxscore_cache_path||!fs.existsSync(boxPath))throw new Error('postseason boxscore cache missing');
      const box=readJson(boxPath);
      const lus={
        away:historicalStartingLineup(box,'away'),
        home:historicalStartingLineup(box,'home')
      };
      if(lus.away.state!=='OFFICIAL'||lus.home.state!=='OFFICIAL')throw new Error(
        `lineup unresolved away=${lus.away.state} home=${lus.home.state}`
      );

      const priorUsage=loadPriorDayUsage(root,game,bullpenCore);
      const parkResolved=resolvePark(parkCore,parkBundles[season],game.venue_name,homeCode);
      const park=parkResolved.row;
      if(!park)throw new Error(`park factor unresolved: ${game.venue_name} (${homeCode})`);
      const parkConditions=parkCore.conditionLines(park);

      const sideData={};
      for(const side of ['away','home']){
        const team=game[side], oppSide=side==='away'?'home':'away', opp=game[oppSide];
        const code=side==='away'?awayCode:homeCode;
        const st=team.starter||{}, pid=String(st.mlb_id||'');
        if(!pid)throw new Error(`${side} starter id missing`);

        const logPath=path.join(root,`data/raw/mlb/historical_priors_040/mlb/starter_gamelog/${season}/${pid}.json`);
        const gameLog=parsePitchingGameLog(readJson(logPath));
        if(!gameLog.length)throw new Error(`${side} regular-season pitching game log empty: ${pid}`);
        const workload=workloadMarkets(gameLog,snapshotAt);
        const markets=workload.markets;
        const proxyOuts=kCore.blendedCountExpectation(markets['player-pitcher-outs'],16.5,.36,.64);
        if(!Number.isFinite(proxyOuts))throw new Error(`${side} workload proxy unavailable`);
        if(workload.mode==='EMPTY')throw new Error(`${side} no pregame workload history: ${pid}`);

        const mlPitcher=mlCore.structuredSavantRow(
          savantBundles.pitcher[season],pid,savantCore,{minCurrent:30,minPrevious:60}
        );
        const kPitcher=kSkillRow(kCore,savantBundles.pitcher[season],pid);
        if(!mlPitcher||!kPitcher)throw new Error(`${side} starter Savant skill unavailable: ${pid}`);

        const mlLineup=[],kLineup=[];
        for(const h of lus[oppSide].hitters){
          const mr=mlCore.structuredSavantRow(
            savantBundles.batter[season],h.mlbId,savantCore,{minCurrent:20,minPrevious:80}
          );
          const kr=kSkillRow(kCore,savantBundles.batter[season],h.mlbId);
          if(!mr||!kr){
            if(String(h.position||'').toUpperCase()==='P'){
              throw new Error(`${side} historical ruleset mismatch: pitcher batting slot has no production-compatible Savant hitter row: ${h.name} ${h.mlbId}`);
            }
            throw new Error(`${side} opponent Savant hitter unavailable: ${h.name} ${h.mlbId}`);
          }
          const wr=wrcCore.getForSavantRow(wrcBundles[season],h.mlbId,mr);
          if(!wr||!Number.isFinite(num(wr.wrcPlus)))throw new Error(`${side} opponent wRC+ unavailable: ${h.name}`);
          const metrics={...(mr.metrics||{}),'wRC+':Number(wr.wrcPlus)};
          mlLineup.push({...mr,order:h.order,batter:h.name||mr.name,metrics,'wRC+':metrics['wRC+']});
          kLineup.push({...kr,order:h.order,mlbId:String(h.mlbId),name:h.name||kr.name});
        }
        if(mlLineup.length!==9||kLineup.length!==9)throw new Error(`${side} lineup skill coverage not 9/9`);

        const tid=String(team.team_id);
        const statsPath=path.join(root,`data/raw/mlb/historical_priors_040/mlb/team_pitching/${season}/${tid}.json`);
        const rosterPath=path.join(root,`data/raw/mlb/historical_priors_040/mlb/roster/${String(game.game_date).slice(0,10)}/${tid}.json`);
        const pitching=bullpenCore.parseTeamPitchingStats(readJson(statsPath),season);
        const usageKnown=priorUsage.knownTeams.has(tid);
        const used=priorUsage.usedByTeam.get(tid)||new Set();
        const bullpen=bullpenCore.parseRoster(readJson(rosterPath),{
          teamId:tid,teamCode:code,year:season,starterId:pid,usedYesterday:used,
          usageKnown,pitchingStatsById:pitching
        });
        if(bullpen.validation?.status!=='validated')throw new Error(
          `${side} bullpen not validated: ${bullpen.validation?.status} ${bullpen.validation?.reason||''}`
        );

        sideData[side]={
          pid,code,st,markets,gameLog,workloadMode:workload.mode,proxyOuts,mlPitcher,kPitcher,mlLineup,kLineup,bullpen,
          mlCapture:{
            side,team:code,teamId:tid,officialName:st.name,officialMlbId:pid,
            pitcherMetrics:mlPitcher.metrics||{},
            opponentTeamMetrics:mlOpponentMetrics(mlCore,mlLineup),
            lineupStatus:'Official',lineup:mlLineup,
            workload:{
              IP:proxyOuts/3,expectedOuts:proxyOuts,
              source:'historical regular-season starter game-log proxy',
              state:'HISTORY_PROXY',productionEligible:false
            },
            bullpen:bullpen.rows,bullpenValidation:bullpen.validation,
            gameConditions:parkConditions
          }
        };
      }

      const mlGame={
        away:awayCode,home:homeCode,
        starters:{
          [awayCode]:sideData.away.mlCapture,
          [homeCode]:sideData.home.mlCapture
        }
      };
      const mlInput={
        replay_type:'ML',game_id:baseId,game_date:game.game_date,season,season_type:'POST',
        snapshot_at:snapshotAt,selection_team:homeCode,actual_home_win:Number(game.actual_home_win),
        production_input:mlGame,replay_input_mode:'POST_HISTORY_PROXY',
        model_variant:'POST_HISTORY_PROXY',stage:'RESEARCH',thesis:'REG_SEASON_SKILL_HISTORY_WORKLOAD_PROXY'
      };
      const mlOut=replay.replayML(mlInput);
      mlOut.ruleset=rulesetForSeason(season);
      mlOut.away_workload_proxy_source=sideData.away.workloadMode;
      mlOut.home_workload_proxy_source=sideData.home.workloadMode;
      mlOut.park_resolution_method=parkResolved.method;
      ledger.push(mlOut);
      snapshotRows.push({...mlInput,target:'ML_HOME',production_input:undefined});

      for(const side of ['away','home']){
        const d=sideData[side];
        const kStarter={
          officialName:d.st.name,officialMlbId:d.pid,team:d.code,gamePk:baseId,
          markets:d.markets
        };
        const actualK=num(game[side]?.starter?.strikeouts,null);
        if(actualK===null)throw new Error(`${side} actual K missing`);
        const kInput={
          replay_type:'K',evaluation_mode:'XK_ONLY',game_id:baseId,game_date:game.game_date,
          season,season_type:'POST',snapshot_at:snapshotAt,pitcher:d.st.name,team:d.code,
          actual_k:actualK,starter_input:kStarter,lineup_rows:d.kLineup,pitcher_row:d.kPitcher,
          replay_input_mode:'POST_HISTORY_PROXY',model_variant:'POST_HISTORY_PROXY',
          stage:'RESEARCH',thesis:'REG_SEASON_SKILL_HISTORY_WORKLOAD_PROXY'
        };
        const kOut=replay.replayKDistributionOnly(kInput);
        kOut.ruleset=rulesetForSeason(season);
        kOut.workload_proxy_source=d.workloadMode;
        kOut.park_resolution_method=parkResolved.method;
        ledger.push(kOut);
        snapshotRows.push({
          ...kInput,starter_input:undefined,lineup_rows:undefined,pitcher_row:undefined,
          target:`K_XK|${d.pid}`
        });
      }
    }catch(e){
      blocked.push({game_id:baseId,game_date:game.game_date,error:e.message});
    }
  }

  const runId=new Date().toISOString().replace(/[-:.]/g,'')+'_'+crypto.randomBytes(4).toString('hex');
  const outDir=args.output?path.dirname(path.resolve(args.output)):path.join(root,'data/models/mlb/postseason_replay_050',runId);
  const ledgerPath=args.output?path.resolve(args.output):path.join(outDir,'MLB_POSTSEASON_HISTORY_PROXY_LEDGER.jsonl');
  const snapshotsPath=path.join(outDir,'MLB_POSTSEASON_HISTORY_PROXY_SNAPSHOTS.jsonl');
  writeJsonl(ledgerPath,ledger);
  writeJsonl(snapshotsPath,snapshotRows);
  const manifest={
    version:VERSION,lineage:LINEAGE,created_at:new Date().toISOString(),run_id:runId,
    outcomes_path:outcomes,outcomes_sha256:sha256File(outcomes),
    priors_manifest:priors,priors_manifest_sha256:sha256File(priors),
    seasons,postseason_games:rows.length,
    successful_games:ledger.filter(x=>x.market_type==='ML').length,
    ml_rows:ledger.filter(x=>x.market_type==='ML').length,
    k_xk_rows:ledger.filter(x=>x.market_type==='K'&&x.evaluation_mode==='XK_ONLY').length,
    blocked_games:blocked.length,blocked,asset_warnings:assetWarnings,
    replay_input_mode:'POST_HISTORY_PROXY',
    exact_production_replay:false,
    exact_components:[
      'production ML probability formula','production K distribution formula',
      'regular-season-complete Savant skill','regular-season-complete FanGraphs wRC+',
      'season-end park factors','postseason official starting lineup identities',
      'historical active roster','prior-day bullpen usage when resolvable'
    ],
    proxy_components:[
      'starter workload from regular-season game logs',
      'K ER/H/BB/K histories from regular-season game logs'
    ],
    unavailable_components:[
      'historical PropsMadness Pitcher Outs/ER/H/BB current-game lines',
      'historical actionable K line/price','historical K closing price'
    ],
    coverage_status:blocked.length?'PARTIAL_FAIL_CLOSED':'COMPLETE',
    strict_coverage_mode:!!args.strictCoverage,
    production_model_mutation:false,model_refit_performed:false,market_requests:0,oddsPapi_requests:0,
    core_identity:replay.coreIdentity(),
    ledger_path:ledgerPath,ledger_sha256:sha256File(ledgerPath),
    snapshots_path:snapshotsPath,snapshots_sha256:sha256File(snapshotsPath)
  };
  const manifestPath=path.join(outDir,'POSTSEASON_REPLAY_MANIFEST.json');
  fs.mkdirSync(outDir,{recursive:true});
  fs.writeFileSync(manifestPath,JSON.stringify(manifest,null,2)+'\n','utf8');
  const pointer=path.join(root,'data/models/mlb/CURRENT_POSTSEASON_REPLAY_050');
  fs.mkdirSync(path.dirname(pointer),{recursive:true});
  fs.writeFileSync(pointer,path.relative(root,outDir)+'\n','utf8');

  console.log('');
  console.log(`MLB POSTSEASON HISTORY-PROXY REPLAY ${VERSION}`);
  console.log(`Games input: ${rows.length} · successful ML games: ${manifest.successful_games} · blocked: ${blocked.length}`);
  console.log(`Ledger rows: ${ledger.length} · ML ${manifest.ml_rows} · K xK-only ${manifest.k_xk_rows}`);
  console.log('Exact production replay: NO · workload proxy clearly labeled');
  console.log('Historical K market fabricated: NO');
  console.log(`Coverage: ${blocked.length?'PARTIAL FAIL-CLOSED':'COMPLETE'} · strict coverage: ${args.strictCoverage?'YES':'NO'}`);
  console.log('Production mutation: NO · refit: NO · OddsPapi: 0');
  if(blocked.length)blocked.slice(0,20).forEach(x=>console.log(`BLOCKED ${x.game_date} ${x.game_id}: ${x.error}`));
  console.log(`Ledger: ${ledgerPath}`);
  console.log(`Manifest: ${manifestPath}`);
  process.exitCode=(args.strictCoverage&&blocked.length)?1:0;
}

if(require.main===module)main();
module.exports={
  VERSION,LINEAGE,TEAM_ID_CODE,TEAM_CODE_NICKNAME,HISTORICAL_VENUE_ALIASES,mean,num,ipToOuts,priorDate,
  parsePitchingGameLog,selectWorkloadHistory,historyMarket,workloadMarkets,kSkillRow,
  mlOpponentMetrics,teamCode,rulesetForSeason,normalizeLabel,resolvePark,historicalStartingLineup
};

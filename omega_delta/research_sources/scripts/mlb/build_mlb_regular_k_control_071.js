#!/usr/bin/env node
'use strict';

const fs=require('fs');
const path=require('path');
const crypto=require('crypto');

const VERSION='0.7.1';
const LINEAGE='mlb-late-regular-k-control-replay-v0.7.1-2026-09-19';

const SWING_DESCRIPTIONS=new Set([
  'swinging_strike','swinging_strike_blocked','foul','foul_tip','hit_into_play',
  'foul_bunt','missed_bunt','bunt_foul_tip'
]);
const WHIFF_DESCRIPTIONS=new Set([
  'swinging_strike','swinging_strike_blocked','missed_bunt'
]);
const NO_PA_EVENTS=new Set([
  'caught_stealing_2b','caught_stealing_3b','caught_stealing_home',
  'pickoff_1b','pickoff_2b','pickoff_3b','pickoff_caught_stealing_2b',
  'pickoff_caught_stealing_3b','pickoff_caught_stealing_home',
  'runner_double_play'
]);
const K_EVENTS=new Set(['strikeout','strikeout_double_play']);
const BB_EVENTS=new Set(['walk','intent_walk']);

function num(v,f=null){
  if(v===null||v===undefined||v==='')return f;
  const n=Number(String(v).replace(/%/g,'').trim());
  return Number.isFinite(n)?n:f;
}
function clamp(v,a,b){return Math.max(a,Math.min(b,v));}
function sha256File(p){const h=crypto.createHash('sha256');h.update(fs.readFileSync(p));return h.digest('hex');}
function readJson(p){return JSON.parse(fs.readFileSync(p,'utf8'));}
function readJsonl(p){return fs.readFileSync(p,'utf8').split(/\r?\n/).filter(x=>x.trim()).map(JSON.parse);}
function writeJsonl(p,rows){
  fs.mkdirSync(path.dirname(p),{recursive:true});
  const tmp=path.join(path.dirname(p),'.'+path.basename(p)+'.tmp');
  fs.writeFileSync(tmp,rows.map(x=>JSON.stringify(x)).join('\n')+'\n','utf8');
  fs.renameSync(tmp,p);
}
function pointerFile(root,rel,leaf){
  const p=path.join(root,rel);
  if(!fs.existsSync(p))throw new Error(`missing pointer ${p}`);
  const dir=path.join(root,fs.readFileSync(p,'utf8').trim());
  const out=path.join(dir,leaf);
  if(!fs.existsSync(out))throw new Error(`missing pointed file ${out}`);
  return out;
}
function normHeader(s){return String(s||'').replace(/^\uFEFF/,'').trim().toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');}

function parseCsvObjects(savantCore,text){
  const rows=savantCore.parseCsv(text);
  if(rows.length<2)return [];
  const h=rows[0].map(normHeader);
  return rows.slice(1).map(vals=>{
    const o={};h.forEach((k,i)=>o[k]=vals[i]??'');return o;
  });
}
function first(o,keys){
  for(const k of keys)if(o&&Object.prototype.hasOwnProperty.call(o,k)&&o[k]!==''&&o[k]!=null)return o[k];
  return null;
}
function reconRowsById(savantCore,text){
  const out=new Map();
  for(const o of parseCsvObjects(savantCore,text)){
    const id=String(first(o,['player_id','playerid'])||'').trim();
    if(!id)continue;
    const pa=num(first(o,['pa','b_total_pa','p_total_pa','bf','batters_faced']),0);
    const row={
      playerId:id,
      name:String(first(o,['last_name_first_name','player_name','name'])||'').trim()||null,
      pa,
      strikeouts:num(first(o,['strikeout','so']), pa*num(first(o,['k_percent']),0)/100),
      walks:num(first(o,['walk','bb']), pa*num(first(o,['bb_percent']),0)/100),
      kPct:num(first(o,['k_percent'])),
      bbPct:num(first(o,['bb_percent'])),
      pitchCount:num(first(o,['pitch_count','pitches'])),
      inZoneSwing:num(first(o,['in_zone_swing'])),
      outZoneSwing:num(first(o,['out_zone_swing'])),
      inZoneMiss:num(first(o,['in_zone_swing_miss'])),
      outZoneMiss:num(first(o,['out_zone_swing_miss'])),
      swingPct:num(first(o,['swing_percent'])),
      whiffPct:num(first(o,['whiff_percent'])),
    };
    row.swings=(Number.isFinite(row.inZoneSwing)&&Number.isFinite(row.outZoneSwing))
      ? row.inZoneSwing+row.outZoneSwing
      : (Number.isFinite(row.pitchCount)&&Number.isFinite(row.swingPct)?row.pitchCount*row.swingPct/100:null);
    row.whiffs=(Number.isFinite(row.inZoneMiss)&&Number.isFinite(row.outZoneMiss))
      ? row.inZoneMiss+row.outZoneMiss
      : (Number.isFinite(row.swings)&&Number.isFinite(row.whiffPct)?row.swings*row.whiffPct/100:null);
    const prior=out.get(id);
    if(!prior||row.pa>prior.pa)out.set(id,row);
  }
  return out;
}
function rawRows(savantCore,text){
  return parseCsvObjects(savantCore,text).map(o=>({
    gamePk:String(first(o,['game_pk'])||''),
    gameDate:String(first(o,['game_date'])||'').slice(0,10),
    pitcher:String(first(o,['pitcher'])||''),
    batter:String(first(o,['batter'])||''),
    atBat:String(first(o,['at_bat_number'])||''),
    description:String(first(o,['description'])||'').toLowerCase(),
    event:String(first(o,['events'])||'').toLowerCase(),
  })).filter(x=>x.gamePk&&x.pitcher&&x.batter);
}
function futureContribution(rows,playerId,role,snapshotMs,startByPk){
  let pitches=0,swings=0,whiffs=0,k=0,bb=0;
  const pas=new Set(),games=new Set();
  for(const r of rows){
    const id=role==='pitcher'?r.pitcher:r.batter;
    if(String(id)!==String(playerId))continue;
    const start=startByPk.get(String(r.gamePk));
    if(!Number.isFinite(start)||start<snapshotMs)continue;
    pitches++;games.add(String(r.gamePk));
    if(SWING_DESCRIPTIONS.has(r.description))swings++;
    if(WHIFF_DESCRIPTIONS.has(r.description))whiffs++;
    if(r.event&&!NO_PA_EVENTS.has(r.event)){
      pas.add(`${r.gamePk}|${r.atBat}`);
      if(K_EVENTS.has(r.event))k++;
      if(BB_EVENTS.has(r.event))bb++;
    }
  }
  return {pa:pas.size,strikeouts:k,walks:bb,pitches,swings,whiffs,games:games.size};
}
function fullSkill(row){
  if(!row)return null;
  const pa=Math.max(0,num(row.pa,0));
  const kPct=Number.isFinite(num(row.kPct))?num(row.kPct):(pa>0?100*num(row.strikeouts,0)/pa:null);
  const bbPct=Number.isFinite(num(row.bbPct))?num(row.bbPct):(pa>0?100*num(row.walks,0)/pa:null);
  const swingPct=Number.isFinite(num(row.swingPct))?num(row.swingPct):
    (num(row.pitchCount,0)>0?100*num(row.swings,0)/num(row.pitchCount):null);
  const whiffPct=Number.isFinite(num(row.whiffPct))?num(row.whiffPct):
    (num(row.swings,0)>0?100*num(row.whiffs,0)/num(row.swings):null);
  if(![kPct,swingPct,whiffPct].every(Number.isFinite))return null;
  return {
    playerId:row.playerId,name:row.name,pa,
    K:kPct,BB:bbPct,
    Whiff:whiffPct,Swing:swingPct,SwStr:swingPct*whiffPct/100,Contact:100-whiffPct
  };
}
function reconstructSkill(row,future){
  if(!row)return {row:null,warnings:['full-season row missing']};
  const warnings=[];
  const full={
    pa:num(row.pa,0),strikeouts:num(row.strikeouts,0),walks:num(row.walks,0),
    pitches:num(row.pitchCount,0),swings:num(row.swings,0),whiffs:num(row.whiffs,0)
  };
  const pre={};
  for(const k of Object.keys(full)){
    const fv=k==='pitches'?future.pitches:k==='swings'?future.swings:k==='whiffs'?future.whiffs:
      k==='strikeouts'?future.strikeouts:k==='walks'?future.walks:future.pa;
    pre[k]=full[k]-num(fv,0);
    if(pre[k]<-1.5)warnings.push(`${k} reconstruction negative (${pre[k].toFixed(2)})`);
    pre[k]=Math.max(0,pre[k]);
  }
  if(pre.pa<=0||pre.pitches<=0||pre.swings<=0)return {row:null,warnings:[...warnings,'pregame sample has no usable PA/pitches/swings']};
  const K=100*pre.strikeouts/pre.pa;
  const BB=100*pre.walks/pre.pa;
  const Swing=100*pre.swings/pre.pitches;
  const Whiff=100*pre.whiffs/pre.swings;
  const rowOut={
    playerId:row.playerId,name:row.name,pa:pre.pa,
    K:clamp(K,0,70),BB:clamp(BB,0,50),
    Whiff:clamp(Whiff,0,75),Swing:clamp(Swing,0,85),
    SwStr:clamp(Swing*Whiff/100,0,40),Contact:clamp(100-Whiff,25,100),
    reconstructionCounts:pre,futureRemoved:future
  };
  return {row:rowOut,warnings};
}
function chooseSkill(current,previous,{minCurrent,minPrevious}){
  const cur=current?.row||null,prev=fullSkill(previous);
  const warnings=[...(current?.warnings||[])];
  if(cur&&num(cur.pa,0)>=minCurrent){
    return {...cur,sourceSeason:'current',sampleCurrent:num(cur.pa,0),samplePrevious:num(prev?.pa,0),
      previousK:num(prev?.K),previousWhiff:num(prev?.Whiff),previousSwStr:num(prev?.SwStr),previousContact:num(prev?.Contact),
      reconstructionWarnings:warnings};
  }
  if(prev&&num(prev.pa,0)>=minPrevious){
    return {...prev,sourceSeason:'previous',sampleCurrent:num(cur?.pa,0),samplePrevious:num(prev.pa,0),
      reconstructionWarnings:[...warnings,'prior-season fallback used']};
  }
  if(cur){
    return {...cur,sourceSeason:'current-small',sampleCurrent:num(cur.pa,0),samplePrevious:num(prev?.pa,0),
      previousK:num(prev?.K),previousWhiff:num(prev?.Whiff),previousSwStr:num(prev?.SwStr),previousContact:num(prev?.Contact),
      reconstructionWarnings:warnings};
  }
  if(prev){
    return {...prev,sourceSeason:'previous-small',sampleCurrent:0,samplePrevious:num(prev.pa,0),
      reconstructionWarnings:[...warnings,'small prior-season fallback used']};
  }
  return null;
}
function priorWorkloadMarkets(history,snapshotMs,startByPk,postBuilder,snapshotAt){
  const prior=(history||[]).filter(x=>{
    const t=startByPk.get(String(x.gamePk||''));
    if(Number.isFinite(t))return t<snapshotMs;
    return String(x.date||'')<String(snapshotAt).slice(0,10);
  });
  const starts=prior.filter(x=>Number(x.gamesStarted)>=1);
  const logs=starts.length?starts:prior;
  const mode=starts.length?'REGULAR_SEASON_STARTS':'REGULAR_SEASON_APPEARANCES_OPENER_FALLBACK';
  const mk=vals=>postBuilder.historyMarket(vals,snapshotAt);
  return {mode,logs,markets:{
    'player-strikeouts':mk(logs.map(x=>x.k)),
    'player-pitcher-outs':mk(logs.map(x=>x.outs)),
    'player-earned-runs':mk(logs.map(x=>x.er)),
    'player-hits-allowed':mk(logs.map(x=>x.hits)),
    'player-walks':mk(logs.map(x=>x.bb)),
  }};
}
function parseArgs(argv){
  const a={root:'/Users/abbeyfelix/Developer/MODEL',control:null,output:null};
  for(let i=2;i<argv.length;i++){
    const x=argv[i];
    if(x==='--root')a.root=argv[++i];
    else if(x==='--control')a.control=argv[++i];
    else if(x==='--output')a.output=argv[++i];
    else throw new Error(`unknown argument ${x}`);
  }
  return a;
}
function rulesetForSeason(y){y=Number(y);return y===2020||y>=2022?'UNIVERSAL_DH':'PRE_UNIVERSAL_DH';}

function main(){
  const args=parseArgs(process.argv),root=path.resolve(args.root);
  const savantCore=require(path.join(root,'packages/providers/baseball_savant/src/savant_core.js'));
  const starterCore=require(path.join(root,'packages/providers/mlb_official/src/starter_core.js'));
  const postBuilder=require(path.join(root,'scripts/mlb/build_mlb_postseason_replay_050.js'));
  const replay=require(path.join(root,'packages/models/mlb/evaluation/production_replay_adapter_020.js'));

  const control=args.control?path.resolve(args.control):pointerFile(
    root,'data/normalized/mlb/CURRENT_REGULAR_CONTROL_070','MLB_REGULAR_CONTROL_TARGETS.jsonl'
  );
  const controlDir=path.dirname(control);
  const manifestPath=path.join(controlDir,'REGULAR_CONTROL_MANIFEST.json');
  const schedulePath=path.join(controlDir,'REGULAR_SCHEDULE_INDEX.json');
  const manifest=readJson(manifestPath);
  if(manifest.error_count)throw new Error(`control acquisition has ${manifest.error_count} errors`);
  const targets=readJsonl(control);
  const sched=readJson(schedulePath);
  const seasons=[...new Set(targets.map(x=>Number(x.season)))].sort((a,b)=>a-b);

  const startByPk=new Map();
  for(const arr of Object.values(sched))for(const g of arr||[]){
    const t=Date.parse(g.game_datetime||'');if(Number.isFinite(t))startByPk.set(String(g.game_pk),t);
  }

  const recon={pitcher:{},batter:{}},raw={};
  for(const season of seasons){
    for(const type of ['pitcher','batter']){
      const cur=path.join(root,`data/raw/mlb/regular_control_070/savant_recon/${season}/${type}.csv`);
      const prev=path.join(root,`data/raw/mlb/regular_control_070/savant_recon/${season-1}/${type}.csv`);
      recon[type][season]={
        current:reconRowsById(savantCore,fs.readFileSync(cur,'utf8')),
        previous:fs.existsSync(prev)?reconRowsById(savantCore,fs.readFileSync(prev,'utf8')):new Map()
      };
    }
    raw[season]=[];
    const days=[...new Set(targets.filter(x=>Number(x.season)===season).map(x=>x.game_date))].sort();
    // Acquisition fetched every day in the final window, not only target dates.
    const statDir=path.join(root,`data/raw/mlb/regular_control_070/statcast_day/${season}`);
    if(!fs.existsSync(statDir))throw new Error(`missing Statcast day directory ${statDir}`);
    for(const name of fs.readdirSync(statDir).filter(x=>x.endsWith('.csv')).sort()){
      raw[season].push(...rawRows(savantCore,fs.readFileSync(path.join(statDir,name),'utf8')));
    }
  }

  const ledger=[],blocked=[];
  for(const game of targets){
    const season=Number(game.season),snapshotAt=game.game_datetime,snapshotMs=Date.parse(snapshotAt||'');
    try{
      if(!Number.isFinite(snapshotMs))throw new Error('game_datetime missing');
      const bp=path.join(root,String(game.boxscore_cache_path||''));
      if(!fs.existsSync(bp))throw new Error('control boxscore missing');
      const box=readJson(bp);
      const lineups={
        away:postBuilder.historicalStartingLineup(box,'away'),
        home:postBuilder.historicalStartingLineup(box,'home')
      };
      if(lineups.away.state!=='OFFICIAL'||lineups.home.state!=='OFFICIAL'){
        throw new Error(`historical lineup unresolved away=${lineups.away.state} home=${lineups.home.state}`);
      }

      for(const side of ['away','home']){
        const oppSide=side==='away'?'home':'away';
        const st=game[side]?.starter||{},pid=String(st.mlb_id||'');
        if(!pid)throw new Error(`${side} starter id missing`);

        const curPitch=recon.pitcher[season].current.get(pid)||null;
        const prevPitch=recon.pitcher[season].previous.get(pid)||null;
        const pf=futureContribution(raw[season],pid,'pitcher',snapshotMs,startByPk);
        const pitcher=chooseSkill(reconstructSkill(curPitch,pf),prevPitch,{minCurrent:30,minPrevious:60});
        if(!pitcher)throw new Error(`${side} pitcher pregame skill unavailable: ${pid}`);

        const lineup=[];
        for(const h of lineups[oppSide].hitters){
          const hid=String(h.mlbId);
          const cur=recon.batter[season].current.get(hid)||null;
          const prev=recon.batter[season].previous.get(hid)||null;
          const future=futureContribution(raw[season],hid,'batter',snapshotMs,startByPk);
          const skill=chooseSkill(reconstructSkill(cur,future),prev,{minCurrent:20,minPrevious:80});
          if(!skill){
            if(String(h.position||'').toUpperCase()==='P'){
              throw new Error(`${side} historical ruleset mismatch: pitcher batting slot pregame skill unavailable: ${h.name} ${hid}`);
            }
            throw new Error(`${side} opponent pregame skill unavailable: ${h.name} ${hid}`);
          }
          lineup.push({...skill,order:h.order,mlbId:hid,name:h.name||skill.name});
        }
        if(lineup.length!==9)throw new Error(`${side} lineup skill coverage ${lineup.length}/9`);

        const gp=path.join(root,`data/raw/mlb/regular_control_070/mlb/starter_gamelog/${season}/${pid}.json`);
        if(!fs.existsSync(gp))throw new Error(`${side} starter game log missing`);
        const hist=postBuilder.parsePitchingGameLog(readJson(gp));
        const workload=priorWorkloadMarkets(hist,snapshotMs,startByPk,postBuilder,snapshotAt);
        if(!workload.logs.length)throw new Error(`${side} no prior workload history`);

        const starter={
          officialName:st.name,officialMlbId:pid,
          team:starterCore.teamCode(game[side]?.name)||postBuilder.TEAM_ID_CODE[String(game[side]?.team_id)]||null,
          gamePk:String(game.game_pk),markets:workload.markets
        };
        const actualK=num(st.strikeouts,null);
        if(actualK===null)throw new Error(`${side} actual K missing`);
        const input={
          replay_type:'K',evaluation_mode:'XK_ONLY',game_id:String(game.game_id),game_date:game.game_date,
          season,season_type:'REG',snapshot_at:snapshotAt,pitcher:st.name,team:starter.team,
          actual_k:actualK,starter_input:starter,lineup_rows:lineup,pitcher_row:pitcher,
          replay_input_mode:'REG_LATE_HISTORY_PROXY',model_variant:'REG_LATE_HISTORY_PROXY',
          stage:'RESEARCH',thesis:'PREGAME_RECONSTRUCTED_SKILL_HISTORY_WORKLOAD_PROXY'
        };
        const out=replay.replayKDistributionOnly(input);
        out.ruleset=rulesetForSeason(season);
        out.workload_proxy_source=workload.mode;
        out.control_match_quality=game.control_match_quality;
        out.control_cohort=game.control_cohort;
        out.days_to_regular_season_end=game.days_to_regular_season_end;
        out.pregame_skill_reconstruction='FULL_SEASON_MINUS_TARGET_AND_FUTURE_STATCAST';
        out.pitcher_future_removed=pf;
        out.pitcher_reconstruction_warnings=pitcher.reconstructionWarnings||[];
        ledger.push(out);
      }
    }catch(e){
      blocked.push({game_id:String(game.game_id),game_date:game.game_date,error:e.message});
    }
  }

  const runId=new Date().toISOString().replace(/[-:.]/g,'')+'_'+crypto.randomBytes(4).toString('hex');
  const outDir=args.output?path.dirname(path.resolve(args.output)):path.join(root,'data/models/mlb/regular_control_k_071',runId);
  const ledgerPath=args.output?path.resolve(args.output):path.join(outDir,'MLB_REGULAR_CONTROL_K_LEDGER.jsonl');
  writeJsonl(ledgerPath,ledger);
  fs.mkdirSync(outDir,{recursive:true});
  const mp=path.join(outDir,'REGULAR_CONTROL_K_REPLAY_MANIFEST.json');
  const outManifest={
    version:VERSION,lineage:LINEAGE,created_at:new Date().toISOString(),run_id:runId,
    control_targets:control,control_targets_sha256:sha256File(control),
    acquisition_manifest:manifestPath,acquisition_manifest_sha256:sha256File(manifestPath),
    seasons,target_games:targets.length,k_rows:ledger.length,successful_games:new Set(ledger.map(x=>x.game_id)).size,
    blocked_games:blocked.length,blocked,
    reconstruction:'full-season Savant aggregate minus target-and-future pitch-level Statcast in final control window',
    target_game_removed_from_skill:true,future_games_removed_from_skill:true,
    workload:'same pregame prior-start/history proxy semantics as postseason replay',
    historical_k_market:'NOT_ACQUIRED',evaluation_mode:'XK_ONLY',
    production_model_mutation:false,model_refit_performed:false,market_requests:0,oddsPapi_requests:0,
    core_identity:replay.coreIdentity(),ledger_path:ledgerPath,ledger_sha256:sha256File(ledgerPath)
  };
  fs.writeFileSync(mp,JSON.stringify(outManifest,null,2)+'\n','utf8');
  const ptr=path.join(root,'data/models/mlb/CURRENT_REGULAR_CONTROL_K_071');
  fs.mkdirSync(path.dirname(ptr),{recursive:true});
  fs.writeFileSync(ptr,path.relative(root,outDir)+'\n','utf8');

  console.log('');
  console.log(`MLB LATE REGULAR K CONTROL REPLAY ${VERSION}`);
  console.log(`Target games: ${targets.length} · successful games: ${outManifest.successful_games} · blocked: ${blocked.length}`);
  console.log(`K xK-only rows: ${ledger.length}`);
  console.log('Pregame skill: full-season aggregate MINUS target/future Statcast');
  console.log('Historical K market fabricated: NO');
  console.log('Production mutation: NO · refit: NO · OddsPapi: 0');
  blocked.slice(0,25).forEach(x=>console.log(`BLOCKED ${x.game_date} ${x.game_id}: ${x.error}`));
  console.log(`Ledger: ${ledgerPath}`);
  console.log(`Manifest: ${mp}`);
  process.exitCode=0;
}
if(require.main===module)main();

module.exports={
  VERSION,SWING_DESCRIPTIONS,WHIFF_DESCRIPTIONS,NO_PA_EVENTS,K_EVENTS,BB_EVENTS,
  reconRowsById,rawRows,futureContribution,fullSkill,reconstructSkill,chooseSkill,
  priorWorkloadMarkets,rulesetForSeason
};


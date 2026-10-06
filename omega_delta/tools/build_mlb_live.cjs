// Assemble pregame features from receipted public assets. Never reads outcomes.
const fs=require('node:fs');
const h=require('../research_sources/scripts/mlb/build_mlb_postseason_replay_050.js');
const ml=require('../models/mlb/moneyline/structured_ml_core.js');
const k=require('../models/mlb/k/structured_k_core.js');
const sav=require('../research_sources/packages/providers/baseball_savant/src/savant_core.js');
const park=require('../research_sources/packages/providers/baseball_savant/src/park_factor_core.js');
const wrc=require('../research_sources/packages/providers/fangraphs/src/wrc_core.js');
const bp=require('../research_sources/packages/providers/mlb_official/src/bullpen_core.js');
const x=JSON.parse(fs.readFileSync(0,'utf8')),year=x.season;
const bundles={};
for(const type of ['pitcher','batter'])bundles[type]=sav.seasonBundle(sav.parseLeaderboard(x.assets[`savant_${type}`],type,year),sav.parseLeaderboard(x.assets[`previous_${type}`],type,year-1));
const wb=wrc.seasonBundle(wrc.parseLeaderboard(x.assets.wrc,year),wrc.parseLeaderboard(x.assets.previous_wrc,year-1));
const parks=park.mergeBundles([3,2,1].map(r=>park.parseHtml(x.assets['park_'+r],year,r)));
const results=[];
for(const g of x.games){
  try{
    if(!['P','S'].includes(g.abstract_state))throw Error('Game is not pregame');
    if(Date.parse(g.start_at)<=Date.parse(x.captured_at))throw Error('First pitch has passed');
    const lu={away:h.historicalStartingLineup(g.box,'away'),home:h.historicalStartingLineup(g.box,'home')};
    if(lu.away.state!=='OFFICIAL'||lu.home.state!=='OFFICIAL')throw Error('Waiting for both official nine-player batting orders');
    const pp=h.resolvePark(park,parks,g.venue,g.home.code).row;
    if(!pp)throw Error('Park factor unresolved');
    const usage=bp.parseYesterdayUsage(g.previous_schedule,g.previous_boxes,[String(g.away.id),String(g.home.id)]);
    const captures={},kin=[],workloads={};
    for(const side of ['away','home']){
      const t=g[side],opp=side==='away'?'home':'away',pid=String(t.pitcher_id||'');
      if(!pid)throw Error('Probable starter missing for '+t.code);
      const history=h.workloadMarkets(h.parsePitchingGameLog(t.log),g.start_at);
      if(history.mode==='EMPTY')throw Error('No regular-season workload history for '+t.pitcher_name);
      const pm=ml.structuredSavantRow(bundles.pitcher,pid,sav,{minCurrent:30,minPrevious:60});
      const pk=h.kSkillRow(k,bundles.pitcher,pid);
      if(!pm||!pk)throw Error('Starter skill data unavailable');
      const mlrows=[],krows=[];
      for(const b of lu[opp].hitters){
        const mr=ml.structuredSavantRow(bundles.batter,b.mlbId,sav,{minCurrent:20,minPrevious:80});
        const kr=h.kSkillRow(k,bundles.batter,b.mlbId);
        const wr=mr?wrc.getForSavantRow(wb,b.mlbId,mr):null;
        if(!mr||!kr||!wr||!Number.isFinite(Number(wr.wrcPlus)))throw Error('Lineup skill unavailable for '+b.name);
        mlrows.push({...mr,order:b.order,batter:b.name,metrics:{...mr.metrics,'wRC+':Number(wr.wrcPlus)},'wRC+':Number(wr.wrcPlus)});
        krows.push({...kr,order:b.order,mlbId:String(b.mlbId),name:b.name});
      }
      const bullpen=bp.parseRoster(t.roster,{teamId:String(t.id),teamCode:t.code,year,starterId:pid,usedYesterday:usage.usedByTeam.get(String(t.id))||new Set(),usageKnown:usage.knownTeams.has(String(t.id)),pitchingStatsById:bp.parseTeamPitchingStats(t.stats,year)});
      if(bullpen.validation?.status!=='validated')throw Error('Bullpen data incomplete for '+t.code);
      const outs=k.blendedCountExpectation(history.markets['player-pitcher-outs'],16.5,.36,.64);
      workloads[side]={IP:outs/3,expectedOuts:outs,state:'HISTORY_PROXY',regular_starts:history.mode==='REGULAR_SEASON_STARTS'};
      captures[t.code]={team:t.code,officialName:t.pitcher_name,officialMlbId:pid,pitcherMetrics:pm.metrics,opponentTeamMetrics:h.mlOpponentMetrics(ml,mlrows),lineupStatus:'Official',lineup:mlrows,workload:workloads[side],bullpen:bullpen.rows,bullpenValidation:bullpen.validation,gameConditions:park.conditionLines(pp)};
      kin.push({replay_type:'K',game_id:g.game_id,snapshot_at:x.captured_at,starter_input:{officialName:t.pitcher_name,officialMlbId:pid,team:t.code,gamePk:g.game_id,markets:history.markets},lineup_rows:krows,pitcher_row:pk,workload_mode:'HISTORY_PROXY',regular_starts:workloads[side].regular_starts});
    }
    results.push({game_id:g.game_id,start_at:g.start_at,away:g.away.code,home:g.home.code,status:'READY_RESEARCH',workloads,
                  inputs:[{replay_type:'ML',game_id:g.game_id,snapshot_at:x.captured_at,production_input:{away:g.away.code,home:g.home.code,starters:captures}},...kin]});
  }catch(e){results.push({game_id:g.game_id,start_at:g.start_at,away:g.away.code,home:g.home.code,status:'BLOCKED',reason:e.message});}
}
process.stdout.write(JSON.stringify(results));

const assert=require('assert');
const radar=require('../../../packages/core/src/slate_radar/radar_core.js');
const mlCore=require('../../../packages/models/mlb/moneyline/structured_ml_core.js');
const kCore=require('../../../packages/models/mlb/k/structured_k_core.js');
const wrcCore=require('../../../packages/providers/fangraphs/src/wrc_core.js');

const now=Date.parse('2026-09-07T16:00:00Z');
const iso=new Date(now-2*60000).toISOString();
const market=(line,avg,l30,over=-110,under=-110)=>({state:'PRICED',observedAt:iso,representative:{line,overOdds:over,underOdds:under,sportsbook:'RadarTest',capturedAt:iso},statistics:{overall:{season:{average:avg},l30}}});
const starter=(team,opp,id,name)=>({team,opponent:opp,officialName:name,officialMlbId:String(id),identityState:'VERIFIED',markets:{
  'player-strikeouts':market(4.5,5.1,[4,5,6,5,7,4],-105,-115),
  'player-pitcher-outs':market(16.5,17,[17,18,16,17,18]),
  'player-earned-runs':market(2.5,2.4,[2,3,1,4,2]),
  'player-hits-allowed':market(5.5,5.2,[5,6,4,5,6]),
  'player-walks':market(1.5,1.8,[2,1,2,2,1])
}});
const game={gamePk:'9001',away:'AAA',home:'BBB',awayTeamId:'1',homeTeamId:'2',venueName:'Test Park',startAt:'2026-09-07T22:00:00Z',pregame:true,state:'VERIFIED',starters:{away:starter('AAA','BBB',101,'Away Arm'),home:starter('BBB','AAA',201,'Home Arm')}};
const missingStarter={gamePk:'9002',away:'CCC',home:'DDD',awayTeamId:'3',homeTeamId:'4',venueName:'Test Park',startAt:'2026-09-07T23:00:00Z',pregame:true,state:'BLOCKED',starters:{away:{identityState:'NOT_FOUND',team:'CCC'},home:{identityState:'NOT_FOUND',team:'DDD'}}};
const noMarketStarter=starter('AAA','BBB',101,'Away Arm');
noMarketStarter.markets['player-strikeouts']={...noMarketStarter.markets['player-strikeouts'],representative:{...noMarketStarter.markets['player-strikeouts'].representative,line:null,overOdds:null,underOdds:null},offers:[]};
const noMarketGame={...game,gamePk:'9003',startAt:'2026-09-08T00:00:00Z',starters:{away:noMarketStarter,home:starter('BBB','AAA',201,'Home Arm')}};
const starterBoard={games:[game,missingStarter,noMarketGame]};

const pitcherRows=new Map([
 ['101',{playerId:'101',name:'Away Arm',pa:500,kPct:25,bbPct:7,whiffPct:29,contactPct:71,swStrPct:13,ba:.235,xba:.238,xslg:.385,xwoba:.305,iso:.150,hardHitPct:36,barrelPct:7}],
 ['201',{playerId:'201',name:'Home Arm',pa:520,kPct:23,bbPct:8,whiffPct:27,contactPct:73,swStrPct:12,ba:.242,xba:.244,xslg:.398,xwoba:.316,iso:.160,hardHitPct:38,barrelPct:8}]
]);
const batterRows=new Map();
const wrcRows=new Map();
function addTeam(startId,teamBias){
  for(let i=0;i<10;i++){
    const id=String(startId+i),pa=500-i*20;
    batterRows.set(id,{playerId:id,name:`H${id}`,pa,kPct:20+teamBias+i*.15,bbPct:8.5,whiffPct:24+teamBias*.2,contactPct:76-teamBias*.2,swStrPct:11.0+teamBias*.1,ba:.250+teamBias*.002,xba:.248+teamBias*.002,xslg:.410+teamBias*.006,xwoba:.325+teamBias*.004,iso:.175+teamBias*.004,hardHitPct:40+teamBias,barrelPct:8.5+teamBias*.2});
    wrcRows.set(id,{playerId:id,name:`H${id}`,year:2026,pa,wrcPlus:100+teamBias*5});
  }
}
addTeam(1000,1); addTeam(2000,-1);
const pitcherSavant={current:{byId:pitcherRows},previous:{byId:new Map()}};
const batterSavant={current:{byId:batterRows},previous:{byId:new Map()}};
const savantCore={getRow(bundle,id){const r=bundle?.current?.byId?.get(String(id))||bundle?.previous?.byId?.get(String(id));return r?{...r,sourceSeason:'current'}:null;}};
const wrcBundle={currentYear:2026,previousYear:2025,current:{byId:wrcRows},previous:{byId:new Map()}};
const roster=(startId)=>({roster:Array.from({length:10},(_,i)=>({person:{id:startId+i,fullName:`H${startId+i}`},position:{type:'Infielder',abbreviation:'IF'}}))});
const rostersByTeam=new Map([['1',roster(1000)],['2',roster(2000)]]);
const bpRows=[1,2,3,4,5].map(i=>({ERA:3.8+i*.05,WHIP:1.20,K:24,BB:8,rest:'1+'}));
const bullpensByTeam=new Map([['9001:away',{rows:bpRows,validation:{status:'validated'}}],['9001:home',{rows:bpRows,validation:{status:'validated'}}],['9003:away',{rows:bpRows,validation:{status:'validated'}}],['9003:home',{rows:bpRows,validation:{status:'validated'}}]]);
const parkBundle={};
const parkCore={getForVenue(){return{provider:'test',venue:'Test Park',runFactor:1,runIndex:100};},conditionLines(){return['Runs +0%'];}};
const lineupsByPk=new Map([['9001',{away:{state:'PENDING',hitters:[]},home:{state:'PENDING',hitters:[]}}],['9002',{away:{state:'PENDING',hitters:[]},home:{state:'PENDING',hitters:[]}}],['9003',{away:{state:'PENDING',hitters:[]},home:{state:'PENDING',hitters:[]}}]]);
const mlBoard={games:[{gamePk:'9001',status:'BLOCKED',projectionEligible:false,reasons:['official lineup unavailable']},{gamePk:'9003',status:'BLOCKED',projectionEligible:false,reasons:['official lineup unavailable']}]};
const kBoard={games:[{gamePk:'9001',starters:[{side:'away',status:'BLOCKED',reasons:['official lineup unavailable']},{side:'home',status:'BLOCKED',reasons:['official lineup unavailable']}]},{gamePk:'9003',starters:[{side:'away',status:'BLOCKED',reasons:['official lineup unavailable']},{side:'home',status:'BLOCKED',reasons:['official lineup unavailable']}]}]};

const recentSchedule={dates:Array.from({length:8},(_,i)=>({date:`2026-08-${String(20+i).padStart(2,'0')}`,games:[{officialDate:`2026-08-${String(20+i).padStart(2,'0')}`,status:{abstractGameState:'Final'},teams:{away:{team:{id:1},score:5+i%2},home:{team:{id:2},score:2}}}]}))};
const hot=radar.recentResultsProfile('1',recentSchedule);
assert.equal(hot.label,'HOT');
assert.equal(hot.games,8);

const board=radar.buildBoard({starterBoard,lineupsByPk,pitcherSavant,batterSavant,savantCore,wrcBundle,wrcCore,rostersByTeam,bullpensByTeam,parkBundle,parkCore,mlCore,kCore,mlBoard,kBoard,recentSchedule,nowMs:now});
assert.equal(board.version,'1.7');
assert.equal(board.researchVersion,'RCE-0.5');
assert.equal(board.probabilityMutationFromResearch,false);
assert.equal(board.mode,'PRELINEUP_ACTIVE_ROSTER_PROXY');
assert.equal(board.actionable,false);
assert.equal(board.oddsPapiRequests,0);
const ml=board.ml.find(x=>x.gamePk==='9001');
assert.equal(ml.status,'CANDIDATE');
assert.equal(ml.stage,'RADAR');
assert.equal(ml.officialLineups,0);
assert.equal(ml.actionable,false);
assert(Number.isFinite(ml.probability) && ml.probability>.5);
assert(Number.isFinite(ml.watchPrice.american));
assert(ml.offenseProxy.away.official===false && ml.offenseProxy.home.official===false);assert(ml.lineupSnapshot?.away?.players?.length>=7);assert(ml.lineupSnapshot?.home?.players?.length>=7);
assert(ml.modelComponents?.runModel?.away && ml.modelComponents?.runModel?.home);
assert(ml.research && ml.research.probabilityMutation===false);
assert(['HOT','AVERAGE','COLD','UNKNOWN'].includes(ml.research.recentForm?.team?.label));
assert.equal(ml.research.externalProjections.status,'NOT_CONNECTED');
const ks=board.k.filter(x=>x.gamePk==='9001');
assert.equal(ks.length,2);
assert(ks.every(x=>x.status==='CANDIDATE'));
assert(ks.every(x=>Number.isFinite(x.expectedK)));
assert(ks.every(x=>x.actionable===false));
assert(ks.every(x=>x.modelComponents && Number.isFinite(x.modelComponents.expectedBF)));
assert(ks.every(x=>x.research && x.research.probabilityMutation===false));
assert(ks.every(x=>['HOT','AVERAGE','COLD','UNKNOWN'].includes(x.research.recentForm?.label)));
assert.equal(kCore.TARGET_K_MARKET_WEIGHT,0);
const wait=board.ml.find(x=>x.gamePk==='9002');
assert.equal(wait.status,'WAITING_STARTER');
assert.equal(wait.probability,undefined);

const noMarket=board.k.find(x=>x.gamePk==='9003'&&x.officialMlbId==='101');
assert(noMarket,'missing no-market radar row');
assert.equal(noMarket.status,'DISTRIBUTION_ONLY');
assert.equal(noMarket.marketState,'NO_MARKET');
assert.equal(noMarket.probability,null);
assert.equal(noMarket.listedOdds,null);
assert.equal(noMarket.ev,null);
assert(Number.isFinite(noMarket.expectedK));
const src=require('fs').readFileSync(require('path').join(__dirname,'../../../packages/core/src/slate_radar/radar_core.js'),'utf8');
assert(!/fetch\s*\(/.test(src),'Radar core must make no network/API calls');
assert(!/model_mlb_ml_projection_board_current/.test(src),'Radar core must not write/read production storage directly');
console.log('PASS Slate Radar 1.7/RCE 0.5: model-component visibility, Recent Form, non-mutating research, starter fail-closed, no-market integrity, 0 OddsPapi, never actionable');

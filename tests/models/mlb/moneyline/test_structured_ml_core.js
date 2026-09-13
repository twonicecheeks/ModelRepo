const assert=require('assert');
const fs=require('fs');
const path=require('path');
const core=require('../../../../packages/models/mlb/moneyline/structured_ml_core.js');
assert.equal(core.VERSION,'1.3');
assert.equal(core.MODEL_VERSION,'mlb-moneyline-v0.8.0-offense-strength-2026-09-06');
assert.equal(core.CALIBRATION_STATUS,'PRODUCTION_INPUT_MIGRATION');

function hitter(i,shift=0){return {PA:420-i*12,metrics:{'wRC+':100+shift+i%3*4,'ISO':.165+shift*.0005+i*.001,'xSLG':.395+shift*.0007+i*.002,'xwOBA':.318+shift*.0004+i*.001,'BB%':8.2+i*.12,'K%':22.8-i*.18,'Whiff%':25-i*.1,'Contact%':75+i*.1,'SwStr%':11.5,'HardHit%':39+i*.2,'Barrel%':8+i*.1,'BA':.245+i*.001}};}
function starter(offShift=0,pitchShift=0){return {pitcherMetrics:{'xwOBA':.315+pitchShift*.001,'BA':.240+pitchShift*.001,'xSLG':.390+pitchShift*.002,'HardHit%':38+pitchShift,'Barrel%':7.5+pitchShift*.2,'K%':24-pitchShift*.3,'BB%':7.5+pitchShift*.2,'Whiff%':27-pitchShift*.2},opponentTeamMetrics:{'xwOBA':.325+offShift*.001,'BA':.248+offShift*.001,'xSLG':.410+offShift*.002,'HardHit%':40+offShift,'Barrel%':8.5+offShift*.2,'K%':22-offShift*.2,'BB%':8.8+offShift*.1,'Contact%':75+offShift*.1},lineupStatus:'Official',lineup:Array.from({length:9},(_,i)=>hitter(i,offShift)),workload:{IP:5.7},bullpen:[{ERA:3.8,WHIP:1.20,K:25,BB:7,rest:'1'},{ERA:4.1,WHIP:1.30,K:23,BB:8,rest:'0'},{ERA:3.5,WHIP:1.18,K:27,BB:6,rest:'2'},{ERA:4.4,WHIP:1.35,K:21,BB:9,rest:'1'},{ERA:3.9,WHIP:1.25,K:24,BB:7.5,rest:'2'},{ERA:4.0,WHIP:1.27,K:24,BB:8,rest:'1'}],bullpenValidation:{status:'cross_market_confirmed'},gameConditions:['Park','Runs +3%']};}
const game={away:'AAA',home:'BBB',starters:{AAA:starter(4,1),BBB:starter(-3,-1)}};
const p=core.projectGame(game);
assert(p.complete);
const golden={awayRuns:4.197861719599442,homeRuns:4.558094281350443,awayWin:0.4439502280211731,homeWin:0.5560497719788269,awayOffenseFactor:1.0011041684002757,homeOffenseFactor:1.0110087673592425};
for(const [k,v] of Object.entries(golden)) assert(Math.abs(p[k]-v)<1e-12,`${k} drifted: ${p[k]} vs ${v}`);
assert.equal(p.favorite,'BBB');assert.equal(p.homeFair,'-125');assert.equal(p.awayFair,'+125');
assert(p.awayRunComponents && p.homeRunComponents,'run-component transparency missing');
for(const c of [p.awayRunComponents,p.homeRunComponents]){
  assert(Number.isFinite(c.starterRuns));assert(Number.isFinite(c.bullpenRuns));assert(Number.isFinite(c.rawRunsBeforePark));assert(Number.isFinite(c.parkFactor));assert(Number.isFinite(c.expectedStarterIP));
  assert(Math.abs(c.runs-((c.rawRunsBeforePark*c.parkFactor)+c.homeFieldRuns))<1e-12,'run component decomposition drift');
}


// Production coefficients now live only in the structured ML core; the legacy popup engine is removed.
const root=path.resolve(__dirname,'../../../..');
const coreSource=fs.readFileSync(path.join(root,'packages/models/mlb/moneyline/structured_ml_core.js'),'utf8');
for(const marker of [
  'mlb-moneyline-v0.8.0-offense-strength-2026-09-06',
  '.50*((wrc-100)/25)', '.18*((iso-.170)/.055)', '.12*((xslg-.400)/.065)', '.08*((xwoba-.320)/.040)',
  '.07*((bb-8.5)/3)', '-.05*((k-22.5)/5)', 'starterAdj+matchupAdj*.35',
  'homeWin=1/(1+Math.exp(-diff/1.60))'
]) assert(coreSource.includes(marker),`production v0.8 marker missing: ${marker}`);
assert(!fs.existsSync(path.join(root,'apps/chrome-extension/src/popup.js')),'legacy popup.js should be physically removed');

// Structured-board policy: unresolved wRC+ and bullpen MUST block promotion. Neutral values are diagnostic only.
const ids={};
for(let i=1;i<=18;i++) ids[String(i)]={playerId:String(i),name:`H${i}`,pa:300,kPct:20+i*.05,bbPct:8,ba:.250,xba:.248,xslg:.410,xwoba:.325,iso:.160,hardHitPct:40,barrelPct:8,whiffPct:24,swingPct:47,contactPct:76,swStrPct:11.28,wrcPlus:null,sourceSeason:'current'};
ids['101']={playerId:'101',name:'Away Starter',pa:500,kPct:25,bbPct:7,ba:.235,xba:.240,xslg:.390,xwoba:.310,iso:.155,hardHitPct:38,barrelPct:7,whiffPct:28,swingPct:49,contactPct:72,swStrPct:13.72,wrcPlus:null};
ids['202']={...ids['101'],playerId:'202',name:'Home Starter'};
const fakeCore={getRow:(_bundle,id)=>ids[String(id)]||null};
const hittersAway=Array.from({length:9},(_,i)=>({mlbId:String(i+1),name:`A${i+1}`,order:i+1}));
const hittersHome=Array.from({length:9},(_,i)=>({mlbId:String(i+10),name:`H${i+1}`,order:i+1}));
const pmStarter=(name,id)=>({identityState:'VERIFIED',officialName:name,officialMlbId:String(id),markets:{'player-pitcher-outs':{statistics:{overall:{season:{average:17.1}}},representative:{line:17.5}}}});
const starterBoard={games:[{pregame:true,gamePk:'9',away:'AAA',home:'BBB',startAt:'2026-09-07T20:00:00Z',starters:{away:pmStarter('Away Starter',101),home:pmStarter('Home Starter',202)}}]};
const lineupsByPk=new Map([['9',{away:{state:'OFFICIAL',hitters:hittersAway},home:{state:'OFFICIAL',hitters:hittersHome}}]]);
const b=core.buildStructuredBoard({starterBoard,lineupsByPk,pitcherSavant:{},batterSavant:{},savantCore:fakeCore,nowMs:Date.parse('2026-09-07T14:00:00Z')});
assert.equal(b.gameCount,1);assert.equal(b.readyCount,0);assert.equal(b.blockedCount,1);
const g=b.games[0];assert.equal(g.status,'BLOCKED');assert.equal(g.projectionEligible,false);assert.equal(g.diagnosticOnly,true);assert(g.diagnosticProjection?.complete);
assert(g.reasons.some(x=>x.includes('structured wRC+ source unresolved')));assert(g.reasons.some(x=>x.includes('structured bullpen source unresolved')));
assert(g.reasons.some(x=>x.includes('structured park/run-factor source unresolved')));


// Real-source path: exact-ID wRC+ + validated structured bullpen + park promotes an otherwise complete game to READY.
const wrcCore={getForSavantRow:(_bundle,id)=>({wrcPlus:95+(Number(id)%17),sourceSeason:'current',seasonFallback:false,pa:300})};
const bpRows=Array.from({length:6},(_,i)=>({playerId:String(700+i),name:`RP${i}`,ERA:3.6+i*.1,WHIP:1.15+i*.02,K:24+i*.3,BB:7+i*.2,rest:i===0?'0':'1+'}));
const bp={rows:bpRows,validation:{status:'validated',usageKnown:true,source:'MLB structured test'}};
const starterBoardReady={games:[{pregame:true,gamePk:'9',away:'AAA',home:'BBB',awayTeamId:'11',homeTeamId:'22',venueId:'77',venueName:'Test Park',startAt:'2026-09-07T20:00:00Z',starters:{away:pmStarter('Away Starter',101),home:pmStarter('Home Starter',202)}}]};
const parkRow={provider:'Baseball Savant Statcast Park Factors',providerVersion:'1.0',venue:'Test Park',window:'2024-2026',rollingYears:3,runIndex:103,runPct:3,runFactor:1.03,pa:50000};
const parkCore={getForVenue:()=>parkRow,conditionLines:()=>['Park: Test Park','Runs +3%']};
const ready=core.buildStructuredBoard({starterBoard:starterBoardReady,lineupsByPk,pitcherSavant:{},batterSavant:{},savantCore:fakeCore,wrcBundle:{},wrcCore,bullpensByTeam:new Map([['9:away',bp],['9:home',bp]]),parkBundle:{},parkCore,nowMs:Date.parse('2026-09-07T14:00:00Z')});
assert.equal(ready.readyCount,1);assert.equal(ready.blockedCount,0);assert.equal(ready.games[0].status,'READY');assert.equal(ready.games[0].projectionEligible,true);assert.equal(ready.games[0].diagnosticOnly,false);assert(ready.games[0].projection?.complete);assert.equal(ready.games[0].projection.productionInputSource,'STRUCTURED_ML_BOARD');
assert(ready.games[0].starters.AAA.lineup.every(h=>Number.isFinite(h.metrics['wRC+'])));assert.equal(ready.games[0].starters.AAA.bullpenValidation.status,'validated');
assert.equal(ready.games[0].watchReasons.length,0);assert.equal(ready.games[0].park.runFactor,1.03);assert.deepEqual(ready.games[0].starters.AAA.gameConditions,['Park: Test Park','Runs +3%']);


// Workload integrity: current-game line must outrank season average, and season-only is Radar/diagnostic only.
const wlCurrent=core.workloadFromStarter({markets:{'player-pitcher-outs':{statistics:{overall:{season:{average:16.8}}},representative:{line:12.5}}}});
assert.equal(wlCurrent.state,'CURRENT_GAME');assert(Math.abs(wlCurrent.IP-12.5/3)<1e-12);assert.equal(wlCurrent.productionEligible,true);
const wlSeason=core.workloadFromStarter({markets:{'player-pitcher-outs':{statistics:{overall:{season:{average:16.8}}},representative:{line:null}}}});
assert.equal(wlSeason.state,'SEASON_FALLBACK');assert.equal(wlSeason.productionEligible,false);assert(Math.abs(wlSeason.IP-5.6)<1e-12);
const wlProdMissing=core.workloadFromStarter({markets:{'player-pitcher-outs':{statistics:{overall:{season:{average:16.8}}},representative:{line:null}}}},{allowSeasonFallback:false});
assert.equal(wlProdMissing.state,'UNANCHORED');assert.equal(wlProdMissing.IP,null);


const burnsLike=pmStarter('Burns Like',101);burnsLike.markets['player-pitcher-outs'].representative.line=null;
const starterBoardBurns={games:[{pregame:true,gamePk:'10',away:'AAA',home:'BBB',awayTeamId:'11',homeTeamId:'22',venueId:'77',venueName:'Test Park',startAt:'2026-09-07T20:00:00Z',starters:{away:burnsLike,home:pmStarter('Home Starter',202)}}]};
const burnsBoard=core.buildStructuredBoard({starterBoard:starterBoardBurns,lineupsByPk:new Map([['10',{away:{state:'OFFICIAL',hitters:hittersAway},home:{state:'OFFICIAL',hitters:hittersHome}}]]),pitcherSavant:{},batterSavant:{},savantCore:fakeCore,wrcBundle:{},wrcCore,bullpensByTeam:new Map([['10:away',bp],['10:home',bp]]),parkBundle:{},parkCore,nowMs:Date.parse('2026-09-07T14:00:00Z')});
assert.equal(burnsBoard.readyCount,0);assert.equal(burnsBoard.games[0].status,'BLOCKED');assert(burnsBoard.games[0].reasons.some(x=>x.includes('current Pitcher Outs line missing; production workload unanchored')));

const same=core.parity(p,{...p},1e-12);assert.equal(same.pass,true);
const shifted=core.parity(p,{...p,homeWin:p.homeWin+.001},1e-12);assert.equal(shifted.pass,false);
assert(ready.games[0].sourceFreshness?.sourceCount>=1);
console.log('PASS structured ML core: v0.8 golden math + fail-closed production policy');

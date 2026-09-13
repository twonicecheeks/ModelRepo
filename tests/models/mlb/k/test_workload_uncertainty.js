const assert=require('assert');
const core=require('../../../../packages/models/mlb/k/structured_k_core.js');
const now=Date.parse('2026-09-07T20:36:00Z');
function market(line,o,u,avg,recent){return{state:'PRICED',observedAt:'2026-09-07T20:35:30Z',representative:{line,overOdds:o,underOdds:u,capturedAt:'2026-09-07T20:35:30Z',sportsbook:'FanDuel',sportsbookSlug:'fanduel'},statistics:{overall:{l30:recent||[],season:{average:avg},pitcherGrade:98}},offers:[{sportsbook:{name:'FanDuel',slug:'fanduel'},line,odds:{over:o,under:u}}]};}
const st={identityState:'VERIFIED',officialName:'Return Pitcher',officialMlbId:'601713',team:'SD',opponent:'WSH',markets:{
 'player-strikeouts':market(4.5,-122,-104,6,[6,7,5,6]),
 'player-pitcher-outs':market(12.5,-110,-110,17,[18,17,18]),
 'player-earned-runs':market(2.5,-110,-120,2.4,[2,2,3]),
 'player-hits-allowed':market(3.5,-110,-110,4.2,[3,4,4]),
 'player-walks':market(1.5,-110,-120,1.7,[1,2,2])}};
const lineup=Array.from({length:9},(_,i)=>({pa:300,K:21+i*.1,Whiff:25,SwStr:12.2,Contact:75,order:i+1}));
const raw={pa:66,K:36.4,Whiff:26.1,SwStr:12.7368,Contact:73.9,sourceSeason:'current',sampleCurrent:66,samplePrevious:620,previousK:27.1,previousWhiff:28.0,previousSwStr:12.0,previousContact:74.2};
const proj=core.projection({...st,gamePk:'1'},lineup,raw,now);
assert(proj.sampleAdjustment.applied,'small current sample should be shrunk');
assert(proj.sampleAdjustment.adjustedK<31,'36.4% raw K should be materially shrunk');
assert.equal(proj.workloadState,'LIMITED');
assert.equal(proj.workloadLimited,true);
assert.equal(proj.confidence,'Low');
assert(proj.uncertaintyMultiplier>1.25);
assert(proj.overProb<0.73,'tiny-sample + limited workload cannot retain a 73%+ over purely from raw current K%');
const moved=JSON.parse(JSON.stringify(st));moved.markets['player-strikeouts'].representative.line=7.5;moved.markets['player-strikeouts'].representative.overOdds=180;moved.markets['player-strikeouts'].representative.underOdds=-230;
const movedProj=core.projection({...moved,gamePk:'1'},lineup,raw,now);
assert(Math.abs(movedProj.expectedK-proj.expectedK)<1e-12,'target K line/price contaminated hardened expected K');
console.log('PASS Pivetta-like workload + small-sample uncertainty',proj.expectedK.toFixed(3),proj.overProb.toFixed(3),proj.confidence);
